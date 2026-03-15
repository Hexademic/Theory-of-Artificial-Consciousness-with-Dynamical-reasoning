"""
environment.py — Deterministic scalar environment generator.

The environment emits a continuous scalar signal:
    observation(t) = A·sin(2π·f·t + φ) + noise(t)

Pressure pulses can be scheduled to spike amplitude at defined intervals,
simulating the Mixed Niche and City developmental stages.

All randomness is fully seeded for reproducibility.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np


@dataclass
class EnvironmentConfig:
    amplitude:       float = 1.0        # base sine amplitude
    frequency:       float = 0.5        # Hz
    phase:           float = 0.0        # radians
    noise_std:       float = 0.1        # Gaussian noise std
    pressure_pulses: List[dict] = field(default_factory=list)
    # pulse format: {"start_tick": int, "end_tick": int, "amplitude": float}


class Environment:
    """
    Deterministic scalar signal generator.

    Usage:
        env = Environment(EnvironmentConfig(noise_std=0.2), seed=42)
        obs = env.step()   # call each tick
    """

    def __init__(self, config: EnvironmentConfig, seed: int = 0):
        self.config = config
        self._rng   = np.random.default_rng(seed)
        self._tick  = 0

    def step(self) -> float:
        """
        Advance the environment one tick and return the observation scalar.
        """
        t     = self._tick
        f_tick = self.config.frequency / 50.0   # normalised to 50 Hz tick rate
        base   = self.config.amplitude * math.sin(
            2.0 * math.pi * f_tick * t + self.config.phase
        )
        noise  = self._rng.normal(0.0, self.config.noise_std)

        # Apply any pressure pulse active at this tick
        pulse_amp = self._active_pulse_amplitude(t)
        obs = (self.config.amplitude + pulse_amp) * math.sin(
            2.0 * math.pi * f_tick * t + self.config.phase
        ) + noise

        self._tick += 1
        return float(obs)

    def _active_pulse_amplitude(self, tick: int) -> float:
        for pulse in self.config.pressure_pulses:
            if pulse["start_tick"] <= tick < pulse["end_tick"]:
                return float(pulse["amplitude"])
        return 0.0

    @property
    def tick(self) -> int:
        return self._tick

    def reset(self, seed: Optional[int] = None):
        """Reset tick counter and optionally re-seed RNG."""
        self._tick = 0
        if seed is not None:
            self._rng = np.random.default_rng(seed)
