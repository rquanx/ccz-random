"""Indexed, batched statistical storage; deleting history never removes observations."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
import time
from ccz_randomizer.statistics_rules import rule_links, resolve_revision
from ccz_randomizer.statistics_equipment_store import initialize, append as append_equipment
from ccz_randomizer.storage_codec import compact_database
from ccz_randomizer.equipment_labels import equipment_label_resolver

SCHEMA = """
CREATE TABLE IF NOT EXISTS rules (
 revision TEXT PRIMARY KEY, name TEXT NOT NULL, snapshot TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS attempts (
 id TEXT PRIMARY KEY, at REAL NOT NULL, run_id TEXT NOT NULL,
 revision TEXT NOT NULL, mode TEXT NOT NULL, round_number INTEGER,
 slot INTEGER, attempt INTEGER, status TEXT NOT NULL, elapsed REAL NOT NULL,
 job_checked INTEGER NOT NULL, skill_checked INTEGER NOT NULL, qualified INTEGER NOT NULL,
 saved INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS attempts_time ON attempts(at);
CREATE INDEX IF NOT EXISTS attempts_rule_time ON attempts(revision, at);
CREATE TABLE IF NOT EXISTS members (
 attempt_id TEXT NOT NULL, name TEXT NOT NULL, job TEXT,
 job_score REAL, skill_score REAL, PRIMARY KEY(attempt_id,name));
CREATE INDEX IF NOT EXISTS members_name ON members(name,attempt_id);
CREATE TABLE IF NOT EXISTS skills (
 attempt_id TEXT NOT NULL, name TEXT NOT NULL, skill TEXT NOT NULL,
 PRIMARY KEY(attempt_id,name,skill));
CREATE TABLE IF NOT EXISTS reasons (
 attempt_id TEXT NOT NULL, stage TEXT NOT NULL, reason TEXT NOT NULL,
 PRIMARY KEY(attempt_id,stage,reason));
CREATE TABLE IF NOT EXISTS coverage (lost INTEGER NOT NULL);
"""


def attempt_filter(*, start=None, end=None, revision=None, person=None, result="all"):
    if result not in ("all", "qualified", "rejected"):
        raise ValueError("未知的统计结果筛选")
    clauses, args = [], []
    for expression, value in (("a.at >= ?", start), ("a.at < ?", end)):
        if value is not None:
            clauses.append(expression)
            args.append(value)
    if revision is not None:
        revisions = (revision,) if isinstance(revision, str) else tuple(revision)
        clauses.append("a.revision IN (" + ",".join("?" for _ in revisions) + ")")
        args.extend(revisions)
    if person:
        clauses.append("EXISTS (SELECT 1 FROM members p WHERE p.attempt_id=a.id AND p.name=?)")
        args.append(person)
    if result == "qualified":
        clauses.append("a.qualified=1")
    elif result == "rejected":
        clauses.append("a.status IN ('job_failed','skill_failed')")
    return " WHERE " + " AND ".join(clauses) if clauses else "", args


def ranking_sql(kind, where, *, person=None, equipment_name=None):
    args = []
    if kind in ("jobs", "skills"):
        table, column = ("members", "m.job") if kind == "jobs" else ("skills", "m.skill")
        join = f" FROM attempts a JOIN {table} m ON m.attempt_id=a.id"
        conditions = [column + " IS NOT NULL"]
        if person:
            conditions.append("m.name=?")
            args.append(person)
    elif kind == "equipment":
        join = ("FROM attempts a JOIN equipment_attempts k ON k.attempt_id=a.id "
                "JOIN equipment_samples m ON m.attempt_id=k.id") if where else "FROM equipment_samples m"
        if equipment_name:
            where += (" AND " if where else " WHERE ") + "m.name_id=(SELECT id FROM equipment_names WHERE name=?)"
            args.append(equipment_name)
        # Aggregate integer keys before reading effect text; no repeated text joins per item.
        return ("SELECT equipment_label(e.effect) AS label,SUM(g.frequency) AS frequency FROM (SELECT m.effect_id,COUNT(*) AS frequency "
                + join + where +
                " GROUP BY m.effect_id) g JOIN equipment_effects e ON e.id=g.effect_id GROUP BY label"), args
    else:
        raise ValueError("未知的统计排行")
    if conditions:
        where += (" AND " if where else " WHERE ") + " AND ".join(conditions)
    return f"SELECT {column} AS label,COUNT(*) AS frequency{join}{where} GROUP BY {column}", args


class StatisticsRepository:
    def __init__(self, base: Path):
        self.base = Path(base)
        self.path = Path(base) / "ccz_fast_data" / "statistics.sqlite3"

    def _rule_links(self, db):
        return rule_links(self.base, db.execute("SELECT revision,name,snapshot FROM rules ORDER BY rowid").fetchall())

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=10)
        # Normalize only the small effect dictionary after integer aggregation.
        db.create_function('equipment_label', 1, equipment_label_resolver(), deterministic=True)
        try:
            # Switching WAL on a newly created database can fail immediately when
            # another process initializes it; SQLite's busy timeout alone does
            # not cover this pragma. Existing databases need no schema writes.
            deadline = time.monotonic() + 10
            while True:
                try:
                    if db.execute("PRAGMA journal_mode").fetchone()[0] != "wal":
                        db.execute("PRAGMA journal_mode=WAL")
                    if initialize(db, SCHEMA):
                        compact_database(db)
                    break
                except sqlite3.OperationalError as error:
                    if "locked" not in str(error) or time.monotonic() >= deadline:
                        raise
                    time.sleep(0.02)
            with db:
                yield db
        finally:
            db.close()

    def append(self, context, events):
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO rules VALUES (?,?,?)",
                       (context["revision"], context["rule_name"], context["rule_json"]))
            for event in events:
                inserted = db.execute("INSERT OR IGNORE INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                    event["id"], event["at"], context["run_id"], context["revision"], context["mode"],
                    event["round_number"], event["slot"], event["attempt"], event["status"],
                    event["elapsed"], event["job_checked"], event["skill_checked"], event["qualified"], event["saved"],
                )).rowcount
                if not inserted:
                    continue
                for member in event["members"]:
                    db.execute("INSERT INTO members VALUES (?,?,?,?,?)", (event["id"], member["name"],
                               member.get("job"), member.get("job_score"), member.get("skill_score")))
                    db.executemany("INSERT INTO skills VALUES (?,?,?)", (
                        (event["id"], member["name"], skill) for skill in member.get("skills", [])))
                db.executemany("INSERT OR IGNORE INTO reasons VALUES (?,?,?)", (
                    (event["id"], stage, reason) for stage, reason in event["reasons"]))
                append_equipment(db, event["id"], event.get("equipment"))

    def record_loss(self, count):
        with self.connect() as db:
            db.execute("INSERT INTO coverage VALUES (?)", (count,))

    def choices(self):
        with self.connect() as db:
            return dict(rules=sorted(((key, name) for key, (name, _) in self._rule_links(db).items()), key=lambda row: row[1]),
                        people=[r[0] for r in db.execute("SELECT DISTINCT name FROM members ORDER BY name")],
                        equipment=[r[0] for r in db.execute("SELECT name FROM equipment_names ORDER BY name")])

    def query(self, *, start=None, end=None, revision=None, person=None, result="all", equipment_name=None, view="all"):
        """Read the overview first; detailed pages can be requested independently."""
        if view not in ("all", "overview", "members", "equipment"):
            raise ValueError("未知的统计页面")
        with self.connect() as db:
            # All cards in one consistent read snapshot, including concurrent worker writes.
            db.execute("BEGIN")
            links = self._rule_links(db)
            where, args = attempt_filter(start=start, end=end, revision=resolve_revision(links, revision), person=person, result=result)
            def read(sql, extra=()):
                return db.execute(sql, [*args, *extra]).fetchall()
            base = " FROM attempts a" + where
            totals = read("SELECT COUNT(*),COALESCE(SUM(qualified),0),COALESCE(SUM(saved),0),"
                          "COALESCE(SUM(job_checked),0),COALESCE(SUM(skill_checked),0),"
                          "COALESCE(SUM(elapsed),0)" + base)[0]
            statuses = read("SELECT status,COUNT(*)" + base + " GROUP BY status ORDER BY COUNT(*) DESC")
            trend = read("SELECT strftime('%Y-%m-%d',at,'unixepoch','localtime'),COUNT(*),"
                         "SUM(saved)" + base + " GROUP BY 1 ORDER BY 1")
            details = {}
            if view in ("all", "members"):
                member_where = where + (" AND " if where else " WHERE ") + "m.name=?" if person else where
                member_args = (person,) if person else ()
                join = " FROM attempts a JOIN members m ON m.attempt_id=a.id" + member_where
                jobs = read("SELECT m.job,COUNT(*)" + join + (" AND " if member_where else " WHERE ") +
                            "m.job IS NOT NULL GROUP BY m.job ORDER BY COUNT(*) DESC,m.job", member_args)
                histograms = {}
                for stage in ("job", "skill"):
                    col = "m." + stage + "_score"
                    histograms[stage] = read("SELECT CAST(floor(" + col + ") AS INTEGER),COUNT(*)" + join +
                        (" AND " if member_where else " WHERE ") + col + " IS NOT NULL GROUP BY 1 ORDER BY 1", member_args)
                skill_join = " FROM attempts a JOIN skills m ON m.attempt_id=a.id" + member_where
                skills = read("SELECT m.skill,COUNT(*)" + skill_join +
                              " GROUP BY m.skill ORDER BY COUNT(*) DESC,m.skill", member_args)
                details.update(jobs=jobs, skills=skills, histograms=histograms)
            if view in ("all", "equipment"):
                equipment_sql, equipment_args = ranking_sql("equipment", where, equipment_name=equipment_name)
                equipment = read(equipment_sql + " ORDER BY frequency DESC,label", equipment_args)
                equipment_where = where + (" AND " if where else " WHERE ")
                sample_filter = ""
                if equipment_name:
                    sample_filter = " AND s.name_id=(SELECT id FROM equipment_names WHERE name=?)"
                sample_join = ("FROM attempts a JOIN equipment_attempts k ON k.attempt_id=a.id") if where else "FROM equipment_attempts k"
                equipment_samples = read("SELECT COUNT(*) " + sample_join + equipment_where +
                    "EXISTS (SELECT 1 FROM equipment_samples s WHERE s.attempt_id=k.id" + sample_filter + ")", equipment_args)[0][0]
                details.update(equipment=equipment, equipment_samples=equipment_samples)
            reasons = read("SELECT r.reason,COUNT(*) FROM attempts a JOIN reasons r ON r.attempt_id=a.id" +
                           where + " GROUP BY r.reason ORDER BY COUNT(*) DESC LIMIT 12")
            comparisons = read("SELECT a.revision,COUNT(*),SUM(saved)"
                               " FROM attempts a JOIN rules r ON r.revision=a.revision" + where +
                               " GROUP BY a.revision")
            totals_by_revision = {key: (count, saved) for key, count, saved in comparisons}
            comparisons = [(name, sum(totals_by_revision.get(key, (0, 0))[0] for key in revisions),
                            sum(totals_by_revision.get(key, (0, 0))[1] for key in revisions))
                           for name, revisions in links.values()]
            comparisons = sorted((row for row in comparisons if row[1]), key=lambda row: -row[1])[:12]
            lost = db.execute("SELECT COALESCE(SUM(lost),0) FROM coverage").fetchone()[0]
            return dict(totals=totals, statuses=statuses, trend=trend,
                        reasons=reasons, comparisons=comparisons, lost=lost, **details)

    def ranking(self, kind, *, query="", page=1, page_size=50, equipment_name=None, **filters):
        if page < 1 or not 1 <= page_size <= 200:
            raise ValueError("无效的排行分页")
        with self.connect() as db:
            db.execute("BEGIN")
            filters["revision"] = resolve_revision(self._rule_links(db), filters.get("revision"))
            where, args = attempt_filter(**filters)
            sql, extra = ranking_sql(kind, where, person=filters.get("person"), equipment_name=equipment_name)
            params = [*args, *extra]
            # Aggregate observations once. The result is the small distinct
            # label dictionary, not the potentially millions of observations.
            # Let SQLite do matching/sorting to retain its exact collation.
            ranked = db.execute("WITH ranked AS (" + sql + ") "
                "SELECT label,frequency,instr(lower(label),lower(?))>0 FROM ranked "
                "ORDER BY frequency DESC,label COLLATE NOCASE", params + [query.strip()]).fetchall()
            total = sum(frequency for _, frequency, _ in ranked)
            matching = [(label, frequency) for label, frequency, matches in ranked if matches]
            count = len(matching)
            rows = matching[(page-1)*page_size:page*page_size]
            return dict(rows=rows, count=count, total=total, page=page, page_size=page_size)
