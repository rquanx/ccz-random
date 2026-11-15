"""Reclaim space after transactional SQLite upgrades."""

def compact_database(db):
    """Reclaim migration pages; busy readers may defer physical reclamation."""
    import sqlite3
    try:
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        db.execute("VACUUM")
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.OperationalError:
        pass
