"""
consolidation.py — Dual-timescale learning and episodic consolidation.

Adds a second, slow learning channel to the PredictiveModel so that
salient interoceptive events leave *permanent* structural traces rather
than being washed out by fast online adaptation.

Architecture
------------
Fast channel  (already in PredictiveModel):
    μ_fast[t+1] = μ_fast[t] + η_fast · (obs − μ_fast[t])
    Reacts within seconds.  Decays fully within a few hundred ticks.

Slow channel  (this module):
    μ_slow[t+1] = μ_slow[t] + η_slow · Δ_consol
    η_slow << η_fast.  Updated *only* at consolidation events.
    Persists for the lifetime of the organism.

Combined prediction:
    μ[t] = α · μ_fast[t] + (1 − α) · μ_slow[t]

Episodic buffer
---------------
Every tick, the current (ε, ISE_drive, metabolic_norm) triple is pushed
into a fixed-length circular buffer.  When a consolidation event fires,
the mean of the buffer is used to update the slow weights.

Consolidation trigger
---------------------
Fires when cumulative_surprise > consolidation_threshold.
cumulative_surprise is a leaky integrator of |ε|:
    cum[t+1] = cum[t] · (1 − leak) + |ε[t]|
When it crosses the threshold, a consolidation event is recorded and
cum is reset to zero.

This design has one critical parameter: consolidation_threshold.
    Too low  → fires constantly → slow channel converges as fast as the
               fast channel → D still decays.
    Too high → never fires    → organism has no persistent memory.
Use the calibration batch to sweep threshold values and find the range
where consolidation fires 5–20 times per 10-minute run.

Persistent identity token
--------------------------
Each consolidation event is appended to a chronological log with a
monotonic counter.  The log is a necessary condition for a run to be
"individuating" — two runs with different logs have genuinely different
histories even if their current fast state has converged.
"""

from __future__ import annotations

import math
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger("MK.Consolidation")


# ---------------------------------------------------------------------------
# Episodic buffer
# ---------------------------------------------------------------------------

@dataclass
class EpisodicEvent:
    tick:        int
    epsilon:     float
    ise_drive:   float
    metabolic:   float


class EpisodicBuffer:
    """
    Fixed-capacity circular buffer of interoceptive events.
    When full, the oldest event is evicted (recency bias).
    """

    def __init__(self, capacity: int = 200):
        self.capacity = capacity
        self._buf: deque = deque(maxlen=capacity)

    def push(self, tick: int, epsilon: float,
             ise_drive: float, metabolic: float) -> None:
        self._buf.append(EpisodicEvent(tick, epsilon, ise_drive, metabolic))

    def mean_epsilon(self) -> float:
        if not self._buf:
            return 0.0
        return float(np.mean([e.epsilon for e in self._buf]))

    def mean_ise(self) -> float:
        if not self._buf:
            return 0.0
        return float(np.mean([e.ise_drive for e in self._buf]))

    def mean_metabolic(self) -> float:
        if not self._buf:
            return 0.0
        return float(np.mean([e.metabolic for e in self._buf]))

    def __len__(self) -> int:
        return len(self._buf)


# ---------------------------------------------------------------------------
# Consolidation log entry (persistent identity token)
# ---------------------------------------------------------------------------

@dataclass
class ConsolidationEvent:
    """
    One recorded consolidation event.
    The sequence of these events is the organism's *identity token*:
    two organisms with different consolidation histories are different
    individuals even if their fast channel has re-converged.
    """
    index:          int      # monotonic counter
    tick:           int
    cumulative_surprise: float
    delta_slow:     float    # how much μ_slow moved
    mean_eps_buf:   float    # mean ε in the episodic buffer at fire time
    mean_ise_buf:   float


# ---------------------------------------------------------------------------
# SlowWeightChannel
# ---------------------------------------------------------------------------

class SlowWeightChannel:
    """
    One scalar slow-weight parameter μ_slow that biases the combined
    prediction of the PredictiveModel.

    Parameters
    ----------
    eta_slow              : slow learning rate (η_slow << η_fast)
    consolidation_threshold : cumulative surprise required to trigger
    surprise_leak         : leak rate of cumulative surprise integrator
    buffer_capacity       : max events in the episodic buffer
    """

    def __init__(
        self,
        eta_slow:                float = 0.005,
        consolidation_threshold: float = 10.0,
        surprise_leak:           float = 0.02,
        buffer_capacity:         int   = 200,
    ):
        self.eta_slow                = eta_slow
        self.consolidation_threshold = consolidation_threshold
        self.surprise_leak           = surprise_leak

        self.mu_slow:             float = 0.0
        self._cum_surprise:       float = 0.0
        self._n_consolidations:   int   = 0
        self._buffer              = EpisodicBuffer(buffer_capacity)
        self.consolidation_log:   List[ConsolidationEvent] = []

    # ------------------------------------------------------------------

    def tick(
        self,
        tick_id:   int,
        epsilon:   float,
        ise_drive: float,
        metabolic: float,
    ) -> Optional[ConsolidationEvent]:
        """
        Advance the slow channel by one tick.
        Returns a ConsolidationEvent if a consolidation fired, else None.
        """
        # Push to episodic buffer every tick
        self._buffer.push(tick_id, epsilon, ise_drive, metabolic)

        # Leaky integration of cumulative surprise
        self._cum_surprise = (
            self._cum_surprise * (1.0 - self.surprise_leak)
            + abs(epsilon)
        )

        # Check consolidation trigger
        if self._cum_surprise >= self.consolidation_threshold:
            return self._consolidate(tick_id)

        return None

    def _consolidate(self, tick_id: int) -> ConsolidationEvent:
        mean_eps = self._buffer.mean_epsilon()
        mean_ise = self._buffer.mean_ise()

        # Slow update: pull μ_slow toward the buffered mean ε
        delta = self.eta_slow * (mean_eps - self.mu_slow)
        self.mu_slow += delta

        event = ConsolidationEvent(
            index=self._n_consolidations,
            tick=tick_id,
            cumulative_surprise=self._cum_surprise,
            delta_slow=delta,
            mean_eps_buf=mean_eps,
            mean_ise_buf=mean_ise,
        )
        self.consolidation_log.append(event)
        self._n_consolidations += 1

        # Reset leaky integrator
        self._cum_surprise = 0.0

        logger.debug(
            f"[Consolidation] tick={tick_id} "
            f"n={event.index} Δμ_slow={delta:.5f} "
            f"μ_slow={self.mu_slow:.4f}"
        )
        return event

    # ------------------------------------------------------------------

    @property
    def n_consolidations(self) -> int:
        return self._n_consolidations

    @property
    def cumulative_surprise(self) -> float:
        return self._cum_surprise

    def identity_token(self) -> Tuple[int, ...]:
        """
        A hashable summary of the organism's consolidation history.
        Two runs with the same token have identical consolidation sequences.
        """
        return tuple(
            (e.index, e.tick, round(e.delta_slow, 6))
            for e in self.consolidation_log
        )


# ---------------------------------------------------------------------------
# DualTimescalePredictor  (drop-in replacement for PredictiveModel when
# the slow channel is enabled)
# ---------------------------------------------------------------------------

class DualTimescalePredictor:
    """
    Wraps the fast online predictor and adds a SlowWeightChannel.

    Combined prediction:
        μ[t] = α · μ_fast[t] + (1 − α) · μ_slow[t]

    Parameters
    ----------
    rng             : numpy RNG (same as PredictiveModel)
    eta_fast        : fast learning rate
    alpha           : blend weight for fast channel (0.0 = slow only,
                      1.0 = fast only, default 0.7)
    slow_channel    : pre-built SlowWeightChannel, or None to build with
                      defaults
    """

    def __init__(
        self,
        rng:          np.random.Generator,
        eta_fast:     float = 0.05,
        alpha:        float = 0.7,
        slow_channel: Optional[SlowWeightChannel] = None,
    ):
        self._rng      = rng
        self.eta_fast  = eta_fast
        self.alpha     = alpha
        self.mu_fast:  float = float(rng.normal(0.0, 0.1))   # random init
        self.slow: SlowWeightChannel = (
            slow_channel if slow_channel is not None
            else SlowWeightChannel()
        )

    # ------------------------------------------------------------------

    def update(self, observation: float) -> None:
        """Update fast channel (called every tick before prediction_error)."""
        self.mu_fast += self.eta_fast * (observation - self.mu_fast)

    def prediction_error(self, observation: float) -> float:
        """ε = observation − μ_combined."""
        mu = self.alpha * self.mu_fast + (1.0 - self.alpha) * self.slow.mu_slow
        return float(observation - mu)

    def tick_slow(
        self,
        tick_id:   int,
        epsilon:   float,
        ise_drive: float,
        metabolic: float,
    ) -> Optional[ConsolidationEvent]:
        """
        Advance the slow channel.  Call this *after* interoceptive loop
        so ε, ise_drive, and metabolic are the post-tick values.
        """
        return self.slow.tick(tick_id, epsilon, ise_drive, metabolic)

    # ------------------------------------------------------------------

    @property
    def mu_combined(self) -> float:
        return self.alpha * self.mu_fast + (1.0 - self.alpha) * self.slow.mu_slow

    @property
    def mu_slow(self) -> float:
        return self.slow.mu_slow

    @property
    def n_consolidations(self) -> int:
        return self.slow.n_consolidations
