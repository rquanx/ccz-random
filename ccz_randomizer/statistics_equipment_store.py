"""Compact equipment observations using stable integer keys and shared text."""
SCHEMA_VERSION = 3
SCHEMA = """
CREATE TABLE IF NOT EXISTS equipment_attempts (
 id INTEGER PRIMARY KEY, attempt_id TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS equipment_names (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS equipment_effects (
 id INTEGER PRIMARY KEY, effect TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS equipment_samples (
 attempt_id INTEGER NOT NULL, name_id INTEGER NOT NULL, effect_id INTEGER NOT NULL,
 PRIMARY KEY(attempt_id,name_id)) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS equipment_sample_name ON equipment_samples(name_id,attempt_id);
CREATE VIEW IF NOT EXISTS equipment AS
 SELECT a.attempt_id,n.name,e.effect FROM equipment_samples s
 JOIN equipment_attempts a ON a.id=s.attempt_id
 JOIN equipment_names n ON n.id=s.name_id JOIN equipment_effects e ON e.id=s.effect_id;
"""


def initialize(db, base_schema):
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        raise ValueError("统计数据库版本过新，请使用对应版本的工具")
    if version == SCHEMA_VERSION:
        return False
    # DDL and all copied rows form one transaction, including concurrent initialization.
    db.execute("BEGIN IMMEDIATE")
    try:
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version == SCHEMA_VERSION:
            db.commit()
            return False
        if version > SCHEMA_VERSION:
            raise ValueError("统计数据库版本过新，请使用对应版本的工具")
        for statement in base_schema.split(";"):
            if statement.strip():
                db.execute(statement)
        legacy = db.execute("SELECT type FROM sqlite_master WHERE name='equipment'").fetchone()
        if legacy and legacy[0] == "table":
            db.execute("ALTER TABLE equipment RENAME TO equipment_legacy")
        for statement in SCHEMA.split(";"):
            if statement.strip():
                db.execute(statement)
        if legacy and legacy[0] == "table":
            db.execute("INSERT INTO equipment_attempts(attempt_id) SELECT DISTINCT attempt_id FROM equipment_legacy")
            db.execute("INSERT INTO equipment_names(name) SELECT DISTINCT name FROM equipment_legacy")
            db.execute("INSERT INTO equipment_effects(effect) SELECT DISTINCT effect FROM equipment_legacy")
            db.execute("INSERT INTO equipment_samples SELECT a.id,n.id,e.id FROM equipment_legacy s "
                       "JOIN equipment_attempts a ON a.attempt_id=s.attempt_id "
                       "JOIN equipment_names n ON n.name=s.name JOIN equipment_effects e ON e.effect=s.effect")
            db.execute("DROP TABLE equipment_legacy")
        db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        db.commit()
    except BaseException:
        db.rollback()
        raise
    return version > 0


def append(db, attempt_id, items):
    if not items:
        return
    db.execute("INSERT OR IGNORE INTO equipment_attempts(attempt_id) VALUES (?)", (attempt_id,))
    key = db.execute("SELECT id FROM equipment_attempts WHERE attempt_id=?", (attempt_id,)).fetchone()[0]
    db.executemany("INSERT OR IGNORE INTO equipment_names(name) VALUES (?)", ((item["name"],) for item in items))
    db.executemany("INSERT OR IGNORE INTO equipment_effects(effect) VALUES (?)", ((item["effect"],) for item in items))
    db.executemany("INSERT INTO equipment_samples SELECT ?,n.id,e.id FROM equipment_names n,equipment_effects e "
                   "WHERE n.name=? AND e.effect=?", ((key, item["name"], item["effect"]) for item in items))
