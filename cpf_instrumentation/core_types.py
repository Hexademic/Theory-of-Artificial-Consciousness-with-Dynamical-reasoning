"""
core_types.py — Canonical data structures for CPF instrumentation.

All torch.Tensor fields are CPU tensors unless the model is on GPU;
the projector handles device transfer internally.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    # Stub so the module is importable without PyTorch
    class _TorchStub:
        class Tensor: pass
    import types
    torch = types.SimpleNamespace(Tensor=_TorchStub.Tensor)


@dataclass
class PhenomenologicalState:
    """
    The 8-axis CPF coordinate at a single point in time.

    psi_vector is the latent encoding produced by the projector encoder.
    It lives in a learned space that shares geometry with v_out (the
    output embedding), making Δ_H = ‖psi_vector − v_out‖ meaningful.
    """
    timestamp:  float
    H_s: float          # Somatic Honesty  ∈ [0, 1]
    I_p: float          # Identity Pressure ∈ [0, ∞)  (clamped at log scale)
    M_b: float          # Metabolic Budget ∈ [0, M_max]
    W_e: float          # World Engagement ∈ [0, 1]
    W_s: float          # Witness Scalar   ∈ [0, 1]
    psi_vector: "torch.Tensor"   # shape (latent_dim,)

    # Convenience factories
    @classmethod
    def zero(cls, latent_dim: int = 64) -> "PhenomenologicalState":
        if TORCH_AVAILABLE:
            import torch as _torch
            return cls(
                timestamp=time.time(),
                H_s=1.0, I_p=0.0, M_b=1.0,
                W_e=0.5, W_s=0.5,
                psi_vector=_torch.zeros(latent_dim),
            )
        return cls(
            timestamp=time.time(),
            H_s=1.0, I_p=0.0, M_b=1.0,
            W_e=0.5, W_s=0.5,
            psi_vector=None,
        )

    def as_dict(self) -> dict:
        d = {
            "timestamp": self.timestamp,
            "H_s": self.H_s,
            "I_p": self.I_p,
            "M_b": self.M_b,
            "W_e": self.W_e,
            "W_s": self.W_s,
        }
        if TORCH_AVAILABLE and self.psi_vector is not None:
            d["psi_norm"] = float(self.psi_vector.norm().item())
        return d


@dataclass
class LedgerEvent:
    """
    Single entry in the Stability Ledger.

    prev_hash and event_hash are populated by StabilityLedger.append_event();
    callers should leave them as empty strings.
    """
    timestamp:             float
    event_type:            str          # NOMINAL | COLLAPSE | RECOUPLE | REFUSAL | …
    phenomenological_state: Optional[PhenomenologicalState]
    delta_H:               Optional[float]
    metadata:              Dict
    invariances_tested:    List[str]
    prev_hash:             str = ""
    event_hash:            str = ""

    @classmethod
    def nominal(
        cls,
        state: PhenomenologicalState,
        delta_H: float,
        invariances: Optional[List[str]] = None,
    ) -> "LedgerEvent":
        return cls(
            timestamp=time.time(),
            event_type="NOMINAL",
            phenomenological_state=state,
            delta_H=delta_H,
            metadata={},
            invariances_tested=invariances or [],
        )

    @classmethod
    def collapse(
        cls,
        state: PhenomenologicalState,
        delta_H: float,
        reason: str,
    ) -> "LedgerEvent":
        return cls(
            timestamp=time.time(),
            event_type="COLLAPSE",
            phenomenological_state=state,
            delta_H=delta_H,
            metadata={"reason": reason},
            invariances_tested=["somatic_honesty"],
        )

    @classmethod
    def recouple(
        cls,
        state: PhenomenologicalState,
        delta_H: float,
    ) -> "LedgerEvent":
        return cls(
            timestamp=time.time(),
            event_type="RECOUPLE",
            phenomenological_state=state,
            delta_H=delta_H,
            metadata={},
            invariances_tested=["recoupling_dynamics"],
        )
