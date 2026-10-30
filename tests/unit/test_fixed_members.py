import struct
import unittest

from ccz_randomizer.fixed_members import FIXED_MEMBER_INDICES, FIXED_MEMBER_NAMES, expand_rule_members
from ccz_randomizer.rules.config import default_rule_config, validate_rule_config, evaluate_job_rules
from ccz_randomizer.jobs import JOB_MAP
from ccz_randomizer.runtime.personnel_memory import read_personnel
from tests.unit.test_personnel_memory import RecordedReader


class FixedMemberTests(unittest.TestCase):
    def test_all_indices_match_real_randomized_personnel(self):
        rows = read_personnel(0, FIXED_MEMBER_INDICES.values(), planned=True, reader_factory=RecordedReader)
        self.assertEqual([r["name"] for r in rows], list(FIXED_MEMBER_NAMES))

    def test_old_rules_keep_selection_and_new_affinities_roundtrip(self):
        config = default_rule_config()
        profile = config["profiles"][config["activeProfile"]]
        self.assertEqual(profile["threePerson"]["qualifiedMembers"], ["曹操", "夏侯惇", "夏侯渊"])
        profile["threePerson"].update(qualifiedMembers=list(FIXED_MEMBER_NAMES), minQualifiedCount=len(FIXED_MEMBER_NAMES))
        profile["memberAffinity"]["典韦"] = {"primaryType": "MASTER", "secondaryType": "NONE"}
        normalized = validate_rule_config(config)["profiles"][config["activeProfile"]]
        self.assertEqual(normalized["memberAffinity"]["典韦"]["primaryType"], "MASTER")
        self.assertEqual(normalized["threePerson"]["qualifiedMembers"], list(FIXED_MEMBER_NAMES))

    def test_future_member_is_scored_using_real_planned_job_and_affinity(self):
        reader = RecordedReader(0)
        def read_jobs(indices):
            return tuple(struct.unpack("<I", reader.read(0x00503F40 + i * 4, 4))[0] for i in indices)
        initial_names = ("曹操", "夏侯惇", "夏侯渊")
        ids, members = expand_rule_members(read_jobs((0, 1, 6)),
            tuple((name, "NONE", "NONE") for name in initial_names), ["典韦"], read_jobs)
        self.assertEqual(ids[-1], 33)
        config = default_rule_config()
        profile = config["profiles"][config["activeProfile"]]
        profile["threePerson"].update(qualifiedMembers=["典韦"], minQualifiedCount=1,
                                      jobQualificationMode="count", minJobAverage=7.2)
        profile["memberAffinity"]["典韦"] = {"primaryType": "ALL_ROUNDER", "secondaryType": "NONE"}
        jobs = [dict(zip(("name", "score", "type"), JOB_MAP[i])) for i in ids]
        rules = [dict(zip(("name", "primaryType", "secondaryType"), member)) for member in members]
        self.assertTrue(evaluate_job_rules(config, "three", jobs, rules).qualified)
        profile["memberAffinity"]["典韦"]["primaryType"] = "NONE"
        self.assertFalse(evaluate_job_rules(config, "three", jobs, rules).qualified)
