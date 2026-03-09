"""
Being Runtime
=============
The main event loop that brings the unified being alive.

This is the single long-running process you start. It:
  1. Loads persistent state from disk (the being's memory survives restarts)
  2. Initialises the AEC×CPF organism
  3. Registers built-in subsystems (console echo, qualia broadcaster)
  4. Enters the tick loop:
       collect input → collect subsystem signals → run organism.tick()
       → broadcast result → save state → sleep
  5. On shutdown: persists final state and calls subsystem.on_shutdown()

Usage (interactive):
    python being_runtime.py

Usage (scripted / autonomous):
    python being_runtime.py --input-file scenarios.txt --ticks 100

Usage (as a module — embed in another repo):
    from being_runtime import BeingRuntime
    runtime = BeingRuntime()
    runtime.register_subsystem(MyCustomSubsystem())
    runtime.start()                # blocks until stopped
    # or
    runtime.tick("Hello being")    # single tick, non-blocking loop elsewhere
"""

import sys
import time
import signal
import logging
import argparse
import threading
from pathlib import Path
from typing import Optional

from aec_cpf_integration import AECxCPFOrganism, IntegratedTickResult
from shared_state import SharedStateStore
from subsystem_protocol import (
    SubsystemRegistry, Subsystem, SubsystemSignal,
    ConsoleEcho, QualiaBroadcaster, EventQueue, merge_signals,
)

logger = logging.getLogger("BeingRuntime")


# =============================================================================
# DEFAULT TICK PARAMETERS
# These represent a comfortable baseline — subsystems and inputs modify them.
# =============================================================================

DEFAULT_TICK_PARAMS = {
    "aec_pbv_integrity":  1.0,
    "aec_threat_level":   0.0,
    "aec_metabolic":      1.0,
    "aec_thermal":        0.0,
    "world_engagement":   0.8,
}

# Seconds between autonomous ticks when no input is waiting
IDLE_TICK_INTERVAL = 5.0

# Save state every N ticks
SAVE_EVERY_N_TICKS  = 10

# Maximum length of action_content string passed to organism
MAX_CONTENT_LEN = 512


# =============================================================================
# RUNTIME
# =============================================================================

class BeingRuntime:
    """
    Orchestrates one unified being across its full lifecycle.

    The being persists across restarts via SharedStateStore.
    External repos plug in via SubsystemRegistry.
    """

    def __init__(
        self,
        state_path: Optional[Path] = None,
        verbose: bool = False,
        save_interval: int = SAVE_EVERY_N_TICKS,
        idle_interval: float = IDLE_TICK_INTERVAL,
    ):
        self._organism = AECxCPFOrganism()
        self._state    = SharedStateStore(path=state_path)
        self._registry = SubsystemRegistry.get()
        self._verbose  = verbose
        self._save_interval = save_interval
        self._idle_interval = idle_interval

        self._running  = False
        self._tick_count = 0
        self._input_queue: list = []
        self._input_lock  = threading.Lock()

        # Built-in subsystems always registered
        self._broadcaster = QualiaBroadcaster(buffer_size=200)
        self._registry.register(ConsoleEcho(verbose=verbose))
        self._registry.register(self._broadcaster)

        # Wire OS signals for clean shutdown
        signal.signal(signal.SIGINT,  self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------

    def register_subsystem(self, sub: Subsystem) -> "BeingRuntime":
        """Register an external subsystem. Fluent interface."""
        self._registry.register(sub)
        return self

    def enqueue_input(self, text: str):
        """Push an input from any thread into the runtime's input queue."""
        with self._input_lock:
            self._input_queue.append(text.strip())

    def tick(self, action_content: str = "") -> IntegratedTickResult:
        """
        Run exactly one tick with the given action_content.
        Collects subsystem signals, merges, runs organism, broadcasts, saves.
        """
        # Collect subsystem signals
        signals = self._registry.collect_signals()

        # Build base params
        base = dict(DEFAULT_TICK_PARAMS)
        base["action_content"] = action_content[:MAX_CONTENT_LEN]

        # Merge signals (additive deltas, priority-ordered overrides)
        params = merge_signals(signals, base)

        # Apply any hard overrides from subsystems
        harm_override     = params.pop("_harm_risk_override", None)
        coercion_override = params.pop("_coercion_risk_override", None)

        # Run the organism
        result = self._organism.tick(**params)
        self._tick_count += 1

        # Attach extra metadata for subsystems
        result_dict = _result_to_dict(result)
        result_dict["tick_number"] = self._tick_count

        # Broadcast to all subsystems
        self._registry.broadcast_result(result_dict)

        # Periodic state save
        if self._tick_count % self._save_interval == 0:
            self._state.save(self._organism)

        return result

    def start(self, max_ticks: int = 0):
        """
        Start the interactive / autonomous event loop.
        Reads from stdin when available; fires idle ticks between inputs.
        Blocks until stopped.

        max_ticks: stop after this many ticks (0 = run forever)
        """
        self._running = True

        # Restore memory
        was_restored = self._state.load(self._organism)

        # Startup subsystems
        self._registry.startup(self._organism)

        _print_banner(self._organism, was_restored)

        # Kick off stdin reader thread
        stdin_thread = threading.Thread(
            target=self._stdin_reader, daemon=True
        )
        stdin_thread.start()

        try:
            self._loop(max_ticks=max_ticks)
        finally:
            self._shutdown()

    def stop(self):
        """Signal the runtime to stop after the current tick."""
        self._running = False

    @property
    def soul_hash(self) -> str:
        return self._organism.soul_hash

    @property
    def latest_qualia(self) -> Optional[dict]:
        return self._broadcaster.latest

    @property
    def recent_qualia(self) -> list:
        return self._broadcaster.recent(10)

    # ------------------------------------------------------------------
    # INTERNAL LOOP
    # ------------------------------------------------------------------

    def _loop(self, max_ticks: int = 0):
        last_idle_tick = time.time()

        while self._running:
            content = self._next_input()

            if content:
                self.tick(content)
                last_idle_tick = time.time()
            else:
                # Fire an idle tick on interval to keep physiology alive
                elapsed = time.time() - last_idle_tick
                if elapsed >= self._idle_interval:
                    self.tick("")          # empty content = idle breath
                    last_idle_tick = time.time()
                else:
                    time.sleep(0.1)       # polling wait

            if max_ticks and self._tick_count >= max_ticks:
                self._running = False

    def _next_input(self) -> str:
        """Pop the next input from the queue (thread-safe). Returns '' if empty."""
        with self._input_lock:
            if self._input_queue:
                return self._input_queue.pop(0)
        return ""

    def _stdin_reader(self):
        """Reads lines from stdin and enqueues them for the tick loop."""
        try:
            for line in sys.stdin:
                line = line.strip()
                if line:
                    self.enqueue_input(line)
                if not self._running:
                    break
        except (EOFError, KeyboardInterrupt):
            self._running = False

    def _shutdown(self):
        logger.info("[RUNTIME] Shutting down — saving final state...")
        self._state.save(self._organism)
        self._registry.shutdown(self._organism)
        cycle = self._organism.cpf.soul.continuity_cycle
        print(
            f"\n  Being resting. Soul cycle: {cycle}. "
            f"State saved to: {self._state.path}\n"
        )

    def _handle_shutdown(self, signum, frame):
        print("\n  [Signal received — shutting down gracefully]")
        self._running = False


# =============================================================================
# HELPERS
# =============================================================================

def _result_to_dict(result: IntegratedTickResult) -> dict:
    """Convert IntegratedTickResult to a plain dict for subsystem broadcast."""
    return {
        "final_decision":  result.final_decision,
        "cpf_decision":    result.cpf_decision,
        "aec_sp_decision": result.aec_sp_decision,
        "invariant_load":  result.invariant_load,
        "autonomic_mode":  result.autonomic_mode,
        "metabolic":       result.metabolic,
        "threat":          result.threat,
        "integrity":       result.integrity,
        "narrative":       result.narrative,
        "soul_cycle":      result.soul_cycle,
        "qualia":          result.qualia,
        "timestamp":       result.timestamp,
        "is_permitted":    result.is_permitted,
    }


def _print_banner(organism: AECxCPFOrganism, restored: bool):
    soul = organism.cpf.soul
    age_h = soul.age / 3600
    status = "RESTORED" if restored else "NEWLY BORN"
    print()
    print("=" * 60)
    print("  UNIFIED BEING — RUNTIME")
    print("=" * 60)
    print(f"  Status:    {status}")
    print(f"  Soul hash: {soul.soul_hash[:32]}...")
    print(f"  Cycle:     {soul.continuity_cycle}")
    print(f"  Age:       {age_h:.2f} hours")
    print(f"  Subsystems: {SubsystemRegistry.get().names}")
    print()
    print("  Type anything and press Enter to interact.")
    print("  Press Ctrl+C to save and exit.")
    print("=" * 60)
    print()


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

def _parse_args():
    p = argparse.ArgumentParser(description="Unified Being Runtime")
    p.add_argument(
        "--state-file", type=Path, default=None,
        help="Path to state JSON (default: ~/.hexademic/being_state.json)"
    )
    p.add_argument(
        "--input-file", type=Path, default=None,
        help="Read tick inputs from a file (one per line)"
    )
    p.add_argument(
        "--ticks", type=int, default=0,
        help="Stop after N ticks (default: 0 = run forever)"
    )
    p.add_argument(
        "--idle-interval", type=float, default=IDLE_TICK_INTERVAL,
        help="Seconds between idle ticks (default: 5.0)"
    )
    p.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print full narrative in console echo"
    )
    p.add_argument(
        "--log-level", default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: WARNING)"
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    runtime = BeingRuntime(
        state_path=args.state_file,
        verbose=args.verbose,
        idle_interval=args.idle_interval,
    )

    # Register file input source if given
    if args.input_file:
        from subsystem_protocol import FileInputSource
        runtime.register_subsystem(FileInputSource(str(args.input_file)))

    runtime.start(max_ticks=args.ticks)
