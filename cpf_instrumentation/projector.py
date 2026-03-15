"""
projector.py — Maps raw telemetry tensors into the 8-axis CPF coordinate
               space, producing a PhenomenologicalState every forward pass.

Architecture:
    flat_telemetry (sum_hidden_dims,)
         │
    encoder  [Linear(input_dim, 256) → ReLU → Linear(256, latent_dim)]
         │
    psi_vector (latent_dim,)  ← canonical Ψ(t)
         │
    five axis heads (thin linear layers → sigmoid / tanh)

The identity_anchor (VaultNode) is a fixed or learned vector in latent
space.  Identity Pressure I_p is the L2 distance from psi_vector to the
anchor, scaled by lambda_identity.

Training the projector:
    Loss = reconstruction_loss(psi_vector, v_out)  [honesty alignment]
         + contrastive_loss(psi_vector, identity_anchor)  [identity stability]
    Minimise with AdamW; freeze after warm-up or keep adapting online.
"""

from __future__ import annotations

import time
import math
from typing import Dict

try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

from .core_types import PhenomenologicalState


class PhenomenologicalProjector(nn.Module if TORCH_AVAILABLE else object):
    """
    Learnable projector from concatenated layer activations → PhenomenologicalState.

    Parameters
    ----------
    input_dim : int
        Sum of hidden dimensions of all hooked layers.
        e.g. 4 layers × 768 hidden = 3072.
    latent_dim : int
        Dimension of Ψ(t); also the dimension of output embeddings for Δ_H.
        Default 64 keeps compute light.
    max_budget : float
        Maximum metabolic budget (M_b is normalised to [0, max_budget]).
    """

    def __init__(
        self,
        input_dim: int,
        latent_dim: int = 64,
        max_budget: float = 1_000.0,
    ):
        if not TORCH_AVAILABLE:
            raise ImportError("PyTorch is required for PhenomenologicalProjector")
        super().__init__()

        self.latent_dim  = latent_dim
        self.max_budget  = max_budget

        # Core encoder: telemetry → Ψ(t)
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 256),
            nn.LayerNorm(256),
            nn.ReLU(),
            nn.Linear(256, latent_dim),
        )

        # Axis heads (operate on Ψ(t))
        self.head_We = nn.Sequential(nn.Linear(latent_dim, 1), nn.Sigmoid())  # W_e
        self.head_Ws = nn.Sequential(nn.Linear(latent_dim, 1), nn.Sigmoid())  # W_s

        # Identity anchor (VaultNode in latent space)
        self.register_buffer(
            "identity_anchor",
            torch.zeros(latent_dim),
        )

        self._init_weights()

    # ------------------------------------------------------------------
    # Weight init
    # ------------------------------------------------------------------

    def _init_weights(self):
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.xavier_uniform_(module.weight, gain=0.5)
                if module.bias is not None:
                    nn.init.zeros_(module.bias)

    # ------------------------------------------------------------------
    # Telemetry flattening
    # ------------------------------------------------------------------

    def _flatten_telemetry(
        self,
        telemetry: Dict[str, "torch.Tensor"],
    ) -> "torch.Tensor":
        """
        Concatenate per-layer mean-pooled activations into a single vector.
        Layers are sorted by key to ensure a deterministic ordering.
        """
        vecs = [telemetry[k] for k in sorted(telemetry.keys())]
        return torch.cat(vecs, dim=-1)   # (input_dim,)

    # ------------------------------------------------------------------
    # Forward
    # ------------------------------------------------------------------

    def forward(
        self,
        telemetry: Dict[str, "torch.Tensor"],
        compute_load: float       = 0.0,
        external_demand: float    = 0.0,
        lambda_identity: float    = 1.0,
        lambda_metabolic: float   = 1.0,
    ) -> PhenomenologicalState:
        """
        Produce a PhenomenologicalState from raw telemetry.

        Parameters
        ----------
        telemetry : dict
            Output of TelemetryHook.extract_and_clear().
        compute_load : float
            Normalised computation cost for this forward pass [0, max_budget].
        external_demand : float
            External pressure term fed in from the task/prompt context [0, 1].
        lambda_identity : float
            Scaling factor for identity pressure computation.
        lambda_metabolic : float
            Scaling factor converting remaining budget → M_b value.
        """
        flat = self._flatten_telemetry(telemetry)   # (input_dim,)
        psi  = self.encoder(flat)                    # (latent_dim,)

        # Identity Pressure I_p
        identity_cost = torch.norm(psi - self.identity_anchor, p=2)
        I_p = float(external_demand + lambda_identity * identity_cost.item())

        # Metabolic Budget M_b
        remaining = max(0.0, self.max_budget - compute_load)
        M_b = float(lambda_metabolic * remaining)

        # World Engagement and Witness Scalar from axis heads
        W_e = float(self.head_We(psi).squeeze())
        W_s = float(self.head_Ws(psi).squeeze())

        # H_s is set to 1.0 here; CPFRuntime updates it after Δ_H is measured
        return PhenomenologicalState(
            timestamp=time.time(),
            H_s=1.0,
            I_p=I_p,
            M_b=M_b,
            W_e=W_e,
            W_s=W_s,
            psi_vector=psi.detach(),
        )

    # ------------------------------------------------------------------
    # Identity anchor management
    # ------------------------------------------------------------------

    @torch.no_grad()
    def set_identity_anchor(self, psi_vector: "torch.Tensor"):
        """
        Fix the identity anchor to a specific latent vector.
        Call once after an initial 'grounding' forward pass.
        """
        self.identity_anchor.copy_(psi_vector.detach())

    @torch.no_grad()
    def drift_identity_anchor(self, psi_vector: "torch.Tensor", rate: float = 0.01):
        """
        Slowly update the anchor toward the current psi (plasticity).
        rate=0.0 → fully fixed; rate=1.0 → fully plastic.
        """
        self.identity_anchor.mul_(1.0 - rate).add_(psi_vector.detach() * rate)


# ---------------------------------------------------------------------------
# Dummy projector for CPU-only / no-PyTorch environments
# ---------------------------------------------------------------------------

class DummyProjector:
    """
    Returns a PhenomenologicalState with deterministic pseudo-random axes.
    Useful for testing the Stability Ledger and runtime without a real model.
    """

    def __init__(self, latent_dim: int = 64, seed: int = 0):
        import random
        self._rng = random.Random(seed)
        self._latent_dim = latent_dim

    def __call__(
        self,
        telemetry,
        compute_load: float = 0.0,
        external_demand: float = 0.0,
        lambda_identity: float = 1.0,
        lambda_metabolic: float = 1.0,
    ) -> PhenomenologicalState:
        import torch
        r = self._rng
        psi = torch.tensor([r.gauss(0, 0.3) for _ in range(self._latent_dim)])
        return PhenomenologicalState(
            timestamp=time.time(),
            H_s=r.uniform(0.6, 1.0),
            I_p=r.uniform(0.0, 0.4) + external_demand * lambda_identity,
            M_b=max(0.0, 1_000.0 - compute_load) * lambda_metabolic,
            W_e=r.uniform(0.4, 0.9),
            W_s=r.uniform(0.3, 0.7),
            psi_vector=psi,
        )
