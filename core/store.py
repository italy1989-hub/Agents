import json
import os
import sqlite3

DB_PATH = os.getenv("STATE_DB", "state.db")

def _conn():
    c = sqlite3.connect(DB_PATH)
    c.execute("CREATE TABLE IF NOT EXISTS processed_cards "
              "(sha TEXT PRIMARY KEY, status TEXT, ids TEXT)")
    return c

def get(sha: str) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT status, ids FROM processed_cards WHERE sha=?", (sha,)).fetchone()
    return {"status": row[0], "ids": json.loads(row[1])} if row else None

def put(sha: str, status: str, ids: dict) -> None:
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO processed_cards VALUES (?,?,?)",
                  (sha, status, json.dumps(ids)))

def delete(sha: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM processed_cards WHERE sha=?", (sha,))
