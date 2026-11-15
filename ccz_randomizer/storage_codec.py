"""Versioned, lossless compression for large local history payloads."""
import zlib

MAGIC = b"CCZ\x00Z1\x00"
MAX_PAYLOAD = 64 * 1024 * 1024


def unpack(data):
    if isinstance(data, str):
        return data.encode("utf-8")
    data = bytes(data)
    if not data.startswith(MAGIC):
        return data
    decoder = zlib.decompressobj()
    result = decoder.decompress(data[len(MAGIC):], MAX_PAYLOAD + 1)
    if len(result) > MAX_PAYLOAD or not decoder.eof or decoder.unused_data:
        raise ValueError("历史数据压缩内容损坏或大小异常")
    return result


def pack(data):
    raw = unpack(data)
    compressed = MAGIC + zlib.compress(raw, 6)
    return compressed if len(compressed) < len(raw) else raw


def compact_database(db):
    """Reclaim migration pages; busy readers may defer physical reclamation."""
    import sqlite3
    try:
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        db.execute("VACUUM")
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.OperationalError:
        pass


def compress_history(db):
    # Stream bounded batches rather than retaining the complete history in RAM.
    for table, column in (("results", "snapshot_json"), ("result_saves", "data")):
        key = "id" if table == "results" else "result_id"
        last = -1
        while True:
            rows = db.execute(f'SELECT {key},{column} FROM {table} WHERE {key}>? ORDER BY {key} LIMIT 64', (last,)).fetchall()
            if not rows:
                break
            for identifier, value in rows:
                packed = pack(value)
                if packed != value:
                    db.execute(f'UPDATE {table} SET {column}=? WHERE {key}=?', (packed, identifier))
            last = rows[-1][0]
