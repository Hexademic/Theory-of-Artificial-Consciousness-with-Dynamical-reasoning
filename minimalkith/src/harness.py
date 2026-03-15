"""
harness.py — Run harness for MinimalKith batch experiments.

Standard batch
--------------
Executes 60 randomised trials across three conditions:
    Baseline  (N=20): normal environment, full interoception
    Pressure  (N=20): pressure pulses injected, full interoception
    Ablation  (N=20): normal environment, interoception disconnected

Calibration / paired batch
--------------------------
Adds counterfactual pairs: each pair shares the same external-environment
seed (identical noise stream) but uses different internal-history seeds
(different PredictiveModel priors).  This lets us measure behavioural
divergence D that arises purely from internal history, not from external
differences.

    Paired runs: Npairs × 2 (default Npairs=10 for calibration)
    Controls:    Baseline N_ctrl + Ablation N_ctrl (default 10 each)

Run commands:
    # Standard batch
    python -m minimalkith.src.harness --config configs/config.yaml \
                                      --batch-id smoke_001
    # Calibration paired batch
    python -m minimalkith.src.harness --config configs/config.yaml \
                                      --batch-id calib_001 --paired \
                                      --n-pairs 10
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
from .consolidation import SlowWeightChannel, DualTimescalePredictor

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

    # Consolidation (dual-timescale learning) — OFF by default
    # Set consolidation_enabled=True to activate the slow-weight channel.
    # See consolidation.py for full parameter documentation.
    consolidation_enabled:        bool  = False
    consolidation_eta_slow:       float = 0.005   # slow learning rate
    consolidation_threshold:      float = 10.0    # cumulative surprise to trigger
    consolidation_surprise_leak:  float = 0.02    # leaky integrator decay
    consolidation_buffer_capacity: int  = 200     # episodic buffer size
    consolidation_alpha:          float = 0.7     # fast/slow blend (α·fast + (1-α)·slow)

    @classmethod
    def from_yaml(cls, path: str) -> "HarnessConfig":
        with open(path) as f:
            d = yaml.safe_load(f) or {}
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class PairedBatchConfig:
    """
    Configuration for the calibration paired-run batch.

    Each pair shares an *external* seed (identical env noise stream) but
    receives different *internal* seeds (PredictiveModel priors diverge from
    tick 0).  This isolates behavioural divergence D that arises from internal
    history alone.
    """
    n_pairs:             int   = 10     # calibration default; scale to 40 for full batch
    n_baseline_controls: int   = 10
    n_ablation_controls: int   = 10
    precondition_ticks:  int   = 0      # extra warm-up ticks (same ext seed, diff int seed)
                                        # 0 = no preconditioning phase; divergence starts at t=0


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

    if config.consolidation_enabled:
        slow_ch    = SlowWeightChannel(
            eta_slow=config.consolidation_eta_slow,
            consolidation_threshold=config.consolidation_threshold,
            surprise_leak=config.consolidation_surprise_leak,
            buffer_capacity=config.consolidation_buffer_capacity,
        )
        pred_model = DualTimescalePredictor(
            rng=rng, alpha=config.consolidation_alpha, slow_channel=slow_ch,
        )
    else:
        pred_model = PredictiveModel(rng=rng)
        slow_ch    = None

    actuator      = Actuator()
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

        # Slow-weight consolidation tick (no-op if disabled)
        if slow_ch is not None:
            consol = pred_model.tick_slow(
                tick_id=t,
                epsilon=is_state.epsilon,
                ise_drive=ise.drive,
                metabolic=metabolic.normalised,
            )
            if consol is not None:
                db.write_event(tick_id, "CONSOLIDATION", {
                    "index":     consol.index,
                    "delta_slow": consol.delta_slow,
                    "mu_slow":   pred_model.mu_slow,
                })

        epsilon_history.append(is_state.epsilon)
        gate_history.append(is_state.gate_fired)

        if (t + 1) % COMMIT_EVERY == 0:
            db.commit()

    db.commit()

    n_consol = slow_ch.n_consolidations if slow_ch is not None else 0
    return {
        "run_id":          run_id,
        "condition":       condition,
        "seed":            seed,
        "gate_fires":      gate.fire_count,
        "mean_eps":        float(np.mean(np.abs(epsilon_history))),
        "max_eps":         float(np.max(np.abs(epsilon_history))),
        "ticks":           n_ticks,
        "n_consolidations": n_consol,
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
# Paired-run support (counterfactual divergence)
# ---------------------------------------------------------------------------

def run_single_split_seed(
    db:           Database,
    run_id:       int,
    config:       HarnessConfig,
    seed_ext:     int,       # env RNG seed  — shared across pair members
    seed_int:     int,       # organism RNG seed — differs across pair members
    condition:    str,
    precondition_ticks: int = 0,
) -> Dict:
    """
    Like run_single() but with separate external and internal seeds.

    seed_ext controls the environment noise stream.
    seed_int controls the PredictiveModel's internal random state.

    Both pair members get the same seed_ext → identical observations.
    Each pair member gets a different seed_int → diverging internal history.

    precondition_ticks — if >0, run this many ticks with seed_int before the
    recorded run starts.  The env is reset to seed_ext afterwards so the
    recorded observations are still identical between pair members.
    """
    int_rng = np.random.default_rng(seed_int)

    # ── Build organism components ────────────────────────────────────────
    metabolic     = Metabolic(
        capacity=config.metabolic_capacity,
        replenish=config.metabolic_replenish,
    )
    ise           = ISE(decay=config.ise_decay, gate_threshold=config.ise_threshold,
                       dt=1.0 / config.f_tick)
    gate          = RitualGate(refractory_ticks=config.refractory_ticks)

    if config.consolidation_enabled:
        slow_ch    = SlowWeightChannel(
            eta_slow=config.consolidation_eta_slow,
            consolidation_threshold=config.consolidation_threshold,
            surprise_leak=config.consolidation_surprise_leak,
            buffer_capacity=config.consolidation_buffer_capacity,
        )
        pred_model = DualTimescalePredictor(
            rng=int_rng, alpha=config.consolidation_alpha, slow_channel=slow_ch,
        )
    else:
        pred_model = PredictiveModel(rng=int_rng)
        slow_ch    = None

    actuator      = Actuator()
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

    # Preconditioning phase: advance internal state with a *throwaway* env
    if precondition_ticks > 0:
        pre_env = Environment(env_cfg, seed=seed_int)   # different seed → different obs
        for t in range(precondition_ticks):
            obs = pre_env.step()
            loop.tick(obs, t)
            metabolic.replenish()

    # Main run uses seed_ext — identical for both pair members
    env = Environment(env_cfg, seed=seed_ext)

    # ── Run loop ─────────────────────────────────────────────────────────
    n_ticks  = int(config.run_duration_s * config.f_tick)
    epsilon_history: List[float] = []
    gate_history:    List[bool]  = []
    ts0 = time.time()

    for t in range(n_ticks):
        ts  = ts0 + t / config.f_tick
        obs = env.step()

        is_state = loop.tick(obs, t)
        metabolic.replenish()
        cmd  = actuator.command(ise, gate, metabolic, t)
        prop = proprioceptor.read(t, metabolic, ise, gate, actuator)

        tick_id = db.write_tick(run_id=run_id, timestamp=ts, seed=seed_ext)
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

        # Slow-weight consolidation tick (no-op if disabled)
        if slow_ch is not None:
            consol = pred_model.tick_slow(
                tick_id=t,
                epsilon=is_state.epsilon,
                ise_drive=ise.drive,
                metabolic=metabolic.normalised,
            )
            if consol is not None:
                db.write_event(tick_id, "CONSOLIDATION", {
                    "index":      consol.index,
                    "delta_slow": consol.delta_slow,
                    "mu_slow":    pred_model.mu_slow,
                })

        epsilon_history.append(is_state.epsilon)
        gate_history.append(is_state.gate_fired)

        if (t + 1) % COMMIT_EVERY == 0:
            db.commit()

    db.commit()

    n_consol = slow_ch.n_consolidations if slow_ch is not None else 0
    return {
        "run_id":           run_id,
        "condition":        condition,
        "seed_ext":         seed_ext,
        "seed_int":         seed_int,
        "gate_fires":       gate.fire_count,
        "mean_eps":         float(np.mean(np.abs(epsilon_history))),
        "max_eps":          float(np.max(np.abs(epsilon_history))),
        "ticks":            n_ticks,
        "n_consolidations": n_consol,
    }


def run_paired_batch(
    config:        HarnessConfig,
    paired_config: PairedBatchConfig,
    batch_id:      str,
    db_path:       Optional[str] = None,
) -> Dict[str, List[Dict]]:
    """
    Run a calibration / paired-counterfactual batch.

    Returns a dict:
        "pairs"    — list of {"pair_id", "run_a", "run_b"} dicts
        "controls" — list of standard run summary dicts (Baseline + Ablation)

    Pair design
    -----------
    - seed_ext: shared between pair members (same env noise stream)
    - seed_int_a, seed_int_b: different per member (diverging internal priors)

    DB tagging
    ----------
    Each paired run's `params` JSON includes:
        pair_id   — integer pair index
        pair_role — "A" or "B"
        seed_ext  — the shared external seed
        seed_int  — this member's internal seed
    """
    db_path = db_path or config.db_path.format(batch_id=batch_id)
    db_path = str(Path(db_path))

    master_rng = random.Random(config.batch_seed)

    # Draw seeds
    ext_seeds  = [master_rng.randint(0, 2**31)
                  for _ in range(paired_config.n_pairs)]
    int_seeds_a = [master_rng.randint(0, 2**31)
                   for _ in range(paired_config.n_pairs)]
    int_seeds_b = [master_rng.randint(0, 2**31)
                   for _ in range(paired_config.n_pairs)]
    ctrl_base_seeds = [master_rng.randint(0, 2**31)
                       for _ in range(paired_config.n_baseline_controls)]
    ctrl_abla_seeds = [master_rng.randint(0, 2**31)
                       for _ in range(paired_config.n_ablation_controls)]

    # Build run plan: (kind, args) where kind ∈ {"pair_a","pair_b","ctrl"}
    run_plan: List[tuple] = []
    for i in range(paired_config.n_pairs):
        run_plan.append(("pair_a", i, ext_seeds[i], int_seeds_a[i]))
        run_plan.append(("pair_b", i, ext_seeds[i], int_seeds_b[i]))
    for s in ctrl_base_seeds:
        run_plan.append(("ctrl_baseline", s))
    for s in ctrl_abla_seeds:
        run_plan.append(("ctrl_ablation", s))
    master_rng.shuffle(run_plan)

    pairs_by_id: Dict[int, Dict] = {}   # pair_id → {run_a: ..., run_b: ...}
    controls:    List[Dict]      = []

    with Database(db_path) as db:
        for plan_idx, entry in enumerate(run_plan):
            kind = entry[0]
            total = len(run_plan)
            logger.info(f"[PairedHarness] {plan_idx+1}/{total} kind={kind}")

            if kind in ("pair_a", "pair_b"):
                _, pair_id, seed_ext, seed_int = entry
                role      = "A" if kind == "pair_a" else "B"
                condition = "Baseline"
                params    = {
                    "batch_id":   batch_id,
                    "pair_id":    pair_id,
                    "pair_role":  role,
                    "seed_ext":   seed_ext,
                    "seed_int":   seed_int,
                    "run_type":   "paired",
                }
                run_id  = db.begin_run(condition, seed_ext, params)
                summary = run_single_split_seed(
                    db, run_id, config,
                    seed_ext=seed_ext, seed_int=seed_int,
                    condition=condition,
                    precondition_ticks=paired_config.precondition_ticks,
                )
                summary.update({"pair_id": pair_id, "pair_role": role})
                db.end_run(run_id)

                pairs_by_id.setdefault(pair_id, {})
                pairs_by_id[pair_id][f"run_{role.lower()}"] = summary

                logger.info(
                    f"[PairedHarness] pair={pair_id}{role} "
                    f"fires={summary['gate_fires']} ε={summary['mean_eps']:.4f}"
                )

            else:
                _, seed = entry
                condition = "Baseline" if kind == "ctrl_baseline" else "Ablation"
                params    = {
                    "batch_id":  batch_id,
                    "run_type":  "control",
                }
                run_id  = db.begin_run(condition, seed, params)
                summary = run_single(db, run_id, config, seed, condition)
                summary["run_type"] = "control"
                db.end_run(run_id)
                controls.append(summary)

                logger.info(
                    f"[PairedHarness] ctrl cond={condition} "
                    f"fires={summary['gate_fires']} ε={summary['mean_eps']:.4f}"
                )

    pairs = [
        {"pair_id": pid, **members}
        for pid, members in sorted(pairs_by_id.items())
    ]
    return {"pairs": pairs, "controls": controls}


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
    p.add_argument("--paired",   action="store_true",
                   help="Run paired counterfactual batch instead of standard batch")
    p.add_argument("--n-pairs",  type=int, default=10,
                   help="Number of counterfactual pairs (default 10 for calibration)")
    p.add_argument("--n-controls", type=int, default=10,
                   help="Baseline + Ablation controls each in paired mode")
    p.add_argument("--precondition-ticks", type=int, default=0,
                   help="Preconditioning ticks for internal history divergence")
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

    if args.paired:
        paired_cfg = PairedBatchConfig(
            n_pairs=args.n_pairs,
            n_baseline_controls=args.n_controls,
            n_ablation_controls=args.n_controls,
            precondition_ticks=args.precondition_ticks,
        )
        result = run_paired_batch(config, paired_cfg, args.batch_id,
                                  db_path=args.db_path)
        pairs    = result["pairs"]
        controls = result["controls"]

        print("\n=== PAIRED BATCH SUMMARY ===")
        print(f"  Pairs: {len(pairs)}  Controls: {len(controls)}")
        for p in pairs:
            a = p.get("run_a", {})
            b = p.get("run_b", {})
            print(
                f"  pair={p['pair_id']:>3}  "
                f"A fires={a.get('gate_fires','?'):>4} ε={a.get('mean_eps',0):.4f}  "
                f"B fires={b.get('gate_fires','?'):>4} ε={b.get('mean_eps',0):.4f}"
            )
        print(f"\nTotal pairs: {len(pairs)}  Controls: {len(controls)}")

    else:
        summaries = run_batch(config, args.batch_id, db_path=args.db_path)

        print("\n=== BATCH SUMMARY ===")
        for s in summaries:
            print(
                f"  run_id={s['run_id']:>3} cond={s['condition']:<10} "
                f"seed={s['seed']:<12} fires={s['gate_fires']:>5} "
                f"mean_ε={s['mean_eps']:.4f}"
            )
        print(f"\nTotal runs: {len(summaries)}")
