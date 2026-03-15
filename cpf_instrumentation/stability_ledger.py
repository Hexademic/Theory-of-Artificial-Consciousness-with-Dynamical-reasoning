"""
stability_ledger.py — Append-only, cryptographically chained event log.

Each event is a JSON line with a SHA-256 hash that chains from the
previous entry, making any post-hoc modification detectable.

Usage:
    ledger = StabilityLedger("runs/ledger.jsonl")
    ledger.append_event(LedgerEvent.nominal(state, delta_H=0.12))

    # Verify integrity later
    ok, bad_line = ledger.verify()
    assert ok, f"Chain broken at line {bad_line}"

    # Iterate events
    for event in ledger.iter_events():
        print(event["event_type"], event["delta_H"])
"""

from __future__ import annotations

import json
import hashlib
import time
import logging
from pathlib import Path
from typing import Iterator, Optional, Tuple

from .core_types import LedgerEvent, PhenomenologicalState

logger = logging.getLogger("CPF.Ledger")

GENESIS_HASH = hashlib.sha256(b"CPF_GENESIS").hexdigest()


class StabilityLedger:
    """
    Append-only, cryptographically chained JSONL stability ledger.

    File format: one JSON object per line, each containing:
      timestamp, event_type, delta_H, invariances_tested, metadata,
      prev_hash, event_hash

    The hash chain is: event_hash = SHA-256(prev_hash ‖ serialised_payload).
    Tampering with any field of any line breaks all subsequent hashes.
    """

    def __init__(self, file_path: str, append: bool = True):
        self.path = Path(file_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # If not appending, start fresh
        if not append and self.path.exists():
            self.path.unlink()

        # Recover the chain tip from an existing file
        self.prev_hash = self._recover_tip()
        self._entry_count = self._count_lines()
        logger.info(
            f"[Ledger] Ready at {self.path} "
            f"(entries={self._entry_count}, tip={self.prev_hash[:16]}…)"
        )

    # ------------------------------------------------------------------
    # Append
    # ------------------------------------------------------------------

    def append_event(self, event: LedgerEvent) -> str:
        """
        Serialise and append one event.  Returns the new event_hash.
        Modifies event.prev_hash and event.event_hash in-place.
        """
        payload = self._build_payload(event)
        event_hash = self._hash(payload)
        payload["event_hash"] = event_hash

        # Mutate the event so the caller can inspect the hash
        event.prev_hash  = self.prev_hash
        event.event_hash = event_hash

        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, default=_json_default) + "\n")

        self.prev_hash = event_hash
        self._entry_count += 1
        return event_hash

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify(self) -> Tuple[bool, Optional[int]]:
        """
        Re-compute the entire chain.
        Returns (True, None) if intact, (False, line_number) at first break.
        Line numbers are 1-indexed.
        """
        prev = GENESIS_HASH
        for lineno, raw in enumerate(self._raw_lines(), start=1):
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                return False, lineno

            claimed_hash = entry.pop("event_hash", None)
            entry["prev_hash"] = prev    # use chain-reconstructed prev
            recomputed = self._hash(entry)
            if recomputed != claimed_hash:
                return False, lineno
            prev = claimed_hash
        return True, None

    # ------------------------------------------------------------------
    # Iteration
    # ------------------------------------------------------------------

    def iter_events(self) -> Iterator[dict]:
        """Yield each event as a dict (including event_hash)."""
        for raw in self._raw_lines():
            try:
                yield json.loads(raw)
            except json.JSONDecodeError:
                continue

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def entry_count(self) -> int:
        return self._entry_count

    @property
    def chain_tip(self) -> str:
        return self.prev_hash

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_payload(self, event: LedgerEvent) -> dict:
        state_dict = (
            event.phenomenological_state.as_dict()
            if event.phenomenological_state
            else None
        )
        return {
            "timestamp":          event.timestamp or time.time(),
            "event_type":         event.event_type,
            "delta_H":            event.delta_H,
            "invariances_tested": event.invariances_tested,
            "metadata":           event.metadata,
            "state":              state_dict,
            "prev_hash":          self.prev_hash,
        }

    @staticmethod
    def _hash(payload: dict) -> str:
        """Deterministic SHA-256 over sorted JSON serialisation."""
        raw = json.dumps(payload, sort_keys=True, default=_json_default)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _raw_lines(self) -> Iterator[str]:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield line

    def _recover_tip(self) -> str:
        tip = GENESIS_HASH
        for raw in self._raw_lines():
            try:
                entry = json.loads(raw)
                h = entry.get("event_hash", "")
                if h:
                    tip = h
            except json.JSONDecodeError:
                pass
        return tip

    def _count_lines(self) -> int:
        if not self.path.exists():
            return 0
        count = 0
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
        return count


def _json_default(obj):
    """Fallback JSON serialiser for torch.Tensor and numpy types."""
    try:
        import torch
        if isinstance(obj, torch.Tensor):
            return obj.tolist()
    except ImportError:
        pass
    try:
        import numpy as np
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
    except ImportError:
        pass
    return str(obj)
