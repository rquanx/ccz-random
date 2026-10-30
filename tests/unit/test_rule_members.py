import json
import unittest
from pathlib import Path

from ccz_randomizer.rule_members import RULE_MEMBER_NAMES, RULE_MEMBER_INDICES, FIXED_JOB_INDICES
from ccz_randomizer.fixed_members import expand_rule_members
from ccz_randomizer.runtime.personnel_memory import read_rule_job_ids
from ccz_randomizer.rules.config import default_rule_config, validate_rule_config, evaluate_job_rules
from ccz_randomizer.jobs import JOB_MAP
from tests.unit.test_personnel_memory import RecordedReader, FIXTURES


class RuleMemberTests(unittest.TestCase):
    def test_all_effective_jobs_match_real_personnel_previews(self):
        expected = {}
        for filename in ('randomized-personnel.json', 'randomized-fixed-personnel.json'):
            for person in json.loads((FIXTURES / filename).read_text(encoding='utf-8')):
                expected[person['name']] = person['jobId']
        ids = read_rule_job_ids(0, RULE_MEMBER_INDICES.values(), reader_factory=RecordedReader)
        self.assertEqual(130, len(RULE_MEMBER_NAMES))
        self.assertEqual(expected, dict(zip(RULE_MEMBER_NAMES, ids)))
        self.assertEqual(5, len(FIXED_JOB_INDICES))

    def test_all_members_and_recruit_affinity_survive_rule_validation(self):
        config = default_rule_config()
        profile = config['profiles'][config['activeProfile']]
        self.assertEqual(['曹操', '夏侯惇', '夏侯渊'], profile['threePerson']['qualifiedMembers'])
        profile['threePerson'].update(qualifiedMembers=list(RULE_MEMBER_NAMES), minQualifiedCount=130)
        profile['memberAffinity']['张飞'] = dict(primaryType='MASTER', secondaryType='NONE')
        result = validate_rule_config(json.loads(json.dumps(config)))['profiles'][config['activeProfile']]
        self.assertEqual(list(RULE_MEMBER_NAMES), result['threePerson']['qualifiedMembers'])
        self.assertEqual('MASTER', result['memberAffinity']['张飞']['primaryType'])

    def test_recruits_and_fixed_configuration_enter_count_and_average_scoring(self):
        initial = ('曹操', '夏侯惇', '夏侯渊')
        selected = ('张飞', '吕布', '貂蝉')
        def read(positions):
            return read_rule_job_ids(0, positions, reader_factory=RecordedReader)
        ids, members = expand_rule_members(read([RULE_MEMBER_INDICES[n] for n in initial]),
            tuple((n, 'NONE', 'NONE') for n in initial), selected, read)
        self.assertEqual(list(initial + selected), [m[0] for m in members])
        config = default_rule_config()
        profile = config['profiles'][config['activeProfile']]
        settings = profile['threePerson']
        settings.update(qualifiedMembers=list(selected), minQualifiedCount=3, minJobAverage=0,
                        jobQualificationMode='count')
        jobs = [dict(zip(('name', 'score', 'type'), JOB_MAP[i])) for i in ids]
        rules = [dict(zip(('name', 'primaryType', 'secondaryType'), m)) for m in members]
        result = evaluate_job_rules(config, 'three', jobs, rules)
        self.assertTrue(result.qualified)
        self.assertEqual(list(selected), result.metrics['qualifiedMemberNames'])
        settings['minJobAverage'] = 20
        self.assertFalse(evaluate_job_rules(config, 'three', jobs, rules).qualified)
        settings.update(jobQualificationMode='average', minJobAverage=0)
        result = evaluate_job_rules(config, 'three', jobs, rules)
        self.assertAlmostEqual(sum(result.metrics['memberScores'][-3:]) / 3,
                               result.metrics['qualificationAverage'])
