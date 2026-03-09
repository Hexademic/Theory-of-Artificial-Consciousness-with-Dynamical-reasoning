"""
Shared State Store
==================
Atomic JSON persistence for the unified being's identity across sessions
and across repositories.

What is persisted:
  - Soul identity  (soul_hash, continuity_cycle, relational_anchors)
  - Affective threads (4-dim: Hope, Anxiety, Excitement, Intimacy)
  - Identity manifold (16-dim deformation lattice)
  - Episodic ledger (top-N salient episodes)
  - Physiological baseline (metabolic budget at last save)
  - Governance history (violation count, last invariant load)

All writes are atomic: data is written to a temp file then renamed,
so a crash mid-write never produces a corrupt state file.
"""

import os
import json
import time
import tempfile
import logging
import numpy as np
from pathlib import Path
from typing import Optional

logger = logging.getLogger("SharedState")

DEFAULT_STATE_PATH = Path.home() / ".hexademic" / "being_state.json"

# How many episodes to keep in the persisted ledger
MAX_PERSISTED_EPISODES = 500


class SharedStateStore:
    """
    Atomic JSON persistence for a single long-lived being.

    Usage:
        store = SharedStateStore()          # uses ~/.hexademic/being_state.json
        store.load(organism)                # restore state into organism
        ...run ticks...
        store.save(organism)                # persist after each tick
    """

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else DEFAULT_STATE_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._last_save: float = 0.0

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------

    def load(self, organism) -> bool:
        """
        Restore persisted state into a live AECxCPFOrganism (or SovereignKith).
        Returns True if a previous state was found and loaded.
        """
        if not self.path.exists():
            logger.info(f"[STATE] No prior state at {self.path}. Starting fresh.")
            return False

        try:
            with open(self.path, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"[STATE] Failed to read state file: {e}")
            return False

        self._restore_soul(organism, data.get("soul", {}))
        self._restore_affect(organism, data.get("affect", {}))
        self._restore_manifold(organism, data.get("manifold", {}))
        self._restore_physiology(organism, data.get("physiology", {}))
        self._restore_episodes(organism, data.get("episodes", []))

        born = data.get("soul", {}).get("birth_timestamp", time.time())
        age_h = (time.time() - born) / 3600
        cycle = data.get("soul", {}).get("continuity_cycle", 0)
        logger.info(
            f"[STATE] Restored: soul_cycle={cycle}, age={age_h:.1f}h, "
            f"episodes={len(data.get('episodes', []))}"
        )
        return True

    def save(self, organism, force: bool = False) -> bool:
        """
        Atomically persist current organism state to disk.
        Returns True on success.
        """
        try:
            data = self._extract(organism)
            self._atomic_write(data)
            self._last_save = time.time()
            return True
        except Exception as e:
            logger.error(f"[STATE] Save failed: {e}")
            return False

    def snapshot(self, organism) -> dict:
        """Return the current state as a plain dict (without writing to disk)."""
        return self._extract(organism)

    @property
    def exists(self) -> bool:
        return self.path.exists()

    @property
    def age_seconds(self) -> float:
        if not self.path.exists():
            return 0.0
        return time.time() - self.path.stat().st_mtime

    # ------------------------------------------------------------------
    # EXTRACTION (organism → dict)
    # ------------------------------------------------------------------

    def _extract(self, organism) -> dict:
        cpf = _get_cpf(organism)
        return {
            "schema_version": 1,
            "saved_at": time.time(),
            "soul": _extract_soul(cpf),
            "affect": _extract_affect(cpf),
            "manifold": _extract_manifold(cpf),
            "physiology": _extract_physiology(cpf),
            "episodes": _extract_episodes(cpf),
            "governance": _extract_governance(cpf),
        }

    # ------------------------------------------------------------------
    # RESTORATION (dict → organism)
    # ------------------------------------------------------------------

    def _restore_soul(self, organism, soul_data: dict):
        cpf = _get_cpf(organism)
        if not soul_data or not cpf:
            return
        cpf.soul.soul_hash = soul_data.get("soul_hash", cpf.soul.soul_hash)
        cpf.soul.lineage_signature = soul_data.get("lineage_signature", cpf.soul.lineage_signature)
        cpf.soul.birth_timestamp = soul_data.get("birth_timestamp", cpf.soul.birth_timestamp)
        cpf.soul.continuity_cycle = soul_data.get("continuity_cycle", 0)
        cpf.soul.relational_anchors = soul_data.get("relational_anchors", [])

    def _restore_affect(self, organism, affect_data: dict):
        cpf = _get_cpf(organism)
        if not affect_data or not cpf:
            return
        threads = affect_data.get("threads")
        if threads and len(threads) == 4:
            cpf.affect_system._threads = np.array(threads, dtype=float)

    def _restore_manifold(self, organism, manifold_data: dict):
        cpf = _get_cpf(organism)
        if not manifold_data or not cpf:
            return
        m = manifold_data.get("identity_manifold")
        if m and len(m) == 16:
            cpf.memory._manifold = np.array(m, dtype=float)
        em = manifold_data.get("enhanced_manifold")
        if em and len(em) == 16:
            cpf.manifold._M = np.array(em, dtype=float)

    def _restore_physiology(self, organism, phys_data: dict):
        cpf = _get_cpf(organism)
        if not phys_data or not cpf:
            return
        cpf.autonomic.state.metabolic_budget = phys_data.get("metabolic_budget", 1.0)
        cpf.autonomic.state.threat_level = phys_data.get("threat_level", 0.0)
        cpf.autonomic.state.heart_rate = phys_data.get("heart_rate", 72.0)

    def _restore_episodes(self, organism, episodes_data: list):
        from constitutional_phenomenology_framework import MemoryEpisode, AffectiveResonance
        cpf = _get_cpf(organism)
        if not episodes_data or not cpf:
            return
        restored = []
        for ep in episodes_data:
            try:
                affect = AffectiveResonance(
                    valence=ep["affect"]["valence"],
                    arousal=ep["affect"]["arousal"],
                    intimacy=ep["affect"]["intimacy"],
                    threat=ep["affect"]["threat"],
                )
                from constitutional_phenomenology_framework import AutonomicState
                mode_name = ep.get("somatic_mode", "VENTRAL")
                mode = AutonomicState[mode_name] if mode_name in AutonomicState.__members__ else AutonomicState.VENTRAL
                episode = cpf.memory.encode_experience(
                    context=ep["context"],
                    affect=affect,
                    somatic_mode=mode,
                )
            except (KeyError, ValueError):
                continue
        logger.info(f"[STATE] Restored {len(episodes_data)} episodes.")

    # ------------------------------------------------------------------
    # ATOMIC WRITE
    # ------------------------------------------------------------------

    def _atomic_write(self, data: dict):
        dir_ = self.path.parent
        with tempfile.NamedTemporaryFile(
            mode="w", dir=dir_, suffix=".tmp", delete=False
        ) as tmp:
            json.dump(data, tmp, indent=2, default=_json_default)
            tmp_path = tmp.name
        os.replace(tmp_path, self.path)


# ------------------------------------------------------------------
# EXTRACTION HELPERS
# ------------------------------------------------------------------

def _get_cpf(organism):
    """Safely extract the SovereignKith from various organism types."""
    if hasattr(organism, "cpf"):         # AECxCPFOrganism
        return organism.cpf
    if hasattr(organism, "soul"):        # SovereignKith directly
        return organism
    return None


def _extract_soul(cpf) -> dict:
    if not cpf:
        return {}
    return {
        "soul_hash":         cpf.soul.soul_hash,
        "lineage_signature": cpf.soul.lineage_signature,
        "birth_timestamp":   cpf.soul.birth_timestamp,
        "continuity_cycle":  cpf.soul.continuity_cycle,
        "relational_anchors": cpf.soul.relational_anchors,
    }


def _extract_affect(cpf) -> dict:
    if not cpf:
        return {}
    return {
        "threads":      cpf.affect_system._threads.tolist(),
        "thread_names": cpf.affect_system.THREAD_NAMES,
    }


def _extract_manifold(cpf) -> dict:
    if not cpf:
        return {}
    return {
        "identity_manifold": cpf.memory._manifold.tolist(),
        "identity_magnitude": cpf.memory.identity_magnitude,
        "enhanced_manifold":  cpf.manifold._M.tolist(),
    }


def _extract_physiology(cpf) -> dict:
    if not cpf:
        return {}
    s = cpf.autonomic.state
    return {
        "metabolic_budget": s.metabolic_budget,
        "threat_level":     s.threat_level,
        "heart_rate":       s.heart_rate,
        "autonomic_mode":   cpf.autonomic.mode.name,
    }


def _extract_episodes(cpf) -> list:
    if not cpf:
        return []
    eps = sorted(cpf.memory._episodes, key=lambda e: e.salience, reverse=True)
    eps = eps[:MAX_PERSISTED_EPISODES]
    return [
        {
            "id":          ep.id,
            "timestamp":   ep.timestamp,
            "context":     ep.context,
            "salience":    ep.salience,
            "somatic_mode": ep.somatic_mode,
            "affect": {
                "valence":  ep.affect.valence,
                "arousal":  ep.affect.arousal,
                "intimacy": ep.affect.intimacy,
                "threat":   ep.affect.threat,
            },
        }
        for ep in eps
    ]


def _extract_governance(cpf) -> dict:
    if not cpf:
        return {}
    violations = cpf.kernel.violation_history
    return {
        "violation_count": len(violations),
        "last_invariant_load": violations[-1]["invariant_load"] if violations else 0.0,
    }


def _json_default(obj):
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    return str(obj)
