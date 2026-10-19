"""持久层：SQLite 优先，不可用时自动降级为进程内内存存储。

为什么要有降级：演示环境的目录可能只读、被沙箱限制或残留 journal，
SQLite 会直接抛 `disk I/O error`。此时若整个服务起不来，演示就废了；
降级到内存后功能完全一致（只是重启不保留），并在 /api/health 里如实标注。

表结构对应规划书 6.4：sessions / answer_events / profiles / telemetry。
会话用 JSON 快照整体读写（状态机天然幂等），事件与偏好单条可撤销/删除。
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from ..config import settings

_lock = threading.Lock()

_db_path: str = settings.db_path
_backend: str = "sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    payload     TEXT NOT NULL,
    created_at  REAL NOT NULL,
    expires_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS answer_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    question_id TEXT NOT NULL,
    dimension   TEXT NOT NULL,
    choice      TEXT NOT NULL,
    effects     TEXT NOT NULL,
    revision    INTEGER NOT NULL,
    request_id  TEXT,
    created_at  REAL NOT NULL,
    undone_at   REAL
);
CREATE INDEX IF NOT EXISTS idx_events_session ON answer_events(session_id);
CREATE TABLE IF NOT EXISTS profiles (
    anonymous_id TEXT PRIMARY KEY,
    consent      INTEGER NOT NULL DEFAULT 0,
    pref         TEXT NOT NULL,
    updated_at   REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS telemetry (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT,
    event       TEXT NOT NULL,
    payload     TEXT,
    created_at  REAL NOT NULL
);
"""


class _Memory:
    """与 SQLite 语义对齐的最小内存实现。"""

    sessions: dict[str, dict] = {}
    events: list[dict] = []
    profiles: dict[str, dict] = {}
    telemetry: list[dict] = []
    _seq = 0

    @classmethod
    def next_id(cls) -> int:
        cls._seq += 1
        return cls._seq


def db_path() -> str:
    return _db_path


def backend() -> str:
    return _backend


def _probe(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def _candidates() -> list[str]:
    home = os.path.expanduser("~")
    return [
        settings.db_path,
        "/tmp/mcd_mind_swipe.db",
        os.path.join(home, "Library", "Application Support", "mcd-mind-swipe", "mind_swipe.db"),
        os.path.join(home, ".mcd-mind-swipe", "mind_swipe.db"),
    ]


def init_db() -> None:
    """按候选顺序找第一个可写位置；全都不可写则退到内存后端。"""
    global _db_path, _backend
    for path in _candidates():
        try:
            _probe(path)
            _db_path = path
            _backend = "sqlite"
            return
        except (sqlite3.OperationalError, OSError):
            continue
    _backend = "memory"


@contextmanager
def connect():
    conn = sqlite3.connect(db_path(), timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------- 会话 ----------


def save_session(session_id: str, payload: dict, ttl_sec: int) -> None:
    now = time.time()
    if _backend == "memory":
        _Memory.sessions[session_id] = {
            "payload": json.loads(json.dumps(payload)),
            "created_at": now,
            "expires_at": now + ttl_sec,
        }
        return
    with _lock, connect() as conn:
        conn.execute(
            "INSERT INTO sessions(id, payload, created_at, expires_at) VALUES(?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, expires_at=excluded.expires_at",
            (session_id, json.dumps(payload, ensure_ascii=False), now, now + ttl_sec),
        )


def load_session(session_id: str) -> dict | None:
    if _backend == "memory":
        row = _Memory.sessions.get(session_id)
        if not row or row["expires_at"] < time.time():
            return None
        return json.loads(json.dumps(row["payload"]))
    with connect() as conn:
        row = conn.execute(
            "SELECT payload, expires_at FROM sessions WHERE id=?", (session_id,)
        ).fetchone()
    if not row or row["expires_at"] < time.time():
        return None
    return json.loads(row["payload"])


# ---------- 事件 ----------


def append_event(
    session_id: str,
    question_id: str,
    dimension: str,
    choice: str,
    effects: dict,
    revision: int,
    request_id: str | None,
) -> int:
    record = {
        "session_id": session_id,
        "question_id": question_id,
        "dimension": dimension,
        "choice": choice,
        "effects": dict(effects),
        "revision": revision,
        "request_id": request_id,
        "created_at": time.time(),
        "undone_at": None,
    }
    if _backend == "memory":
        record["id"] = _Memory.next_id()
        _Memory.events.append(record)
        return record["id"]
    with _lock, connect() as conn:
        cur = conn.execute(
            "INSERT INTO answer_events(session_id, question_id, dimension, choice, effects, revision, request_id, created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (session_id, question_id, dimension, choice, json.dumps(effects), revision, request_id, record["created_at"]),
        )
        return int(cur.lastrowid)


def undo_last_event(session_id: str) -> dict | None:
    if _backend == "memory":
        for ev in reversed(_Memory.events):
            if ev["session_id"] == session_id and ev["undone_at"] is None:
                ev["undone_at"] = time.time()
                return dict(ev)
        return None
    with _lock, connect() as conn:
        row = conn.execute(
            "SELECT * FROM answer_events WHERE session_id=? AND undone_at IS NULL ORDER BY id DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        if not row:
            return None
        conn.execute("UPDATE answer_events SET undone_at=? WHERE id=?", (time.time(), row["id"]))
        out = dict(row)
        if isinstance(out["effects"], str):
            out["effects"] = json.loads(out["effects"])
        return out


# ---------- 偏好 ----------


def get_profile(anonymous_id: str) -> dict | None:
    if _backend == "memory":
        row = _Memory.profiles.get(anonymous_id)
        if not row:
            return None
        return {
            "consent": row["consent"],
            "pref": json.loads(json.dumps(row["pref"])),
            "updated_at": row["updated_at"],
        }
    with connect() as conn:
        row = conn.execute("SELECT * FROM profiles WHERE anonymous_id=?", (anonymous_id,)).fetchone()
    if not row:
        return None
    return {"consent": bool(row["consent"]), "pref": json.loads(row["pref"]), "updated_at": row["updated_at"]}


def save_profile(anonymous_id: str, consent: bool, pref: dict) -> None:
    if _backend == "memory":
        _Memory.profiles[anonymous_id] = {
            "consent": consent,
            "pref": json.loads(json.dumps(pref)),
            "updated_at": time.time(),
        }
        return
    with _lock, connect() as conn:
        conn.execute(
            "INSERT INTO profiles(anonymous_id, consent, pref, updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(anonymous_id) DO UPDATE SET consent=excluded.consent, pref=excluded.pref, updated_at=excluded.updated_at",
            (anonymous_id, int(consent), json.dumps(pref, ensure_ascii=False), time.time()),
        )


def delete_profile(anonymous_id: str) -> None:
    if _backend == "memory":
        _Memory.profiles.pop(anonymous_id, None)
        _Memory.events[:] = [e for e in _Memory.events if not e["session_id"].startswith(anonymous_id)]
        return
    with _lock, connect() as conn:
        conn.execute("DELETE FROM profiles WHERE anonymous_id=?", (anonymous_id,))
        conn.execute("DELETE FROM answer_events WHERE session_id LIKE ?", (f"{anonymous_id}%",))


# ---------- 埋点 ----------


def log_event(session_id: str | None, event: str, payload: dict | None = None) -> None:
    record = {"session_id": session_id, "event": event, "payload": payload or {}, "created_at": time.time()}
    if _backend == "memory":
        record["id"] = _Memory.next_id()
        _Memory.telemetry.append(record)
        if len(_Memory.telemetry) > 5000:  # 演示进程的内存上限保护
            del _Memory.telemetry[:1000]
        return
    with _lock, connect() as conn:
        conn.execute(
            "INSERT INTO telemetry(session_id, event, payload, created_at) VALUES(?,?,?,?)",
            (session_id, event, json.dumps(payload or {}, ensure_ascii=False), record["created_at"]),
        )
