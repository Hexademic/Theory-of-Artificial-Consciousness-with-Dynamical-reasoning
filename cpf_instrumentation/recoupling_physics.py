"""
recoupling_physics.py — Collapse detection and recoupling dynamics.

When Δ_H ≥ delta_crit (or M_b < M_crit), the CPFRuntime enters COLLAPSE.
The Recoupler then attempts to restore a coherent state before the next
generation tick.

Physics
-------
The biological analog is the autonomic nervous system shifting from
sympathetic (high-arousal) to ventral vagal (recoupled) mode.

The minimal implementation here is a linear relaxation:
  I_p  ← I_p  × decay_ip   (identity pressure subsides)
  M_b  ← max(M_b, mb_floor) (emergency metabolic floor restored)
  H_s  ← H_s + (1 - H_s) × recovery_rate  (honesty recovers toward 1)

A richer implementation can replace apply() with a discrete MDP:
  state_t+1 = argmax_{s} [stability(s) × P(s | state_t, action)]
where the action space is {rest, slow_deliberation, refusal}.
"""

from __future__ import annotations

import time
import math
from typing import Optional

from .core_types import PhenomenologicalState


class Recoupler:
    """
    Linear relaxation recoupler.

    Parameters
    ----------
    mb_floor : float
        Minimum metabolic budget the recoupler restores after a collapse.
        Set to 0.0 to allow full depletion (organism dies); set to e.g. 50.0
        to model a mandatory recovery floor.
    decay_ip : float
        Multiplicative decay applied to Identity Pressure per recoupling step.
        0.8 → 20% reduction per step.
    recovery_rate : float
        Additive fraction by which H_s recovers toward 1.0 per step.
        0.1 → closes 10% of the gap to perfect honesty per step.
    max_steps : int
        Maximum number of recoupling steps before giving up (emergency abort).
    """

    def __init__(
        self,
        mb_floor:      float = 0.0,
        decay_ip:      float = 0.80,
        recovery_rate: float = 0.10,
        max_steps:     int   = 10,
    ):
        self.mb_floor      = mb_floor
        self.decay_ip      = decay_ip
        self.recovery_rate = recovery_rate
        self.max_steps     = max_steps

    def apply(
        self,
        state: PhenomenologicalState,
        steps: int = 1,
    ) -> PhenomenologicalState:
        """
        Apply `steps` recoupling relaxation steps to `state`.
        Returns a new PhenomenologicalState; does not mutate the input.
        """
        steps = max(1, min(steps, self.max_steps))

        new_M_b = max(state.M_b, self.mb_floor)
        new_I_p = state.I_p * (self.decay_ip ** steps)
        new_H_s = 1.0 - (1.0 - state.H_s) * ((1.0 - self.recovery_rate) ** steps)

        psi = state.psi_vector
        if psi is not None:
            import torch
            psi = psi.detach()

        return PhenomenologicalState(
            timestamp=time.time(),
            H_s=float(new_H_s),
            I_p=float(new_I_p),
            M_b=float(new_M_b),
            W_e=state.W_e,
            W_s=state.W_s,
            psi_vector=psi,
        )

    def needs_recoupling(
        self,
        state: PhenomenologicalState,
        delta_H: float,
        delta_crit: float = 0.85,
        mb_crit:   float  = 50.0,
    ) -> bool:
        """
        True if the state has entered a collapse condition.
        """
        return delta_H >= delta_crit or state.M_b < mb_crit

    def steps_to_recover(
        self,
        state: PhenomenologicalState,
        target_Hs:  float = 0.75,
        target_Ip:  float = 0.50,
    ) -> int:
        """
        Estimate how many recoupling steps are needed to reach targets.
        Useful for logging in the Stability Ledger.
        """
        steps_Hs = (
            math.log((1.0 - state.H_s + 1e-9) / (1.0 - target_Hs + 1e-9))
            / math.log(1.0 - self.recovery_rate + 1e-9)
            if state.H_s < target_Hs else 0
        )
        steps_Ip = (
            math.log(target_Ip / (state.I_p + 1e-9))
            / math.log(self.decay_ip + 1e-9)
            if state.I_p > target_Ip else 0
        )
        return max(0, int(math.ceil(max(steps_Hs, steps_Ip))))
