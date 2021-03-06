<template>

  <KGrid>
    <KGridItem
      :layout8="{ span: 6 }"
      :layout12="{ span: 9 }"
    >
      <h3 v-if="isInImportMode" class="choose-message">
        {{ $tr('chooseContentToImport') }}
      </h3>
      <h3 v-else class="choose-message">
        {{ $tr('chooseContentToExport') }}
      </h3>
      <p class="available-space">
        {{ $tr('availableSpace', { space: bytesForHumans(spaceOnDrive) }) }}
      </p>
      <p class="resources-selected-message">
        {{ fileSizeText }}
      </p>
    </KGridItem>
    <KGridItem
      :layout8="{ span: 2, alignment: 'right' }"
      :layout12="{ span: 3, alignment: 'right' }"
    >
      <KButton
        class="confirm-button"
        :text="buttonText"
        :primary="true"
        :disabled="buttonIsDisabled"
        :style="{ top: buttonOffset }"
        @click="$emit('clickconfirm')"
      />
    </KGridItem>
    <KGridItem>
      <UiAlert
        v-if="remainingSpaceAfterTransfer <= 0"
        type="error"
        :dismissible="false"
      >
        {{ $tr('notEnoughSpace') }}
      </UiAlert>
    </KGridItem>
  </KGrid>

</template>


<script>

  import responsiveWindowMixin from 'kolibri.coreVue.mixins.responsiveWindowMixin';
  import UiAlert from 'keen-ui/src/UiAlert';
  import bytesForHumans from 'kolibri.utils.bytesForHumans';

  const RequiredNumber = { type: Number, required: true };

  export default {
    name: 'SelectedResourcesSize',
    components: {
      UiAlert,
    },
    mixins: [responsiveWindowMixin],
    props: {
      mode: {
        type: String,
        required: true,
        validator(val) {
          return val === 'import' || val === 'export';
        },
      },
      fileSize: RequiredNumber,
      resourceCount: RequiredNumber,
      spaceOnDrive: RequiredNumber,
    },
    computed: {
      isInImportMode() {
        return this.mode === 'import';
      },
      buttonText() {
        return this.isInImportMode ? this.$tr('import') : this.$tr('export');
      },
      buttonIsDisabled() {
        return this.resourceCount === 0 || this.remainingSpaceAfterTransfer <= 0;
      },
      remainingSpaceAfterTransfer() {
        return Math.max(this.spaceOnDrive - this.fileSize, 0);
      },
      fileSizeText() {
        return this.$tr('resourcesSelected', {
          fileSize: bytesForHumans(this.fileSize),
          resources: this.resourceCount,
        });
      },
      buttonOffset() {
        if (this.windowIsSmall) {
          return '0';
        }
        return '72px';
      },
    },
    methods: {
      bytesForHumans,
    },
    $trs: {
      chooseContentToExport: 'Choose content to export',
      chooseContentToImport: 'Choose content to import',
      export: 'export',
      import: 'import',
      notEnoughSpace: 'Not enough space on your device. Select less content to make more space.',
      availableSpace: 'Drive space available: {space}',
      resourcesSelected:
        'Content selected: {fileSize} ({resources, number, integer} {resources, plural, one {resource} other {resources}})',
    },
  };

</script>


<style lang="scss" scoped>

  .confirm-button {
    position: relative;
    margin: 0;
  }

</style>
