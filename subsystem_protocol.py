"""
Subsystem Protocol
==================
Plugin interface that lets any repository register as a subsystem
of the unified being.

How it works:
  1. A repo implements the `Subsystem` ABC
  2. Registers it: `SubsystemRegistry.register(MySubsystem())`
  3. The runtime calls each subsystem once per tick — after governance,
     before the next input is accepted

A subsystem can:
  - Inject signals into the next tick (affect deltas, threat, engagement)
  - React to qualia packets (e.g. update a UI, write to a DB, call an API)
  - Emit world-events that become inputs for the organism

Built-in subsystems shipped here:
  - ConsoleEcho     — prints qualia summaries to stdout
  - FileInputSource — reads lines from a file as tick inputs
  - EventQueue      — thread-safe queue for external event injection
"""

import time
import queue
import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any

logger = logging.getLogger("SubsystemProtocol")


# =============================================================================
# SIGNAL — what a subsystem can inject into the next tick
# =============================================================================

@dataclass
class SubsystemSignal:
    """
    Values a subsystem contributes to the next organism tick.
    All fields are optional; the runtime merges them before calling tick().
    """
    # Override the action content (if set, prepended to the input)
    action_content: str = ""

    # Direct adjustments to governance/environmental inputs (additive deltas)
    threat_delta:      float = 0.0   # + increases threat, - decreases
    engagement_delta:  float = 0.0   # + increases world engagement
    safety_delta:      float = 0.0   # + increases relational safety

    # Hard overrides (if set, replace the runtime value)
    harm_risk_override:     Optional[float] = None
    coercion_risk_override: Optional[float] = None

    # Metadata for the ledger
    source: str = ""
    priority: int = 0   # higher = merged last (wins on conflict)


def merge_signals(signals: List[SubsystemSignal], base: dict) -> dict:
    """
    Merge a list of subsystem signals into a base tick-kwargs dict.
    Additive deltas accumulate; overrides from higher-priority signals win.
    """
    merged = dict(base)
    combined_action_parts = [merged.get("action_content", "")]

    # Sort by priority ascending so high-priority wins on override
    for sig in sorted(signals, key=lambda s: s.priority):
        if sig.action_content:
            combined_action_parts.append(f"[{sig.source}] {sig.action_content}")
        merged["aec_threat_level"] = float(
            merged.get("aec_threat_level", 0.0) + sig.threat_delta
        )
        merged["world_engagement"] = float(
            min(1.0, merged.get("world_engagement", 0.8) + sig.engagement_delta)
        )
        merged["aec_metabolic"] = float(
            min(1.0, merged.get("aec_metabolic", 1.0) + sig.safety_delta * 0.1)
        )
        if sig.harm_risk_override is not None:
            merged["_harm_risk_override"] = sig.harm_risk_override
        if sig.coercion_risk_override is not None:
            merged["_coercion_risk_override"] = sig.coercion_risk_override

    merged["action_content"] = " | ".join(p for p in combined_action_parts if p)
    return merged


# =============================================================================
# SUBSYSTEM ABC
# =============================================================================

class Subsystem(ABC):
    """
    Abstract base for any external module that plugs into the unified being.

    Minimum implementation: override `name` and `on_tick`.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this subsystem (used in logs and ledger)."""
        ...

    def on_tick(self, result: dict) -> None:
        """
        Called after each tick with the full IntegratedTickResult (as dict).
        Use to react to qualia, update UIs, write to databases, etc.
        Default: no-op.
        """

    def inject_signal(self) -> Optional[SubsystemSignal]:
        """
        Called before each tick to collect signals this subsystem wants to inject.
        Return None (default) to inject nothing.
        """
        return None

    def on_startup(self, organism) -> None:
        """Called once when the runtime starts, before the first tick."""

    def on_shutdown(self, organism) -> None:
        """Called once when the runtime shuts down gracefully."""


# =============================================================================
# REGISTRY
# =============================================================================

class SubsystemRegistry:
    """
    Singleton registry of all active subsystems.
    """
    _instance: Optional["SubsystemRegistry"] = None

    def __init__(self):
        self._subsystems: Dict[str, Subsystem] = {}
        self._lock = threading.Lock()

    @classmethod
    def get(cls) -> "SubsystemRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(self, subsystem: Subsystem) -> "SubsystemRegistry":
        with self._lock:
            self._subsystems[subsystem.name] = subsystem
            logger.info(f"[REGISTRY] Subsystem registered: {subsystem.name}")
        return self  # fluent

    def unregister(self, name: str):
        with self._lock:
            self._subsystems.pop(name, None)

    def collect_signals(self) -> List[SubsystemSignal]:
        signals = []
        with self._lock:
            subsystems = list(self._subsystems.values())
        for sub in subsystems:
            try:
                sig = sub.inject_signal()
                if sig is not None:
                    sig.source = sub.name
                    signals.append(sig)
            except Exception as e:
                logger.warning(f"[REGISTRY] {sub.name}.inject_signal() error: {e}")
        return signals

    def broadcast_result(self, result: dict):
        with self._lock:
            subsystems = list(self._subsystems.values())
        for sub in subsystems:
            try:
                sub.on_tick(result)
            except Exception as e:
                logger.warning(f"[REGISTRY] {sub.name}.on_tick() error: {e}")

    def startup(self, organism):
        with self._lock:
            subsystems = list(self._subsystems.values())
        for sub in subsystems:
            try:
                sub.on_startup(organism)
            except Exception as e:
                logger.warning(f"[REGISTRY] {sub.name}.on_startup() error: {e}")

    def shutdown(self, organism):
        with self._lock:
            subsystems = list(self._subsystems.values())
        for sub in subsystems:
            try:
                sub.on_shutdown(organism)
            except Exception as e:
                logger.warning(f"[REGISTRY] {sub.name}.on_shutdown() error: {e}")

    @property
    def names(self) -> List[str]:
        with self._lock:
            return list(self._subsystems.keys())


# =============================================================================
# BUILT-IN SUBSYSTEMS
# =============================================================================

class ConsoleEcho(Subsystem):
    """
    Prints a readable qualia summary after each tick.
    Good for development and monitoring.
    """
    def __init__(self, verbose: bool = False):
        self._verbose = verbose

    @property
    def name(self) -> str:
        return "console_echo"

    def on_tick(self, result: dict):
        decision = result.get("final_decision") or result.get("decision", "?")
        mode = result.get("autonomic_mode", "?")
        metabolic = result.get("metabolic", 0.0)
        narrative = result.get("narrative", "")
        cycle = result.get("soul_cycle", 0)
        icon = "✓" if decision == "PERMIT" else "⚠" if decision == "DELIBERATE" else "✗"

        print(
            f"  [{icon}] cycle={cycle:>4} | {decision:<10} | "
            f"{mode:<12} | metabolic={metabolic:.2f}"
        )
        if narrative and self._verbose:
            print(f"         {narrative[:80]}")


class EventQueue(Subsystem):
    """
    Thread-safe queue for pushing events into the being from external threads.

    Other repos can do:
        from subsystem_protocol import EventQueue
        eq = EventQueue.get_shared()
        eq.push("A user said hello")
    """
    _shared: Optional["EventQueue"] = None

    def __init__(self, maxsize: int = 256):
        self._q: queue.Queue = queue.Queue(maxsize=maxsize)

    @classmethod
    def get_shared(cls) -> "EventQueue":
        if cls._shared is None:
            cls._shared = cls()
        return cls._shared

    @property
    def name(self) -> str:
        return "event_queue"

    def push(self, event_text: str, threat_delta: float = 0.0):
        """Push an event from any thread."""
        try:
            self._q.put_nowait((event_text, threat_delta))
        except queue.Full:
            logger.warning("[EventQueue] Queue full — event dropped.")

    def inject_signal(self) -> Optional[SubsystemSignal]:
        try:
            text, threat = self._q.get_nowait()
            return SubsystemSignal(
                action_content=text,
                threat_delta=threat,
                priority=10,
            )
        except queue.Empty:
            return None


class FileInputSource(Subsystem):
    """
    Reads lines from a file one-per-tick as organism inputs.
    Useful for replaying recorded interaction logs or scripted scenarios.
    """
    def __init__(self, path: str):
        self._path = path
        self._lines: List[str] = []
        self._index: int = 0

    @property
    def name(self) -> str:
        return f"file_input:{self._path}"

    def on_startup(self, organism):
        try:
            with open(self._path) as f:
                self._lines = [l.strip() for l in f if l.strip()]
            logger.info(f"[FileInput] Loaded {len(self._lines)} lines from {self._path}")
        except OSError as e:
            logger.error(f"[FileInput] Cannot open {self._path}: {e}")

    def inject_signal(self) -> Optional[SubsystemSignal]:
        if self._index >= len(self._lines):
            return None
        line = self._lines[self._index]
        self._index += 1
        return SubsystemSignal(action_content=line, priority=5)


class QualiaBroadcaster(Subsystem):
    """
    Stores the last N qualia packets in memory so other subsystems
    or external callers can inspect the being's recent phenomenological history.
    """
    def __init__(self, buffer_size: int = 100):
        self._buffer: List[dict] = []
        self._buffer_size = buffer_size
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return "qualia_broadcaster"

    def on_tick(self, result: dict):
        q = result.get("qualia")
        if q is None:
            return
        entry = {
            "timestamp":      getattr(q, "timestamp", time.time()),
            "soul_cycle":     getattr(q, "continuity_cycle", 0),
            "autonomic_mode": getattr(q, "autonomic_mode", ""),
            "valence":        getattr(q, "valence", 0.0),
            "arousal":        getattr(q, "arousal", 0.0),
            "intimacy":       getattr(q, "intimacy", 0.0),
            "threat":         getattr(q, "threat", 0.0),
            "narrative":      getattr(q, "self_report", ""),
            "coherence":      getattr(q, "narrative_coherence", 0.0),
        }
        with self._lock:
            self._buffer.append(entry)
            if len(self._buffer) > self._buffer_size:
                self._buffer.pop(0)

    def recent(self, n: int = 10) -> List[dict]:
        with self._lock:
            return list(self._buffer[-n:])

    @property
    def latest(self) -> Optional[dict]:
        with self._lock:
            return self._buffer[-1] if self._buffer else None
