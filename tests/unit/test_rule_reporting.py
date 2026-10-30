import unittest

from ccz_randomizer.rules.reporting import job_rule_report
from ccz_randomizer.rules.config import default_rule_config, evaluate_job_rules
from ccz_randomizer.rule_members import RULE_MEMBER_INDICES
from ccz_randomizer.runtime.personnel_memory import read_rule_job_ids
from ccz_randomizer.jobs import JOB_MAP
from ccz_randomizer.app import format_user_log
from ccz_randomizer.ui.result_details import format_result_detail
from tests.unit.test_personnel_memory import RecordedReader


class RuleReportingTests(unittest.TestCase):
    def test_zhang_bao_only_rule_has_only_zhang_bao_in_log_and_detail(self):
        # User's active rule: 张宝 alone, count=1, threshold=8.
        config = default_rule_config()
        profile = config['profiles'][config['activeProfile']]
        profile['threePerson'].update(qualifiedMembers=['张宝'], jobQualificationMode='count',
                                      minQualifiedCount=1, minJobAverage=8)
        names = ('曹操', '夏侯惇', '夏侯渊', '张宝')
        ids = read_rule_job_ids(0, [RULE_MEMBER_INDICES[n] for n in names], reader_factory=RecordedReader)
        jobs = [dict(zip(('name', 'score', 'type'), JOB_MAP[i])) for i in ids]
        members = tuple((n, 'NONE', 'NONE') for n in names)
        evaluation = evaluate_job_rules(config, 'three', jobs,
            [dict(zip(('name', 'primaryType', 'secondaryType'), m)) for m in members])
        report, summaries = job_rule_report(evaluation, jobs, members, qualified=evaluation.qualified)
        self.assertEqual(['张宝'], [row['name'] for row in report['members']])
        self.assertEqual([f"张宝:{jobs[-1]['name']}"], summaries)
        text = format_user_log('R0 三人兵种筛选: ' + '; '.join(summaries) + '; 结果=通过')
        self.assertIn('张宝', text)
        self.assertNotIn('曹操', text)
        # Existing saved details can still contain the unselected initial team.
        report['members'].insert(0, dict(name='曹操', job=jobs[0]['name'], score=jobs[0]['score']))
        view = format_result_detail(dict(mode='three', label='合格', job=report,
            skill=dict(qualified=True, metrics={}, members=[])))
        self.assertEqual('兵种筛选 1 人', view['mode'])
        self.assertEqual(1, len(view['sections'][0]['rows']))
        self.assertTrue(view['sections'][0]['rows'][0].startswith('张宝：'))
        self.assertEqual('特技评分（初始三人）', view['sections'][1]['title'])
