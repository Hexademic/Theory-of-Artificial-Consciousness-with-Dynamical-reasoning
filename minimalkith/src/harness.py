"""
harness.py — Run harness for MinimalKith batch experiments.

Executes 60 randomized trials across three conditions:
    Baseline  (N=20): normal environment, full interoception
    Pressure  (N=20): pressure pulses injected, full interoception
    Ablation  (N=20): normal environment, interoception disconnected

All runs use deterministic seeds.  Seeds are drawn from a master RNG
seeded by the batch_seed in the config, ensuring cross-condition
reproducibility (same seed → same initial state, same noise stream).

Run command:
    python -m minimalkith.src.harness --config configs/config.yaml \
                                      --batch-id smoke_001
"""

from __future__ import annotations

import argparse
import itertools
import json
import logging
import math
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional

import numpy as np
import yaml

from .core import (
    Metabolic, ISE, RitualGate,
    PredictiveModel, Actuator, Proprioceptor,
)
from .environment import Environment, EnvironmentConfig
from .interoception import InteroceptiveLoop
from .persistence import Database

logger = logging.getLogger("MK.Harness")

TICK_RATE_HZ  = 50
COMMIT_EVERY  = 100   # flush DB every N ticks


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class HarnessConfig:
    f_tick:            int   = TICK_RATE_HZ
    run_duration_s:    float = 600.0        # 10 minutes per run
    n_per_condition:   int   = 20
    batch_seed:        int   = 0

    # Environment
    noise_std:         float = 0.10
    env_amplitude:     float = 1.0
    env_frequency:     float = 0.5

    # Pressure pulse (Pressure condition only)
    pulse_amplitude:   float = 2.0
    pulse_start_s:     float = 120.0
    pulse_end_s:       float = 180.0

    # Organism
    metabolic_capacity: float = 100.0
    metabolic_replenish: float = 0.5
    ise_decay:          float = 0.05
    ise_threshold:      float = 1.0
    refractory_ticks:   int   = 5

    # DB
    db_path:           str   = "data/runs/{batch_id}.db"

    @classmethod
    def from_yaml(cls, path: str) -> "HarnessConfig":
        with open(path) as f:
            d = yaml.safe_load(f) or {}
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Single run
# ---------------------------------------------------------------------------

def run_single(
    db:        Database,
    run_id:    int,
    config:    HarnessConfig,
    seed:      int,
    condition: str,
) -> Dict:
    """
    Execute one run and return summary metrics.

    condition ∈ {"Baseline", "Pressure", "Ablation"}
    """
    rng = np.random.default_rng(seed)

    # ── Build organism components ────────────────────────────────────────
    metabolic   = Metabolic(
        capacity=config.metabolic_capacity,
        replenish=config.metabolic_replenish,
    )
    ise         = ISE(decay=config.ise_decay, gate_threshold=config.ise_threshold,
                     dt=1.0 / config.f_tick)
    gate        = RitualGate(refractory_ticks=config.refractory_ticks)
    pred_model  = PredictiveModel(rng=rng)
    actuator    = Actuator()
    proprioceptor = Proprioceptor()

    loop = InteroceptiveLoop(pred_model, ise, gate, connected=True)

    if condition == "Ablation":
        loop.ablate()

    # ── Build environment ────────────────────────────────────────────────
    pulses = []
    if condition == "Pressure":
        pulse_start = int(config.pulse_start_s * config.f_tick)
        pulse_end   = int(config.pulse_end_s   * config.f_tick)
        pulses = [{"start_tick": pulse_start,
                   "end_tick":   pulse_end,
                   "amplitude":  config.pulse_amplitude}]

    env_cfg = EnvironmentConfig(
        amplitude=config.env_amplitude,
        frequency=config.env_frequency,
        noise_std=config.noise_std,
        pressure_pulses=pulses,
    )
    env = Environment(env_cfg, seed=seed)

    # ── Run loop ─────────────────────────────────────────────────────────
    n_ticks  = int(config.run_duration_s * config.f_tick)
    epsilon_history: List[float] = []
    gate_history:    List[bool]  = []
    ts0      = time.time()

    for t in range(n_ticks):
        ts = ts0 + t / config.f_tick

        # Environment step
        obs = env.step()

        # Interoceptive loop
        is_state = loop.tick(obs, t)

        # Actuator
        metabolic.replenish()
        cmd = actuator.command(ise, gate, metabolic, t)

        # Proprioception
        prop = proprioceptor.read(t, metabolic, ise, gate, actuator)

        # Persist
        tick_id = db.write_tick(run_id=run_id, timestamp=ts, seed=seed)
        db.write_state(
            tick_id=tick_id,
            metabolic=metabolic.normalised,
            ISE=ise.drive,
            epsilon=is_state.epsilon,
            gate_state=gate.state,
            actuator_vector=np.array([cmd.magnitude], dtype=np.float32),
            proprioception=np.array([
                prop.metabolic_norm,
                prop.drive,
                float(prop.gate_state),
                prop.last_magnitude,
            ], dtype=np.float32),
        )

        if is_state.gate_fired:
            db.write_event(tick_id, "GATE_FIRE", {
                "drive": ise.drive,
                "epsilon": is_state.epsilon,
            })
        if metabolic.depleted:
            db.write_event(tick_id, "METABOLIC_DEPLETION", {
                "budget": metabolic.state.budget,
            })

        epsilon_history.append(is_state.epsilon)
        gate_history.append(is_state.gate_fired)

        if (t + 1) % COMMIT_EVERY == 0:
            db.commit()

    db.commit()

    return {
        "run_id":     run_id,
        "condition":  condition,
        "seed":       seed,
        "gate_fires": gate.fire_count,
        "mean_eps":   float(np.mean(np.abs(epsilon_history))),
        "max_eps":    float(np.max(np.abs(epsilon_history))),
        "ticks":      n_ticks,
    }


# ---------------------------------------------------------------------------
# Batch runner
# ---------------------------------------------------------------------------

def run_batch(
    config:    HarnessConfig,
    batch_id:  str,
    db_path:   Optional[str] = None,
) -> List[Dict]:
    """
    Run all 60 trials (20 × 3 conditions) in randomised order.
    Returns list of per-run summary dicts.
    """
    db_path = db_path or config.db_path.format(batch_id=batch_id)
    db_path = str(Path(db_path))

    # Generate deterministic seeds for all runs
    master_rng = random.Random(config.batch_seed)
    seeds: Dict[str, List[int]] = {
        "Baseline": [master_rng.randint(0, 2**31) for _ in range(config.n_per_condition)],
        "Pressure": [master_rng.randint(0, 2**31) for _ in range(config.n_per_condition)],
        "Ablation": [master_rng.randint(0, 2**31) for _ in range(config.n_per_condition)],
    }

    # Interleave conditions to avoid systematic ordering bias
    run_plan = []
    for i in range(config.n_per_condition):
        for cond in ["Baseline", "Pressure", "Ablation"]:
            run_plan.append((cond, seeds[cond][i]))
    master_rng.shuffle(run_plan)

    summaries = []
    with Database(db_path) as db:
        for run_idx, (condition, seed) in enumerate(run_plan):
            params = {
                "f_tick": config.f_tick,
                "run_duration_s": config.run_duration_s,
                "noise_std": config.noise_std,
                "batch_id": batch_id,
                "run_index": run_idx,
            }
            run_id = db.begin_run(condition, seed, params)

            logger.info(
                f"[Harness] Run {run_idx+1}/{len(run_plan)} "
                f"condition={condition} seed={seed} run_id={run_id}"
            )

            summary = run_single(db, run_id, config, seed, condition)
            db.end_run(run_id)
            summaries.append(summary)

            logger.info(
                f"[Harness] Done run_id={run_id}: "
                f"gate_fires={summary['gate_fires']} mean_ε={summary['mean_eps']:.4f}"
            )

    return summaries


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _parse_args():
    p = argparse.ArgumentParser(description="MinimalKith run harness")
    p.add_argument("--config",   default="configs/config.yaml",
                   help="Path to config.yaml")
    p.add_argument("--batch-id", default=f"batch_{int(time.time())}",
                   help="Unique batch identifier")
    p.add_argument("--db-path",  default=None,
                   help="Override DB path from config")
    p.add_argument("--smoke",    action="store_true",
                   help="Run a 2-minute smoke test (1 run per condition)")
    return p.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    args = _parse_args()

    config = (
        HarnessConfig.from_yaml(args.config)
        if Path(args.config).exists()
        else HarnessConfig()
    )

    if args.smoke:
        config.run_duration_s  = 120.0
        config.n_per_condition = 1
        logger.info("[Harness] SMOKE MODE: 2-minute run × 1 per condition")

    summaries = run_batch(config, args.batch_id, db_path=args.db_path)

    print("\n=== BATCH SUMMARY ===")
    for s in summaries:
        print(
            f"  run_id={s['run_id']:>3} cond={s['condition']:<10} "
            f"seed={s['seed']:<12} fires={s['gate_fires']:>5} "
            f"mean_ε={s['mean_eps']:.4f}"
        )
    print(f"\nTotal runs: {len(summaries)}")
