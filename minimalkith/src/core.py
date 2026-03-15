"""
core.py — MinimalKith primitive classes.

MinimalKith is a minimal interoceptive organism that demonstrates the
causal relationship between prediction error (ε), interoceptive state
estimation (ISE), and ritualistic gating behaviour (RitualGate).

Primitives
----------
Metabolic  : energetic resource that drains with actuation and replenishes.
ISE        : Interoceptive State Estimator — drive vector derived from ε.
RitualGate : Boolean gate triggered when ISE crosses a threshold.
PredictiveModel : lightweight generative model producing εₜ.
Actuator   : motor command generator with metabolic cost.
Proprioceptor : sensor that reads body state + environment.
"""

from __future__ import annotations

import math
import time
import logging
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

logger = logging.getLogger("MK.Core")


# ---------------------------------------------------------------------------
# Metabolic
# ---------------------------------------------------------------------------

@dataclass
class MetabolicState:
    budget:     float       # current metabolic budget
    capacity:   float       # maximum budget
    drain_rate: float       # budget drained per unit actuator cost
    replenish:  float       # budget replenished per tick at rest


class Metabolic:
    """
    Metabolic energy budget.

    drain(cost) — consume energy proportional to actuator cost.
    replenish()  — passive per-tick energy recovery.
    """

    def __init__(
        self,
        capacity:   float = 100.0,
        initial:    float = 100.0,
        drain_rate: float = 0.1,
        replenish:  float = 0.5,
    ):
        self.state = MetabolicState(
            budget=float(initial),
            capacity=float(capacity),
            drain_rate=float(drain_rate),
            replenish=float(replenish),
        )

    def drain(self, cost: float) -> float:
        """Remove energy proportional to cost.  Returns actual drain."""
        actual = min(self.state.budget, cost * self.state.drain_rate)
        self.state.budget -= actual
        return actual

    def replenish(self):
        """Passive per-tick recovery."""
        self.state.budget = min(
            self.state.capacity,
            self.state.budget + self.state.replenish
        )

    @property
    def normalised(self) -> float:
        """Budget in [0, 1]."""
        return self.state.budget / max(1e-9, self.state.capacity)

    @property
    def depleted(self) -> bool:
        return self.state.budget < 1e-3


# ---------------------------------------------------------------------------
# ISE — Interoceptive State Estimator
# ---------------------------------------------------------------------------

class ISE:
    """
    Integrates prediction error ε into a drive vector.

    d(drive)/dt = ε − decay × drive
    drive is a scalar in [−∞, ∞]; positive drive signals unresolved error.

    When |drive| crosses the gate_threshold the RitualGate fires.
    """

    def __init__(
        self,
        decay:          float = 0.05,
        gate_threshold: float = 1.0,
        dt:             float = 1.0 / 50.0,   # 50 Hz
    ):
        self.decay          = float(decay)
        self.gate_threshold = float(gate_threshold)
        self.dt             = float(dt)
        self.drive: float   = 0.0

    def update(self, epsilon: float) -> float:
        """Integrate one tick of prediction error.  Returns updated drive."""
        self.drive += self.dt * (epsilon - self.decay * self.drive)
        return self.drive

    @property
    def above_threshold(self) -> bool:
        return abs(self.drive) >= self.gate_threshold

    def reset(self):
        self.drive = 0.0


# ---------------------------------------------------------------------------
# RitualGate
# ---------------------------------------------------------------------------

@dataclass
class GateEvent:
    tick:        int
    timestamp:   float
    drive_at_trigger: float
    epsilon_at_trigger: float


class RitualGate:
    """
    Boolean gate that fires when ISE drive crosses threshold.

    On firing: ISE drive is partially reset (simulating post-gate relief).
    Consecutive firing is blocked for refractory_ticks to prevent chatter.
    """

    def __init__(
        self,
        refractory_ticks: int   = 5,
        drive_reset_frac: float = 0.5,
    ):
        self.refractory_ticks = int(refractory_ticks)
        self.drive_reset_frac = float(drive_reset_frac)
        self._refractory_remaining = 0
        self.state: bool = False
        self.events: List[GateEvent] = []

    def evaluate(
        self,
        ise:     ISE,
        epsilon: float,
        tick:    int,
    ) -> bool:
        """
        Evaluate gate condition and fire if appropriate.
        Returns True if the gate fires this tick.
        """
        if self._refractory_remaining > 0:
            self._refractory_remaining -= 1
            self.state = False
            return False

        if ise.above_threshold:
            self.state = True
            self._refractory_remaining = self.refractory_ticks
            ise.drive *= (1.0 - self.drive_reset_frac)   # partial reset

            event = GateEvent(
                tick=tick,
                timestamp=time.time(),
                drive_at_trigger=ise.drive,
                epsilon_at_trigger=epsilon,
            )
            self.events.append(event)
            logger.debug(f"[Gate] FIRE tick={tick} drive={ise.drive:.3f} ε={epsilon:.3f}")
            return True

        self.state = False
        return False

    @property
    def fire_count(self) -> int:
        return len(self.events)


# ---------------------------------------------------------------------------
# PredictiveModel
# ---------------------------------------------------------------------------

class PredictiveModel:
    """
    Lightweight generative model that produces a prediction μₜ of the
    next environment observation, giving εₜ = observation − μₜ.

    The model maintains a running exponential moving average of observations
    (analogous to a simple Kalman filter prior) and can update online.

    A richer implementation can replace predict() with a neural network.
    """

    def __init__(
        self,
        alpha: float = 0.15,   # EMA smoothing factor
        noise: float = 0.0,    # optional stochastic noise on prediction
        rng: Optional[np.random.Generator] = None,
    ):
        self.alpha = float(alpha)
        self.noise = float(noise)
        self._rng  = rng or np.random.default_rng(0)
        self._mu: float = 0.0          # current prediction
        self._initialised: bool = False

    def predict(self) -> float:
        """Return current prediction μₜ."""
        if self.noise > 0.0:
            return self._mu + self._rng.normal(0.0, self.noise)
        return self._mu

    def update(self, observation: float):
        """Update internal model with new observation (online learning)."""
        if not self._initialised:
            self._mu = observation
            self._initialised = True
        else:
            self._mu = self.alpha * observation + (1.0 - self.alpha) * self._mu

    def prediction_error(self, observation: float) -> float:
        """Compute εₜ = observation − μₜ."""
        return observation - self.predict()


# ---------------------------------------------------------------------------
# Actuator
# ---------------------------------------------------------------------------

@dataclass
class ActuatorCommand:
    tick:       int
    magnitude:  float      # signed motor command in [-1, 1]
    cost:       float      # metabolic cost incurred


class Actuator:
    """
    Produces motor commands and charges the metabolic system.

    The command magnitude scales with gate state and drive magnitude,
    capped at max_magnitude.
    """

    def __init__(
        self,
        base_cost:     float = 1.0,
        max_magnitude: float = 1.0,
    ):
        self.base_cost     = float(base_cost)
        self.max_magnitude = float(max_magnitude)
        self.history: List[ActuatorCommand] = []

    def command(
        self,
        ise:      ISE,
        gate:     RitualGate,
        metabolic: Metabolic,
        tick:     int,
    ) -> ActuatorCommand:
        """
        Generate and execute one motor command.
        - When gate fires, command magnitude is drive-proportional.
        - When gate is inactive, command is near-zero (maintenance).
        """
        if gate.state:
            magnitude = float(np.clip(ise.drive, -self.max_magnitude, self.max_magnitude))
        else:
            magnitude = 0.05 * float(np.sign(ise.drive))   # idle maintenance

        cost = self.base_cost * abs(magnitude)
        metabolic.drain(cost)

        cmd = ActuatorCommand(tick=tick, magnitude=magnitude, cost=cost)
        self.history.append(cmd)
        return cmd


# ---------------------------------------------------------------------------
# Proprioceptor
# ---------------------------------------------------------------------------

@dataclass
class ProprioceptiveReading:
    tick:           int
    metabolic_norm: float   # metabolic budget ∈ [0, 1]
    drive:          float   # ISE drive
    gate_state:     bool
    last_magnitude: float   # last actuator command


class Proprioceptor:
    """
    Reads internal body state and packages it as a structured observation
    for the PredictiveModel and ISE routing logic.
    """

    def read(
        self,
        tick:       int,
        metabolic:  Metabolic,
        ise:        ISE,
        gate:       RitualGate,
        actuator:   Actuator,
    ) -> ProprioceptiveReading:
        last_mag = actuator.history[-1].magnitude if actuator.history else 0.0
        return ProprioceptiveReading(
            tick=tick,
            metabolic_norm=metabolic.normalised,
            drive=ise.drive,
            gate_state=gate.state,
            last_magnitude=last_mag,
        )
