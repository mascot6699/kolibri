import tempfile

import portend
from django.test import TestCase
from mock import patch

from kolibri.utils import cli
from kolibri.utils.server import NotRunning
from kolibri.utils.tests.helpers import override_option


class SanityCheckTestCase(TestCase):
    @patch("kolibri.utils.sanity_checks.logging.error")
    @patch("kolibri.utils.sanity_checks.get_status", return_value={1, 2, 3})
    def test_other_kolibri_running(self, status_mock, logging_mock):
        with self.assertRaises(SystemExit):
            cli.main(["manage"])
            logging_mock.assert_called()

    @patch("kolibri.utils.sanity_checks.logging.error")
    @patch("kolibri.utils.sanity_checks.portend.free")
    @patch("kolibri.utils.sanity_checks.get_status")
    def test_port_occupied(self, status_mock, portend_mock, logging_mock):
        status_mock.side_effect = NotRunning("Kolibri not running")
        portend_mock.side_effect = portend.Timeout
        with self.assertRaises(SystemExit):
            cli.main(["manage"])
            logging_mock.assert_called()

    @patch("kolibri.utils.cli.get_version", return_value="")
    @patch("kolibri.utils.sanity_checks.logging.error")
    @override_option("Paths", "CONTENT_DIR", "/dir_dne")
    def test_content_dir_dne(self, logging_mock, get_version):
        with self.assertRaises(SystemExit):
            cli.main(["manage"])
            logging_mock.assert_called()

    @patch("kolibri.utils.sanity_checks.logging.error")
    @patch("kolibri.utils.sanity_checks.os.access", return_value=False)
    @override_option("Paths", "CONTENT_DIR", tempfile.mkdtemp())
    def test_content_dir_not_writable(self, access_mock, logging_mock):
        with self.assertRaises(SystemExit):
            cli.main(["manage"])
            logging_mock.assert_called()

    @patch("kolibri.utils.cli.get_version", return_value="")
    @patch("kolibri.utils.sanity_checks.shutil.move")
    @patch(
        "kolibri.utils.sanity_checks.os.path.exists",
        # This requires an additional return value at the end
        # to prevent a StopIteration exception during test
        # execution, but the first three values are the ones
        # that make the difference to the assert count below.
        side_effect=[True, False, True, False],
    )
    def test_old_log_file_exists(self, path_exists_mock, move_mock, get_version):
        cli.setup_logging()
        # Check if the number of calls to shutil.move equals to the number of times
        # os.path.exists returns True
        self.assertEqual(move_mock.call_count, 2)
