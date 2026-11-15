"""Clear owned SQLite data transactionally while preserving usable schemas."""
from contextlib import closing
import sqlite3


def clear_database(path, category):
    if not path.is_file() or path.is_symlink():
        raise ValueError("数据库不可用")
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=1)) as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            maximum = 4 if category == "history" else 3
            if not 1 <= version <= maximum:
                raise ValueError("数据库版本不支持清理，请使用对应版本的工具")
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                if category == "history":
                    db.execute("DELETE FROM runs")
                else:
                    for table in ("equipment", "equipment_samples", "equipment_attempts", "equipment_names", "equipment_effects",
                                  "reasons", "skills", "members", "attempts", "rules", "coverage"):
                        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
                            db.execute(f'DELETE FROM "{table}"')
            # Keep the database usable for already-open history/statistics windows.
            # A reader may postpone compaction without invalidating a successful clear.
            try:
                db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                db.execute("VACUUM")
                db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except sqlite3.OperationalError:
                pass
    except sqlite3.Error as exc:
        raise ValueError("数据库正在使用或无法清理") from exc
