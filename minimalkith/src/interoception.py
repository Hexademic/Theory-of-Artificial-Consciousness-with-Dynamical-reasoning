"""
interoception.py — Interoceptive routing loop.

This module wires:
    observation → PredictiveModel → ε → ISE → RitualGate

The routing flag `connected` can be set to False for ablation runs:
    When False, ε does NOT update ISE; the gate receives no interoceptive input.
    The sham flag toggles the routing flag but leaves connections structurally intact.

All routing logic lives here so that ablation is a single toggle, not scattered.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .core import Metabolic, ISE, RitualGate, PredictiveModel, Actuator, Proprioceptor

logger = logging.getLogger("MK.Interoception")


@dataclass
class InteroceptiveState:
    """Snapshot of the interoceptive loop at one tick."""
    tick:        int
    epsilon:     float
    drive:       float
    gate_fired:  bool
    connected:   bool        # was routing active this tick?


class InteroceptiveLoop:
    """
    Manages the routing from prediction error → ISE → RitualGate.

    Parameters
    ----------
    connected : bool
        True = full interoceptive routing (normal condition).
        False = ablated condition; ISE receives zero input.
    sham : bool
        True = sham ablation; flag is toggled but routing is intact.
        Sham allows verification that the flag alone has no effect.
    """

    def __init__(
        self,
        predictive_model: PredictiveModel,
        ise:              ISE,
        gate:             RitualGate,
        connected:        bool = True,
        sham:             bool = False,
    ):
        self.model     = predictive_model
        self.ise       = ise
        self.gate      = gate
        self._connected = connected
        self._sham      = sham

    # ------------------------------------------------------------------

    def tick(
        self,
        observation: float,
        tick_id:     int,
    ) -> InteroceptiveState:
        """
        Run one interoceptive tick.

        1. Update the predictive model with the new observation.
        2. Compute ε = observation − μ.
        3. Route ε → ISE (if connected and not ablated).
        4. Evaluate RitualGate.
        """
        self.model.update(observation)
        epsilon = self.model.prediction_error(observation)

        # Routing logic
        routed = self._connected or self._sham
        if routed:
            self.ise.update(epsilon)
        else:
            # Ablated: ISE receives zero error input
            self.ise.update(0.0)

        fired = self.gate.evaluate(self.ise, epsilon, tick_id)

        return InteroceptiveState(
            tick=tick_id,
            epsilon=epsilon,
            drive=self.ise.drive,
            gate_fired=fired,
            connected=self._connected and not self._sham,
        )

    # ------------------------------------------------------------------

    def ablate(self):
        """Disconnect interoceptive routing (true ablation)."""
        self._connected = False
        self._sham      = False
        logger.info("[Interoception] ABLATED — routing disconnected.")

    def reconnect(self):
        """Restore interoceptive routing."""
        self._connected = True
        self._sham      = False
        logger.info("[Interoception] RECONNECTED — routing restored.")

    def set_sham(self, sham: bool):
        """
        Set sham mode.  Sham sets the flag but keeps actual routing intact.
        Use to verify that the flag alone has no effect on behaviour.
        """
        self._sham = sham
        logger.info(f"[Interoception] Sham={'ON' if sham else 'OFF'}.")

    @property
    def connected(self) -> bool:
        return self._connected and not self._sham
