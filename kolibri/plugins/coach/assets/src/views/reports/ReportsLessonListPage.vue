<template>

  <CoreBase
    :immersivePage="false"
    :authorized="userIsAuthorized"
    authorizedRole="adminOrCoach"
    :showSubNav="true"
  >
    <TopNavbar slot="sub-nav" />

    <KPageContainer>
      <ReportsHeader />
      <KSelect
        v-model="filter"
        :label="coreString('showAction')"
        :options="filterOptions"
        :inline="true"
      />
      <CoreTable :emptyMessage="emptyMessage">
        <thead slot="thead">
          <tr>
            <th>{{ coachString('titleLabel') }}</th>
            <th>{{ coreString('progressLabel') }}</th>
            <th>{{ coachString('recipientsLabel') }}</th>
            <th>{{ coachString('statusLabel') }}</th>
          </tr>
        </thead>
        <transition-group slot="tbody" tag="tbody" name="list">
          <tr v-for="tableRow in table" :key="tableRow.id">
            <td>
              <KLabeledIcon icon="lesson">
                <KRouterLink
                  :text="tableRow.title"
                  :to="classRoute('ReportsLessonReportPage', { lessonId: tableRow.id })"
                />
              </KLabeledIcon>
            </td>
            <td>
              <StatusSummary
                :tally="tableRow.tally"
                :verbose="true"
              />
            </td>
            <td>
              <Recipients
                :groupNames="tableRow.groupNames"
                :hasAssignments="tableRow.hasAssignments"
              />
            </td>
            <td><LessonActive :active="tableRow.active" /></td>
          </tr>
        </transition-group>
      </CoreTable>
    </KPageContainer>
  </CoreBase>

</template>


<script>

  import commonCoreStrings from 'kolibri.coreVue.mixins.commonCoreStrings';
  import commonCoach from '../common';
  import ReportsHeader from './ReportsHeader';

  export default {
    name: 'ReportsLessonListPage',
    components: {
      ReportsHeader,
    },
    mixins: [commonCoach, commonCoreStrings],
    data() {
      return {
        filter: 'allLessons',
      };
    },
    computed: {
      emptyMessage() {
        if (this.filter.value === 'allLessons') {
          return this.coachString('lessonListEmptyState');
        }
        if (this.filter.value === 'activeLessons') {
          return this.$tr('noActiveLessons');
        }
        if (this.filter.value === 'inactiveLessons') {
          return this.$tr('noInactiveLessons');
        }

        return '';
      },
      filterOptions() {
        return [
          {
            label: this.coreString('allLessonsLabel'),
            value: 'allLessons',
          },
          {
            label: this.$tr('activeLessons'),
            value: 'activeLessons',
          },
          {
            label: this.$tr('inactiveLessons'),
            value: 'inactiveLessons',
          },
        ];
      },
      table() {
        const filtered = this.lessons.filter(lesson => {
          if (this.filter.value === 'allLessons') {
            return true;
          } else if (this.filter.value === 'activeLessons') {
            return lesson.active;
          } else if (this.filter.value === 'inactiveLessons') {
            return !lesson.active;
          }
        });
        const sorted = this._.sortBy(filtered, ['title', 'active']);
        return sorted.map(lesson => {
          const learners = this.getLearnersForLesson(lesson);
          const tableRow = {
            totalLearners: learners.length,
            tally: this.getLessonStatusTally(lesson.id, learners),
            groupNames: this.getGroupNames(lesson.groups),
            hasAssignments: learners.length > 0,
          };
          Object.assign(tableRow, lesson);
          return tableRow;
        });
      },
    },
    beforeMount() {
      this.filter = this.filterOptions[0];
    },
    $trs: {
      activeLessons: 'Active lessons',
      inactiveLessons: 'Inactive lessons',
      noActiveLessons: 'No active lessons',
      noInactiveLessons: 'No inactive lessons',
    },
  };

</script>


<style lang="scss" scoped>

  @import '../common/list-transition';

</style>
