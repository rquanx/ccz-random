import hashlib
import json
import os
import struct
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from ccz_randomizer.entry_catalog import attach_fixed_entries, missing_fixed_entries
from ccz_randomizer.fixed_members import fixed_member_indices
from ccz_randomizer.game_versions import detect_game_version
from ccz_randomizer.recruitment import parse_recruits
from ccz_randomizer.recruitment_catalog import load_catalog, attach_recruitment
from ccz_randomizer.rule_members import rule_member_indices, validate_selected_members
from ccz_randomizer.runtime.personnel_memory import decode_personnel_record, validate_personnel_identity
from ccz_randomizer.runtime.skill_memory import RECORD_ARRAY_BASE_POINTER_ADDRESS
from tools.research.recruitment_catalog import extract_stage_recruits, STAGE_EXTRAS

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/personnel_220_1104"
VERSION = "2.20-1104"


class Game1104Tests(unittest.TestCase):
    def test_blue_route_guanyu_is_available_for_rules_and_personnel_preview(self):
        script = (FIXTURES / 'r48.eex').read_bytes()
        self.assertIn('关羽入队处理'.encode('gb18030'), script)
        self.assertEqual(bytes.fromhex('3b00020003000e0000003e000000'), script[0x17a8:0x17b6])
        self.assertIn('关羽兵种赋值'.encode('gb18030'), script)
        self.assertEqual(3, rule_member_indices(VERSION)['关羽'])
        validate_selected_members(['关羽'], VERSION)
        raw = (FIXTURES / 'records.bin').read_bytes()
        rows = []
        for name, index in fixed_member_indices(VERSION).items():
            actual, member_id, job = decode_personnel_record(raw[index*72:(index+1)*72], index)
            rows.append(dict(name=actual, recordIndex=index, memberId=member_id, jobId=job))
        guanyu = next(row for row in attach_fixed_entries(rows, version=VERSION) if row['name'] == '关羽')
        self.assertEqual(('fixed', 0, '蓝线 · 江陵之战', True),
                         (guanyu['entryKind'], guanyu['recruitmentCost'], guanyu['stage'], guanyu['availabilityVerified']))

    def test_old_save_roster_is_rejected_before_randomization(self):
        data = bytearray((FIXTURES / 'records.bin').read_bytes())
        class Reader:
            def __init__(self, pid): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, address, size):
                if address == RECORD_ARRAY_BASE_POINTER_ADDRESS:
                    return struct.pack('<I', 0x10000000)
                return bytes(data[:size])
        validate_personnel_identity(0, rule_member_indices(VERSION), reader_factory=Reader)
        data[30*72:31*72] = (FIXTURES / 'old-record-30.bin').read_bytes()
        with self.assertRaisesRegex(ValueError, '曹昂.*邓艾.*第 20 栏'):
            validate_personnel_identity(0, rule_member_indices(VERSION), reader_factory=Reader)

    def test_result_keeps_runner_version_when_active_game_changes(self):
        from ccz_randomizer import app
        runner = SimpleNamespace(_result_outcome='accepted', _game_version=VERSION)
        with patch.dict(os.environ, CCZ_GAME_VERSION='2.2'):
            self.assertEqual(VERSION, app.result_detail_for_runner(runner, 1, 1)['gameVersion'])

    def test_real_script_matches_complete_new_catalog(self):
        script = (FIXTURES / "r99.eex").read_bytes()
        stages = extract_stage_recruits(script)
        catalog = load_catalog(version=VERSION)
        actual = {s["stageId"]: sorted(s["recordIndices"]) for s in stages}
        expected = {}
        for person in catalog:
            for stage in person["stages"]:
                expected.setdefault(stage["stageId"], []).append(person["recordIndex"])
        self.assertEqual(actual, {k: sorted(v) for k, v in expected.items()})
        self.assertEqual((44, 126, 138), (len(stages), len(catalog), sum(map(len, actual.values()))))
        self.assertEqual([148], actual[25])
        self.assertEqual([90, 138, 139], actual[31])
        old = {p['name'] for p in load_catalog(version="2.2")}
        new = {p['name'] for p in catalog}
        self.assertEqual({'曹仁', '荀攸', '貂蝉'}, old - new)
        self.assertEqual({'曹昂', '邓艾', '许攸', '马腾', '韩遂', '曹植', '曹真',
                          '曹休', '曹纯', '曹豹', '杨任', '公孙瓒', '陈到'}, new - old)

    def test_real_extra_commands_fail_closed_when_unknown_or_truncated(self):
        block = (FIXTURES / "r99-stage-assignments.bin").read_bytes()
        for bad in (block[:-3], block.replace(STAGE_EXTRAS[25], b'\xff' + STAGE_EXTRAS[25][1:])):
            with self.assertRaises(ValueError):
                extract_stage_recruits(bad)
        with self.assertRaises(ValueError):
            extract_stage_recruits((FIXTURES / "r99.eex").read_bytes()[:2000])

    def test_real_title_records_bind_to_144_people_without_index_aliasing(self):
        raw = (FIXTURES / "records.bin").read_bytes()
        skills = json.loads((FIXTURES / "title-skills.json").read_text(encoding="utf-8"))
        rows = []
        for member in skills['members']:
            i = member['record_index']
            name, member_id, job = decode_personnel_record(raw[i*72:(i+1)*72], i)
            rows.append(dict(recordIndex=i, name=name, memberId=member_id, jobId=job,
                             personalTalents=[s['display_name'] for s in member['personal']],
                             jobTalents=[s['display_name'] for s in member['job']]))
        recruits = attach_recruitment(rows, load_catalog(version=VERSION))
        fixed = attach_fixed_entries(rows, version=VERSION)
        parsed = parse_recruits(dict(schemaVersion=1, gameVersion=VERSION, personnel=recruits+fixed))
        self.assertEqual(144, len(parsed))
        self.assertEqual(18, len(fixed))
        by_name = {p.name: p for p in parsed}
        self.assertEqual(30, by_name['曹昂'].record_index)
        self.assertEqual(31, by_name['邓艾'].record_index)
        self.assertEqual(148, by_name['曹植'].record_index)
        for name in ('曹仁', '荀攸', '貂蝉'):
            self.assertEqual(('fixed', 0), (by_name[name].entry_kind, by_name[name].cost))
        self.assertEqual('共通 · 徐州平定战', by_name['貂蝉'].stage)
        self.assertEqual((3, ('虎豹骑', '保留随机结果')), (by_name['曹纯'].cost, by_name['曹纯'].job_choices))
        self.assertEqual((4, ('名将', '随机')), (by_name['邓艾'].cost, by_name['邓艾'].job_choices))

    def test_switching_versions_does_not_reuse_catalog_or_relabel_old_history(self):
        for version, count in [(VERSION, 126), ('2.2', 116), (VERSION, 126)]:
            with patch.dict(os.environ, CCZ_GAME_VERSION=version):
                self.assertEqual(count, len(load_catalog()))
                self.assertEqual(14, len(missing_fixed_entries('2.2')))
                self.assertEqual(18, len(missing_fixed_entries(VERSION)))
        self.assertEqual(130, len(rule_member_indices('2.2')))
        self.assertEqual(144, len(rule_member_indices(VERSION)))
        with self.assertRaisesRegex(ValueError, '曹昂'):
            validate_selected_members(['曹昂'], '2.2')
        validate_selected_members(['曹昂', '曹仁'], VERSION)

    def test_new_rule_choices_round_trip_without_changing_old_selection(self):
        from ccz_randomizer.rules.config import default_rule_config, validate_rule_config
        config = default_rule_config()
        profile = config['profiles'][config['activeProfile']]
        original = list(profile['threePerson']['qualifiedMembers'])
        self.assertEqual(original, validate_rule_config(config)['profiles'][config['activeProfile']]['threePerson']['qualifiedMembers'])
        profile['threePerson'].update(qualifiedMembers=['曹昂', '邓艾'], minQualifiedCount=1)
        validated = validate_rule_config(config)
        self.assertEqual(['曹昂', '邓艾'], validated['profiles'][validated['activeProfile']]['threePerson']['qualifiedMembers'])

    def test_fingerprint_differences_do_not_block_execution(self):
        # Minimal file contents exercise the hash contract, not invented game records.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exe = root / 'Ekd5.exe'
            exe.write_bytes(b'executable')
            (root / 'Imsg.e5').write_bytes(b'messages')
            manifest = {VERSION: {n: hashlib.sha256((root/n).read_bytes()).hexdigest()
                                  for n in ('Ekd5.exe', 'Imsg.e5')}}
            self.assertEqual(VERSION, detect_game_version(exe, manifest=manifest))
            (root / 'Imsg.e5').write_bytes(b'old messages')
            self.assertEqual(VERSION, detect_game_version(exe, manifest=manifest))
            exe.write_bytes(b'unknown')
            from ccz_randomizer.profiles import load_profile
            self.assertEqual(load_profile().game_version, detect_game_version(exe, manifest=manifest))

    def test_optional_fingerprint_file_is_ignored_when_present(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exe = root / 'Ekd5.exe'
            exe.write_bytes(b'executable')
            optional = root / 'Data.e5'
            optional.write_bytes(b'optional resource from this distribution')
            manifest = {VERSION: {
                'Ekd5.exe': hashlib.sha256(exe.read_bytes()).hexdigest(),
                'Data.e5': None,
            }}
            self.assertEqual(VERSION, detect_game_version(exe, manifest=manifest))
