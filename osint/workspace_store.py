"""Durable local search history. No credentials or command arguments are stored."""

import datetime as dt
import json
import sqlite3
from contextlib import contextmanager

from paths import DATA_ROOT

DB_PATH = DATA_ROOT / "workspace.sqlite3"


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=20)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute(
        "CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, type TEXT, target TEXT, created TEXT, payload TEXT)"
    )
    db.execute("CREATE TABLE IF NOT EXISTS health (tool TEXT PRIMARY KEY, payload TEXT)")
    try:
        with db:
            yield db
    finally:
        db.close()


def put(record_id, record_type, payload):
    with connect() as db:
        db.execute(
            "INSERT OR REPLACE INTO records VALUES (?,?,?,?,?)",
            (
                record_id,
                record_type,
                payload.get("target", payload.get("query", "")),
                payload.get("timestamp", now()),
                json.dumps(payload),
            ),
        )


def get(record_id):
    with connect() as db:
        row = db.execute("SELECT payload FROM records WHERE id=?", (record_id,)).fetchone()
    return json.loads(row[0]) if row else None


def history(query="", limit=200):
    with connect() as db:
        # A group owns its child jobs so they appear once in the history list.
        rows = db.execute(
            "SELECT type,payload FROM records WHERE type NOT IN ('image','image reuse','saved_query','review_bundle') AND target LIKE ? ORDER BY created DESC LIMIT ?",
            ("%" + query + "%", limit * 13),
        ).fetchall()
    items = []
    for kind, raw in rows:
        item = json.loads(raw)
        if not item.get("group_id"):
            item["record_type"] = kind
            items.append(item)
        if len(items) >= limit:
            break
    return items


def update_health(tool, **fields):
    with connect() as db:
        row = db.execute("SELECT payload FROM health WHERE tool=?", (tool,)).fetchone()
        state = json.loads(row[0]) if row else {}
        state.update(fields)
        db.execute("INSERT OR REPLACE INTO health VALUES (?,?)", (tool, json.dumps(state)))


def health():
    with connect() as db:
        return {key: json.loads(raw) for key, raw in db.execute("SELECT tool,payload FROM health")}


def recover():
    with connect() as db:
        rows = db.execute("SELECT id,payload FROM records WHERE type='addon'").fetchall()
        for key, raw in rows:
            item = json.loads(raw)
            if item.get("status") in ("queued", "running"):
                item.update(
                    status="interrupted",
                    output=item.get("output", "")
                    + "\nSearch interrupted by server restart. Start a new search to retry.",
                )
                db.execute("UPDATE records SET payload=? WHERE id=?", (json.dumps(item), key))


def recover_research():
    """Mark incomplete synchronous research requests after a server restart."""
    with connect() as db:
        for key, raw in db.execute("SELECT id,payload FROM records WHERE type IN ('global_search','research_tool')").fetchall():
            item = json.loads(raw)
            if item.get('status') == 'running':
                item.update(status='interrupted', finished_at=now(), entries=item.get('entries', []),
                            errors=item.get('errors', []) + ['Research request interrupted by server restart. Review inputs before retrying.'])
                db.execute('UPDATE records SET payload=? WHERE id=?', (json.dumps(item), key))
