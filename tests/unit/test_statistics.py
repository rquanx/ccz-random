import datetime as dt
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ccz_randomizer.rules.config import default_rule_config, evaluate_job_rules, evaluate_skill_rules
from ccz_randomizer.rules.reporting import job_rule_report
from ccz_randomizer.workflow.result_snapshots import skill_result_detail
from ccz_randomizer.statistics import StatisticsRecorder, observation
from ccz_randomizer.statistics_store import StatisticsRepository
from ccz_randomizer.history_filters import parse_time_range


def runner_fixture(*, reject=False, skills=True, skill_reject=False):
    # Confirmed rule inputs from test_rule_config and the actual runtime report builders.
    config = default_rule_config()
    profile = config["profiles"][config["activeProfile"]]
    profile["jobScoring"]["affinityEnabled"] = False
    profile["threePerson"].update(jobQualificationMode="total", minJobAverage=21 if reject else 15,
        qualifiedMembers=["曹操", "夏侯渊"], minQualifiedCount=1)
    members = [dict(name="曹操", primaryType="ALL_ROUNDER", secondaryType="WARRIOR"),
               dict(name="夏侯惇", primaryType="WARRIOR", secondaryType="ALL_ROUNDER"),
               dict(name="夏侯渊", primaryType="MASTER", secondaryType="ALL_ROUNDER")]
    jobs = [dict(name="群雄", score=8, type="ALL_ROUNDER"),
            dict(name="轻步兵", score=6, type="WARRIOR"),
            dict(name="道士", score=7, type="MASTER")]
    evaluation = evaluate_job_rules(config, "three", jobs, members)
    report, _ = job_rule_report(evaluation, jobs,
        [(m["name"], m["primaryType"], m["secondaryType"]) for m in members], qualified=evaluation.qualified)
    skill = None
    if skills and not reject:
        profile["sevenPerson"]["skillBaseScores"] = {"能力辅助（防辅攻精）": 0 if skill_reject else 4.5}
        evaluation = evaluate_skill_rules(config, 7.6, {"夏侯惇": ["能力辅助 防→攻精"]}, set(), set(), set())
        skill = skill_result_detail(evaluation, [SimpleNamespace(name="夏侯惇",
            skillList=[SimpleNamespace(name="能力辅助 防→攻精")])])
    return SimpleNamespace(_job_evaluation_detail=report, _skill_evaluation_detail=skill,
                           _result_outcome="job_failed" if reject else "skill_failed" if skill_reject else "accepted")


def record_process(base):
    recorder = StatisticsRecorder(Path(base), run_id="shared-run", rule_name="规则", rule={}, mode="three")
    for index in range(50):
        with recorder.attempt(runner_fixture(reject=True), round_number=1, slot=1, attempt=index+1):
            pass
    recorder.close()
    return recorder.lost


class StatisticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.repo = StatisticsRepository(self.base)

    def tearDown(self):
        self.tmp.cleanup()

    def recorder(self, **kwargs):
        return StatisticsRecorder(self.base, run_id=kwargs.get("run_id", "run"),
            rule_name=kwargs.get("name", "规则"), rule=kwargs.get("rule", {"threshold": 8}), mode="three")

    def capture(self, recorder, runner, *, saved=False, round_number=1, attempt=1):
        with recorder.attempt(runner, round_number=round_number, slot=1, attempt=attempt) as result:
            result["saved"] = saved

    def test_short_circuit_does_not_invent_skills_and_only_selected_jobs(self):
        recorder = self.recorder()
        self.capture(recorder, runner_fixture(reject=True))
        recorder.close()
        data = self.repo.query()
        self.assertEqual((1, 0, 0, 1, 0), data["totals"][:5])
        self.assertEqual([("job_failed", 1)], data["statuses"])
        self.assertEqual([], data["skills"])
        self.assertEqual([], data["histograms"]["skill"])
        self.assertEqual(2, sum(count for _, count in data["jobs"]))
        self.assertNotIn("夏侯惇", self.repo.choices()["people"])

    def test_person_filter_overview_and_member_distributions_have_different_scope(self):
        recorder = self.recorder()
        self.capture(recorder, runner_fixture(), saved=True)
        self.capture(recorder, runner_fixture(reject=True))
        recorder.close()
        all_data = self.repo.query()
        self.assertEqual((2, 1, 1, 2, 1), all_data["totals"][:5])
        data = self.repo.query(person="夏侯惇")
        self.assertEqual(1, data["totals"][0])
        self.assertEqual([], data["jobs"])
        self.assertEqual([("能力辅助 防→攻精", 1)], data["skills"])
        self.assertEqual([(4, 1)], data["histograms"]["skill"])
        cao = self.repo.query(person="曹操")
        self.assertEqual(2, cao["totals"][0])
        self.assertEqual([("群雄", 2)], cao["jobs"])
        self.assertEqual([], cao["skills"])

    def test_save_failure_and_saved_then_postprocessing_failure(self):
        recorder = self.recorder()
        for saved in (False, True):
            runner = runner_fixture()
            runner._result_save_committed = saved
            with self.assertRaisesRegex(RuntimeError, "failure"):
                with recorder.attempt(runner, round_number=1, slot=1, attempt=1):
                    raise RuntimeError("failure")
        recorder.close()
        data = self.repo.query()
        self.assertEqual((2, 2, 1, 2, 2), data["totals"][:5])
        self.assertEqual([("error", 2)], data["statuses"])

    def test_skill_rejection_has_its_own_reasons_and_observed_skill_sample(self):
        recorder = self.recorder()
        self.capture(recorder, runner_fixture(skill_reject=True))
        recorder.close()
        data = self.repo.query()
        self.assertEqual((1, 0, 0, 1, 1), data["totals"][:5])
        self.assertEqual([("skill_failed", 1)], data["statuses"])
        self.assertEqual([("特技综合评价未达到当前规则要求", 1)], data["reasons"])
        self.assertEqual([(0, 1)], data["histograms"]["skill"])

    def test_result_filters_cover_all_charts_without_treating_errors_as_rejections(self):
        recorder = self.recorder()
        self.capture(recorder, runner_fixture(), saved=True)
        self.capture(recorder, runner_fixture(reject=True))
        self.capture(recorder, runner_fixture(skill_reject=True))
        with self.assertRaises(OSError):
            with recorder.attempt(runner_fixture(), round_number=1, slot=1, attempt=4):
                raise OSError("save failed after qualification")
        with self.assertRaises(KeyboardInterrupt):
            with recorder.attempt(SimpleNamespace(), round_number=1, slot=1, attempt=5):
                raise KeyboardInterrupt()
        recorder.close()
        self.assertEqual(5, self.repo.query(result="all")["totals"][0])
        qualified = self.repo.query(result="qualified")
        rejected = self.repo.query(result="rejected")
        self.assertEqual((2, 2, 1), qualified["totals"][:3])
        self.assertEqual({"saved": 1, "error": 1}, dict(qualified["statuses"]))
        self.assertEqual([], qualified["reasons"])
        self.assertEqual((2, 0, 0), rejected["totals"][:3])
        self.assertEqual({"job_failed": 1, "skill_failed": 1}, dict(rejected["statuses"]))
        self.assertEqual(2, sum(count for _, count in rejected["reasons"]))
        self.assertEqual(4, sum(count for _, count in rejected["jobs"]))
        self.assertEqual([("能力辅助 防→攻精", 1)], rejected["skills"])
        self.assertEqual(2, sum(row[1] for row in rejected["trend"]))
        self.assertEqual((2, 0), tuple(rejected["comparisons"][0][1:]))
        self.assertEqual([(0, 1)], rejected["histograms"]["skill"])
        combined = self.repo.query(result="rejected", person="夏侯惇",
            revision=recorder.context["revision"], start=0, end=time.time()+1)
        self.assertEqual(1, combined["totals"][0])
        self.assertEqual([], combined["jobs"])
        with self.assertRaises(ValueError):
            self.repo.query(result="typo")

    def test_zero_result_stop_and_recovery_invocations_are_preserved(self):
        recorder = self.recorder()
        runner = SimpleNamespace()
        with self.assertRaises(KeyboardInterrupt):
            with recorder.attempt(runner, round_number=4, slot=2, attempt=1):
                raise KeyboardInterrupt()
        with self.assertRaises(RuntimeError):
            with recorder.attempt(runner, round_number=4, slot=2, attempt=1):
                raise RuntimeError()
        self.capture(recorder, runner_fixture(reject=True), round_number=4)
        recorder.close()
        self.assertEqual(3, self.repo.query()["totals"][0])
        self.assertEqual({"stopped": 1, "error": 1, "job_failed": 1}, dict(self.repo.query()["statuses"]))
        self.assertFalse((self.base / "ccz_fast_data/history.sqlite3").exists())

    def test_legacy_rule_choices_only_show_latest_filter_per_name(self):
        for name, rule in (("规则", {"threshold": 8}), ("规则", {"threshold": 9}), ("另一规则", {"threshold": 8})):
            recorder = self.recorder(name=name, rule=rule)
            self.capture(recorder, runner_fixture(reject=True))
            recorder.close()
        choices = self.repo.choices()["rules"]
        self.assertEqual(2, len(choices))
        for revision, _ in choices:
            self.assertEqual(1, self.repo.query(revision=revision)["totals"][0])
        self.assertEqual(2, len(self.repo.query()["comparisons"]))
        self.assertEqual(3, self.repo.query()["totals"][0])

    def test_time_boundaries_use_local_time_and_inclusive_end_date(self):
        recorder = self.recorder()
        event = observation(runner_fixture(reject=True), saved=False, interrupted=False, failed=False, elapsed=1)
        event.update(round_number=1, slot=1, attempt=1)
        event["at"] = dt.datetime(2026, 11, 12, 23, 59, 59).timestamp()
        self.repo.append(recorder.context, [event])
        recorder.close()
        after, before = parse_time_range("2026-11-12", "2026-11-12")
        start, end = (dt.datetime.fromisoformat(v).timestamp() for v in (after, before))
        self.assertEqual(1, self.repo.query(start=start, end=end)["totals"][0])
        self.assertEqual(0, self.repo.query(start=end)["totals"][0])
        self.assertEqual(0, self.repo.query(end=event["at"])["totals"][0])

    def test_multiworker_batched_writes_and_retry_idempotence(self):
        runner = runner_fixture(reject=True)
        def worker(number):
            recorder = self.recorder(run_id=f"run-{number}")
            for index in range(100):
                self.capture(recorder, runner, round_number=index//25+1, attempt=index+1)
            recorder.close()
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(worker, range(4)))
        self.assertEqual(400, self.repo.query()["totals"][0])
        event = observation(runner, saved=False, interrupted=False, failed=False, elapsed=1)
        event.update(round_number=1, slot=1, attempt=1)
        recorder = self.recorder()
        self.repo.append(recorder.context, [event, event])
        recorder.close()
        self.assertEqual(401, self.repo.query()["totals"][0])

    def test_storage_failure_does_not_change_random_result_and_reports_loss(self):
        recorder = self.recorder()
        with patch.object(recorder.repository, "append", side_effect=OSError("disk full")):
            with self.assertLogs("ccz_randomizer.statistics", level="ERROR"):
                self.capture(recorder, runner_fixture(), saved=True)
                recorder.close()
        self.assertEqual(1, self.repo.query()["lost"])

    def test_separate_processes_can_initialize_and_collect_without_loss(self):
        with ProcessPoolExecutor(max_workers=4) as pool:
            lost = list(pool.map(record_process, [str(self.base)] * 4))
        self.assertEqual([0] * 4, lost)
        self.assertEqual(200, self.repo.query()["totals"][0])

    def test_database_initialization_recovers_from_an_actual_exclusive_lock(self):
        import sqlite3
        self.repo.path.parent.mkdir(parents=True)
        locked = sqlite3.connect(self.repo.path)
        locked.execute("BEGIN EXCLUSIVE")
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.repo.query)
            time.sleep(0.05)
            locked.rollback()
            locked.close()
            self.assertEqual(0, future.result(timeout=15)["totals"][0])

    def test_empty_database_and_transaction_rollback(self):
        self.assertEqual(0, self.repo.query()["totals"][0])
        self.assertEqual([], self.repo.choices()["rules"])
        recorder = self.recorder()
        event = observation(runner_fixture(), saved=True, interrupted=False, failed=False, elapsed=1)
        event.update(round_number=1, slot=1, attempt=1)
        event["members"].append(event["members"][0])
        with self.assertRaises(Exception):
            self.repo.append(recorder.context, [event])
        recorder.close()
        self.assertEqual(0, self.repo.query()["totals"][0])


if __name__ == "__main__":
    unittest.main()
