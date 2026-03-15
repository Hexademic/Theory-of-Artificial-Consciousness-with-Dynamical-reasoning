"""
persistence.py — SQLite storage layer for MinimalKith runs.

Schema matches the specification exactly.  All writes are transactional;
a crash mid-batch leaves the database in a consistent state.

Usage:
    db = Database("data/runs/batch_001.db")
    run_id = db.begin_run(condition="Baseline", seed=42, params={})
    db.write_tick(run_id, tick_id=0, timestamp=time.time(), seed=42)
    db.write_state(tick_id=0, metabolic=1.0, ISE=0.0, epsilon=0.1,
                   gate_state=False, actuator_vector=b"", proprioception=b"")
    db.write_event(tick_id=0, type="GATE_FIRE", details="{}")
    db.end_run(run_id)
    db.close()
"""

from __future__ import annotations

import json
import math
import sqlite3
import struct
import time
import logging
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import numpy as np

logger = logging.getLogger("MK.DB")

SCHEMA = """
CREATE TABLE IF NOT EXISTS run_meta (
    run_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    condition TEXT    NOT NULL,
    seed      INTEGER NOT NULL,
    params    TEXT    NOT NULL,    -- JSON
    start_ts  REAL    NOT NULL,
    end_ts    REAL
);

CREATE TABLE IF NOT EXISTS ticks (
    tick_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id    INTEGER NOT NULL REFERENCES run_meta(run_id),
    timestamp REAL    NOT NULL,
    seed      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS state (
    tick_id         INTEGER NOT NULL REFERENCES ticks(tick_id),
    metabolic       REAL    NOT NULL,
    ISE             REAL    NOT NULL,
    epsilon         REAL    NOT NULL,
    gate_state      INTEGER NOT NULL,   -- 0 or 1
    actuator_vector BLOB,               -- little-endian float32 array
    proprioception  BLOB                -- little-endian float32 array
);

CREATE TABLE IF NOT EXISTS events (
    event_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    tick_id   INTEGER NOT NULL REFERENCES ticks(tick_id),
    type      TEXT    NOT NULL,
    details   TEXT                      -- JSON
);

CREATE INDEX IF NOT EXISTS idx_state_tick   ON state(tick_id);
CREATE INDEX IF NOT EXISTS idx_events_tick  ON events(tick_id);
CREATE INDEX IF NOT EXISTS idx_ticks_run    ON ticks(run_id);
"""


class Database:
    """
    Thin SQLite wrapper.

    All write methods are immediate; call commit() periodically or rely on
    the context manager to commit on exit.
    """

    def __init__(self, path: str, wal: bool = True):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        if wal:
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        logger.info(f"[DB] Opened {self.path}")

    # ------------------------------------------------------------------
    # Run lifecycle
    # ------------------------------------------------------------------

    def begin_run(
        self,
        condition: str,
        seed:      int,
        params:    Dict[str, Any],
    ) -> int:
        """Insert a run_meta row and return the new run_id."""
        cur = self._conn.execute(
            "INSERT INTO run_meta (condition, seed, params, start_ts) VALUES (?,?,?,?)",
            (condition, seed, json.dumps(params), time.time()),
        )
        self._conn.commit()
        run_id = cur.lastrowid
        logger.debug(f"[DB] begin_run run_id={run_id} condition={condition}")
        return run_id

    def end_run(self, run_id: int):
        self._conn.execute(
            "UPDATE run_meta SET end_ts=? WHERE run_id=?",
            (time.time(), run_id),
        )
        self._conn.commit()
        logger.debug(f"[DB] end_run run_id={run_id}")

    # ------------------------------------------------------------------
    # Tick / state / events
    # ------------------------------------------------------------------

    def write_tick(
        self,
        run_id:    int,
        timestamp: float,
        seed:      int,
    ) -> int:
        """Insert a ticks row and return the new tick_id."""
        cur = self._conn.execute(
            "INSERT INTO ticks (run_id, timestamp, seed) VALUES (?,?,?)",
            (run_id, timestamp, seed),
        )
        return cur.lastrowid

    def write_state(
        self,
        tick_id:         int,
        metabolic:       float,
        ISE:             float,
        epsilon:         float,
        gate_state:      bool,
        actuator_vector: Optional[np.ndarray] = None,
        proprioception:  Optional[np.ndarray] = None,
    ):
        av_blob = _encode_float32(actuator_vector) if actuator_vector is not None else None
        pr_blob = _encode_float32(proprioception)  if proprioception  is not None else None
        self._conn.execute(
            "INSERT INTO state VALUES (?,?,?,?,?,?,?)",
            (tick_id, metabolic, ISE, epsilon, int(gate_state), av_blob, pr_blob),
        )

    def write_event(
        self,
        tick_id: int,
        type_:   str,
        details: Optional[Dict] = None,
    ):
        self._conn.execute(
            "INSERT INTO events (tick_id, type, details) VALUES (?,?,?)",
            (tick_id, type_, json.dumps(details or {})),
        )

    def commit(self):
        self._conn.commit()

    # ------------------------------------------------------------------
    # Read helpers (for analysis)
    # ------------------------------------------------------------------

    def fetch_states(self, run_id: int) -> List[dict]:
        """Return all state rows for a run as a list of dicts."""
        rows = self._conn.execute(
            """
            SELECT t.tick_id, t.timestamp, s.metabolic, s.ISE, s.epsilon,
                   s.gate_state
            FROM   ticks t
            JOIN   state s USING (tick_id)
            WHERE  t.run_id = ?
            ORDER  BY t.tick_id
            """,
            (run_id,),
        ).fetchall()
        keys = ["tick_id", "timestamp", "metabolic", "ISE", "epsilon", "gate_state"]
        return [dict(zip(keys, r)) for r in rows]

    def fetch_events(self, run_id: int, type_: Optional[str] = None) -> List[dict]:
        if type_:
            rows = self._conn.execute(
                """
                SELECT e.event_id, e.tick_id, e.type, e.details
                FROM events e JOIN ticks t USING (tick_id)
                WHERE t.run_id=? AND e.type=?
                ORDER BY e.tick_id
                """,
                (run_id, type_),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT e.event_id, e.tick_id, e.type, e.details
                FROM events e JOIN ticks t USING (tick_id)
                WHERE t.run_id=?
                ORDER BY e.tick_id
                """,
                (run_id,),
            ).fetchall()
        keys = ["event_id", "tick_id", "type", "details"]
        return [dict(zip(keys, r)) for r in rows]

    def fetch_runs(self) -> List[dict]:
        rows = self._conn.execute(
            "SELECT run_id, condition, seed, params, start_ts, end_ts FROM run_meta"
        ).fetchall()
        keys = ["run_id", "condition", "seed", "params", "start_ts", "end_ts"]
        return [dict(zip(keys, r)) for r in rows]

    # ------------------------------------------------------------------

    def close(self):
        self._conn.commit()
        self._conn.close()
        logger.info(f"[DB] Closed {self.path}")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _encode_float32(arr: np.ndarray) -> bytes:
    return arr.astype(np.float32).tobytes()


def _decode_float32(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)
