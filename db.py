"""
Lightweight SQLite database for tracking processed videos.

Prevents re-processing duplicates via SHA256 content hashing.
Manages the posting workflow: es/ -> to_post/ -> posted/.
"""

import hashlib
import os
import shutil
import sqlite3
import sys
from pathlib import Path

# Fix Unicode output on Windows terminals (emoji in filenames etc.)
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_DB_PATH = Path(__file__).parent / "zack_spanish.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    file_hash TEXT NOT NULL UNIQUE,
    source_path TEXT NOT NULL,
    es_video TEXT,
    es_captioned TEXT,
    es_meta TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT,
    posted_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create tables if they don't exist. Safe to call on every run."""
    conn = _connect()
    conn.executescript(_SCHEMA)
    _migrate(conn)
    conn.commit()
    conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns that may be missing from older schema versions."""
    migrations = [
        ("videos", "es_meta", "TEXT"),
    ]
    for table, column, col_type in migrations:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        except sqlite3.OperationalError:
            pass  # Column already exists


def hash_file(path: str) -> str:
    """Return SHA256 hex digest of a file's contents."""
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            sha.update(chunk)
    return sha.hexdigest()


def lookup_video(file_hash: str) -> dict | None:
    """Return video row by hash, or None if not found."""
    conn = _connect()
    row = conn.execute("SELECT * FROM videos WHERE file_hash = ?", (file_hash,)).fetchone()
    conn.close()
    return dict(row) if row else None


def insert_video(filename: str, file_hash: str, source_path: str) -> int:
    """Register a new video. Returns the new row id."""
    conn = _connect()
    cur = conn.execute(
        "INSERT INTO videos (filename, file_hash, source_path) VALUES (?, ?, ?)",
        (filename, file_hash, source_path),
    )
    conn.commit()
    vid = cur.lastrowid
    conn.close()
    return vid


def update_status(video_id: int, status: str, **extra) -> None:
    """Update video status and optional extra fields. Auto-sets updated_at."""
    fields = ["status = ?", "updated_at = datetime('now')"]
    values = [status]
    for col, val in extra.items():
        fields.append(f"{col} = ?")
        values.append(val)
    values.append(video_id)
    conn = _connect()
    conn.execute(f"UPDATE videos SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()
    conn.close()


def get_videos_by_status(status: str) -> list[dict]:
    """Return all videos with the given status, newest first."""
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM videos WHERE status = ? ORDER BY created_at DESC",
        (status,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_by_status() -> dict[str, int]:
    """Return {status: count} for all statuses."""
    conn = _connect()
    rows = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM videos GROUP BY status"
    ).fetchall()
    conn.close()
    return {r["status"]: r["cnt"] for r in rows}


def mark_posted(es_captioned: str) -> None:
    """Move a captioned video from to_post/ to posted/ and update DB."""
    es_captioned = os.path.normpath(es_captioned)
    filename = os.path.basename(es_captioned)
    project_root = Path(__file__).parent
    to_post_path = project_root / "to_post" / filename
    posted_path = project_root / "posted" / filename

    if not to_post_path.exists():
        print(f"ERROR: {to_post_path} not found in to_post/")
        sys.exit(1)

    shutil.move(str(to_post_path), str(posted_path))

    conn = _connect()
    conn.execute(
        "UPDATE videos SET status = 'posted', posted_at = datetime('now'), "
        "updated_at = datetime('now') WHERE es_captioned = ? OR es_captioned = ?",
        (es_captioned, es_captioned.replace("\\", "/")),
    )
    conn.commit()
    conn.close()
    print(f"Posted: {filename}  -> posted/")


def copy_to_post(es_captioned: str) -> None:
    """Copy a captioned video from es/ to to_post/ and update status."""
    filename = os.path.basename(es_captioned)
    project_root = Path(__file__).parent
    src = project_root / "es" / filename
    dst = project_root / "to_post" / filename

    if not src.exists():
        print(f"ERROR: {src} not found in es/")
        sys.exit(1)

    shutil.copy2(str(src), str(dst))

    conn = _connect()
    conn.execute(
        "UPDATE videos SET status = 'ready', updated_at = datetime('now') "
        "WHERE es_captioned = ?",
        (es_captioned,),
    )
    conn.commit()
    conn.close()
    print(f"Ready to post: {filename}  -> to_post/")


# ---------------------------------------------------------------------------
#  CLI
# ---------------------------------------------------------------------------

def _cli():
    if len(sys.argv) < 2:
        print("Usage: python db.py <command> [args]")
        print()
        print("Commands:")
        print("  init              Initialize the database")
        print("  status            Show counts by status")
        print("  list [status]     List videos (default: all)")
        print("  to-post <path>    Copy captioned video to to_post/")
        print("  posted <path>     Move from to_post/ to posted/")
        print("  check <path>      Check if a file hash is already in DB")
        return

    cmd = sys.argv[1]

    if cmd == "init":
        init_db()
        print(f"Database initialized: {_DB_PATH}")

    elif cmd == "status":
        init_db()
        counts = count_by_status()
        if not counts:
            print("No videos in database.")
        else:
            for status, count in sorted(counts.items()):
                print(f"  {status}: {count}")

    elif cmd == "list":
        init_db()
        status_filter = sys.argv[2] if len(sys.argv) > 2 else None
        conn = _connect()
        if status_filter:
            rows = conn.execute(
                "SELECT * FROM videos WHERE status = ? ORDER BY created_at DESC",
                (status_filter,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM videos ORDER BY created_at DESC"
            ).fetchall()
        conn.close()
        if not rows:
            print("No videos found.")
        for r in rows:
            print(f"  [{r['status']}] {r['filename']}  (id={r['id']})")

    elif cmd == "to-post":
        if len(sys.argv) < 3:
            print("Usage: python db.py to-post <captioned_path>")
            return
        init_db()
        copy_to_post(sys.argv[2])

    elif cmd == "posted":
        if len(sys.argv) < 3:
            print("Usage: python db.py posted <captioned_path>")
            return
        init_db()
        mark_posted(sys.argv[2])

    elif cmd == "check":
        if len(sys.argv) < 3:
            print("Usage: python db.py check <file_path>")
            return
        fhash = hash_file(sys.argv[2])
        video = lookup_video(fhash)
        if video:
            print(f"DUPLICATE: {video['filename']} (status={video['status']})")
        else:
            print("Not found — safe to process.")

    else:
        print(f"Unknown command: {cmd}")


if __name__ == "__main__":
    _cli()
