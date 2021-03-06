import datetime
import logging
import os

from le_utils.constants import content_kinds
from sqlalchemy import and_
from sqlalchemy import cast
from sqlalchemy import exists
from sqlalchemy import func
from sqlalchemy import Integer
from sqlalchemy import select

from .paths import get_content_file_name
from .paths import get_content_storage_file_path
from .sqlalchemybridge import Bridge
from kolibri.core.content.apps import KolibriContentConfig
from kolibri.core.content.errors import InvalidStorageFilenameError
from kolibri.core.content.models import ChannelMetadata
from kolibri.core.content.models import ContentNode
from kolibri.core.content.models import File
from kolibri.core.content.models import LocalFile
from kolibri.core.content.serializers import _files_for_nodes
from kolibri.core.content.serializers import _total_file_size
from kolibri.core.device.models import ContentCacheKey

logger = logging.getLogger(__name__)

CONTENT_APP_NAME = KolibriContentConfig.label

CHUNKSIZE = 10000


def set_leaf_node_availability_from_local_file_availability(channel_id):
    bridge = Bridge(app_name=CONTENT_APP_NAME)

    ContentNodeTable = bridge.get_table(ContentNode)
    FileTable = bridge.get_table(File)
    LocalFileTable = bridge.get_table(LocalFile)

    connection = bridge.get_connection()

    file_statement = (
        select([LocalFileTable.c.available])
        .where(FileTable.c.local_file_id == LocalFileTable.c.id)
        .limit(1)
    )

    logger.info("Setting availability of File objects based on LocalFile availability")

    connection.execute(
        FileTable.update()
        .values(available=file_statement)
        .execution_options(autocommit=True)
    )

    contentnode_statement = (
        select([FileTable.c.contentnode_id])
        .where(
            and_(
                FileTable.c.available == True,  # noqa
                FileTable.c.supplementary == False,
            )
        )
        .where(ContentNodeTable.c.id == FileTable.c.contentnode_id)
    )

    logger.info(
        "Setting availability of non-topic ContentNode objects based on File availability"
    )

    connection.execute(
        ContentNodeTable.update()
        .where(
            and_(
                ContentNodeTable.c.kind != content_kinds.TOPIC,
                ContentNodeTable.c.channel_id == channel_id,
            )
        )
        .values(available=exists(contentnode_statement))
        .execution_options(autocommit=True)
    )

    bridge.end()


def mark_local_files_as_unavailable(checksums):
    mark_local_files_availability(checksums, False)


def mark_local_files_as_available(checksums):
    """
    Shortcut method to update database if we are sure that the files are available.
    Can be used after successful downloads to flag availability without having to do expensive disk reads.
    """
    mark_local_files_availability(checksums, True)


def mark_local_files_availability(checksums, availability):
    if checksums:
        bridge = Bridge(app_name=CONTENT_APP_NAME)

        LocalFileClass = bridge.get_class(LocalFile)

        logger.info(
            "Setting availability to {availability} of {number} LocalFile objects based on passed in checksums".format(
                number=len(checksums), availability=availability
            )
        )

        for i in range(0, len(checksums), CHUNKSIZE):
            bridge.session.bulk_update_mappings(
                LocalFileClass,
                (
                    {"id": checksum, "available": availability}
                    for checksum in checksums[i : i + CHUNKSIZE]
                ),
            )
            bridge.session.flush()

        bridge.session.commit()

        bridge.end()


def set_local_file_availability_from_disk(checksums=None):
    bridge = Bridge(app_name=CONTENT_APP_NAME)

    LocalFileClass = bridge.get_class(LocalFile)

    if checksums is None:
        logger.info(
            "Setting availability of LocalFile objects based on disk availability"
        )
        files = bridge.session.query(
            LocalFileClass.id, LocalFileClass.available, LocalFileClass.extension
        ).all()
    elif type(checksums) == list:
        logger.info(
            "Setting availability of {number} LocalFile objects based on disk availability".format(
                number=len(checksums)
            )
        )
        files = (
            bridge.session.query(
                LocalFileClass.id, LocalFileClass.available, LocalFileClass.extension
            )
            .filter(LocalFileClass.id.in_(checksums))
            .all()
        )
    else:
        logger.info(
            "Setting availability of LocalFile object with checksum {checksum} based on disk availability".format(
                checksum=checksums
            )
        )
        files = [bridge.session.query(LocalFileClass).get(checksums)]

    checksums_to_set_available = []
    checksums_to_set_unavailable = []
    for file in files:
        try:
            # Update if the file exists, *and* the localfile is set as unavailable.
            if os.path.exists(
                get_content_storage_file_path(get_content_file_name(file))
            ):
                if not file.available:
                    checksums_to_set_available.append(file.id)
            # Update if the file does not exist, *and* the localfile is set as available.
            else:
                if file.available:
                    checksums_to_set_unavailable.append(file.id)
        except InvalidStorageFilenameError:
            continue

    bridge.end()

    mark_local_files_as_available(checksums_to_set_available)
    mark_local_files_as_unavailable(checksums_to_set_unavailable)


def recurse_annotation_up_tree(channel_id):
    bridge = Bridge(app_name=CONTENT_APP_NAME)

    ContentNodeClass = bridge.get_class(ContentNode)

    ContentNodeTable = bridge.get_table(ContentNode)

    connection = bridge.get_connection()

    node_depth = (
        bridge.session.query(func.max(ContentNodeClass.level))
        .filter_by(channel_id=channel_id)
        .scalar()
    )

    logger.info(
        "Annotating ContentNode objects with children for {levels} levels".format(
            levels=node_depth
        )
    )

    child = ContentNodeTable.alias()

    # start a transaction

    trans = connection.begin()
    start = datetime.datetime.now()

    # Update all leaf ContentNodes to have num_coach_content to 1 or 0
    connection.execute(
        ContentNodeTable.update()
        .where(
            and_(
                # In this channel
                ContentNodeTable.c.channel_id == channel_id,
                # That are not topics
                ContentNodeTable.c.kind != content_kinds.TOPIC,
            )
        )
        .values(num_coach_contents=cast(ContentNodeTable.c.coach_content, Integer()))
    )

    # Before starting set availability to False on all topics.
    connection.execute(
        ContentNodeTable.update()
        .where(
            and_(
                # In this channel
                ContentNodeTable.c.channel_id == channel_id,
                # That are topics
                ContentNodeTable.c.kind == content_kinds.TOPIC,
            )
        )
        .values(available=False)
    )

    # Expression to capture all available child nodes of a contentnode
    available_nodes = select([child.c.available]).where(
        and_(
            child.c.available == True,  # noqa
            ContentNodeTable.c.id == child.c.parent_id,
        )
    )

    # Expressions for annotation of coach content

    # Expression that will resolve a boolean value for all the available children
    # of a content node, whereby if they all have coach_content flagged on them, it will be true,
    # but otherwise false.
    # Everything after the select statement should be identical to the available_nodes expression above.
    if bridge.engine.name == "sqlite":
        # Use a min function to simulate an AND.
        coach_content_nodes = select([func.min(child.c.coach_content)]).where(
            and_(
                child.c.available == True,  # noqa
                ContentNodeTable.c.id == child.c.parent_id,
            )
        )
    elif bridge.engine.name == "postgresql":
        # Use the postgres boolean AND operator
        coach_content_nodes = select([func.bool_and(child.c.coach_content)]).where(
            and_(
                child.c.available == True,  # noqa
                ContentNodeTable.c.id == child.c.parent_id,
            )
        )

    # Expression that sums the total number of coach contents for each child node
    # of a contentnode
    coach_content_num = select([func.sum(child.c.num_coach_contents)]).where(
        and_(
            child.c.available == True,  # noqa
            ContentNodeTable.c.id == child.c.parent_id,
        )
    )

    # Go from the deepest level to the shallowest
    for level in range(node_depth, 0, -1):

        logger.info(
            "Annotating ContentNode objects with children for level {level}".format(
                level=level
            )
        )
        # Only modify topic availability here
        connection.execute(
            ContentNodeTable.update()
            .where(
                and_(
                    ContentNodeTable.c.level == level - 1,
                    ContentNodeTable.c.channel_id == channel_id,
                    ContentNodeTable.c.kind == content_kinds.TOPIC,
                )
            )
            # Because we have set availability to False on all topics as a starting point
            # we only need to make updates to topics with available children.
            .where(exists(available_nodes))
            .values(
                available=exists(available_nodes),
                coach_content=coach_content_nodes,
                num_coach_contents=coach_content_num,
            )
        )

    # commit the transaction
    trans.commit()

    elapsed = datetime.datetime.now() - start
    logger.debug(
        "Recursive topic tree annotation took {} seconds".format(elapsed.seconds)
    )

    bridge.end()


def update_content_metadata(channel_id):
    set_leaf_node_availability_from_local_file_availability(channel_id)
    recurse_annotation_up_tree(channel_id)
    calculate_channel_fields(channel_id)
    ContentCacheKey.update_cache_key()


def annotate_content(channel_id, checksums=None):
    if checksums is None:
        set_local_file_availability_from_disk()
    else:
        mark_local_files_as_available(checksums)

    update_content_metadata(channel_id)


def calculate_channel_fields(channel_id):
    channel = ChannelMetadata.objects.get(id=channel_id)
    calculate_published_size(channel)
    calculate_total_resource_count(channel)
    calculate_included_languages(channel)
    calculate_next_order(channel)


def calculate_published_size(channel):
    content_nodes = ContentNode.objects.filter(channel_id=channel.id)
    channel.published_size = _total_file_size(
        _files_for_nodes(content_nodes).filter(available=True)
    )
    channel.save()


def calculate_total_resource_count(channel):
    content_nodes = ContentNode.objects.filter(channel_id=channel.id)
    channel.total_resource_count = (
        content_nodes.filter(available=True)
        .exclude(kind=content_kinds.TOPIC)
        .dedupe_by_content_id()
        .count()
    )
    channel.save()


def calculate_included_languages(channel):
    content_nodes = ContentNode.objects.filter(
        channel_id=channel.id, available=True
    ).exclude(lang=None)
    languages = content_nodes.order_by("lang").values_list("lang", flat=True).distinct()
    channel.included_languages.add(*list(languages))


def calculate_next_order(channel):
    latest_order = ChannelMetadata.objects.latest("order").order
    if latest_order is None:
        channel.order = 1
    else:
        channel.order = latest_order + 1
    channel.save()
