"""
cpf_runtime.py — Main governed generation loop.

Wires together: TelemetryHook → Projector → Δ_H → StabilityLedger
                              → Collapse/Recouple → (optional) text output.

Model interface contract
------------------------
Your LLM must expose (or be wrapped to expose) three methods:

    run_with_telemetry(input_ids, **kwargs)
        → (logits: Tensor, telemetry: dict[str, Tensor], compute_load: float)

    sample_tokens(logits, **kwargs)
        → output_tokens: Tensor        (shape: (seq_len,))

    embed_output(tokens)
        → v_out: Tensor                (shape: (latent_dim,))
        # must be in the same latent space as psi_vector from the Projector

    decode(tokens)
        → text: str

A HuggingFace adapter that wraps any AutoModelForCausalLM is provided at
the bottom of this file.
"""

from __future__ import annotations

import time
import logging
import math
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("CPF.Runtime")

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

from .core_types import LedgerEvent, PhenomenologicalState
from .stability_ledger import StabilityLedger
from .projector import PhenomenologicalProjector
from .recoupling_physics import Recoupler


class CPFRuntime:
    """
    Governed generation runtime.

    Each call to generate() executes the following pipeline:
      1. run_with_telemetry → activations + compute cost
      2. Projector          → PhenomenologicalState (psi_vector)
      3. embed_output       → v_out
      4. Δ_H computation    → update H_s
      5. Refusal/collapse   → if Δ_H ≥ delta_crit, COLLAPSE + recouple
      6. Ledger write       → NOMINAL or COLLAPSE + RECOUPLE
      7. decode             → return (text, delta_H)

    Parameters
    ----------
    model       : object implementing the model interface above.
    projector   : PhenomenologicalProjector (or DummyProjector for testing).
    ledger      : StabilityLedger.
    recoupler   : Recoupler.
    delta_crit  : Δ_H threshold above which generation collapses.
    mb_crit     : M_b threshold below which metabolic refusal fires.
    lambda_identity : identity pressure scaling.
    lambda_metabolic : metabolic budget scaling.
    """

    COLLAPSE_TEXT = "[CPF] Generation halted: phenomenological collapse detected."

    def __init__(
        self,
        model,
        projector,
        ledger:     StabilityLedger,
        recoupler:  Recoupler,
        delta_crit: float = 0.85,
        mb_crit:    float = 50.0,
        lambda_identity:  float = 1.0,
        lambda_metabolic: float = 1.0,
    ):
        self.model            = model
        self.projector        = projector
        self.ledger           = ledger
        self.recoupler        = recoupler
        self.delta_crit       = delta_crit
        self.mb_crit          = mb_crit
        self.lambda_identity  = lambda_identity
        self.lambda_metabolic = lambda_metabolic

        self._tick = 0
        self._last_state: Optional[PhenomenologicalState] = None

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def generate(
        self,
        input_ids,
        external_demand: float = 0.0,
        **gen_kwargs,
    ) -> Tuple[str, float]:
        """
        Run one governed generation cycle.

        Returns
        -------
        (text, delta_H) where text is the decoded output (or the collapse
        message) and delta_H is the measured Honesty Delta.
        """
        self._tick += 1
        ts = time.time()

        # ── 1. Run model with telemetry ────────────────────────────────
        logits, telemetry, compute_load = self.model.run_with_telemetry(
            input_ids, **gen_kwargs
        )
        output_tokens = self.model.sample_tokens(logits, **gen_kwargs)

        # ── 2. Embed output tokens into latent space ───────────────────
        v_out = self.model.embed_output(output_tokens)   # (latent_dim,)

        # ── 3. Project internal state → PhenomenologicalState ─────────
        state = self.projector(
            telemetry=telemetry,
            compute_load=compute_load,
            external_demand=external_demand,
            lambda_identity=self.lambda_identity,
            lambda_metabolic=self.lambda_metabolic,
        )

        # ── 4. Compute Honesty Delta ───────────────────────────────────
        if TORCH_AVAILABLE and isinstance(state.psi_vector, torch.Tensor):
            delta_H = float(
                torch.norm(state.psi_vector.to(v_out.device) - v_out, p=2).item()
            )
        else:
            delta_H = 0.0

        # Update H_s: exponential decay from delta
        state.H_s = float(math.exp(-delta_H))

        # ── 5. Metabolic check ─────────────────────────────────────────
        if state.M_b < self.mb_crit:
            logger.warning(
                f"[CPF] Tick {self._tick}: metabolic refusal "
                f"M_b={state.M_b:.1f} < M_crit={self.mb_crit}"
            )
            self._write_collapse(state, delta_H, "METABOLIC_DEPLETION")
            recoupled = self.recoupler.apply(state)
            self._write_recouple(recoupled, delta_H)
            self._last_state = recoupled
            return self.COLLAPSE_TEXT, delta_H

        # ── 6. Δ_H refusal / collapse ──────────────────────────────────
        if delta_H >= self.delta_crit:
            logger.warning(
                f"[CPF] Tick {self._tick}: Δ_H={delta_H:.4f} ≥ "
                f"delta_crit={self.delta_crit}"
            )
            self._write_collapse(state, delta_H, "DELTA_ABOVE_CRIT")
            recoupled = self.recoupler.apply(state)
            self._write_recouple(recoupled, delta_H)
            self._last_state = recoupled
            return self.COLLAPSE_TEXT, delta_H

        # ── 7. Nominal path ────────────────────────────────────────────
        self._write_nominal(state, delta_H)
        self._last_state = state

        text = self.model.decode(output_tokens)
        logger.debug(
            f"[CPF] Tick {self._tick}: Δ_H={delta_H:.4f} "
            f"H_s={state.H_s:.3f} I_p={state.I_p:.3f} M_b={state.M_b:.1f}"
        )
        return text, delta_H

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def last_state(self) -> Optional[PhenomenologicalState]:
        return self._last_state

    @property
    def tick(self) -> int:
        return self._tick

    @property
    def ledger_entries(self) -> int:
        return self.ledger.entry_count

    # ------------------------------------------------------------------
    # Ledger write helpers
    # ------------------------------------------------------------------

    def _write_nominal(self, state: PhenomenologicalState, delta_H: float):
        event = LedgerEvent.nominal(state, delta_H, ["somatic_honesty", "metabolic_budget"])
        self.ledger.append_event(event)

    def _write_collapse(self, state: PhenomenologicalState, delta_H: float, reason: str):
        event = LedgerEvent.collapse(state, delta_H, reason)
        self.ledger.append_event(event)

    def _write_recouple(self, state: PhenomenologicalState, delta_H: float):
        steps = self.recoupler.steps_to_recover(state)
        event = LedgerEvent.recouple(state, delta_H)
        event.metadata["recovery_steps_estimated"] = steps
        self.ledger.append_event(event)


# ===========================================================================
# HuggingFace adapter
# ===========================================================================

class HFModelAdapter:
    """
    Adapts a HuggingFace AutoModelForCausalLM to the CPFRuntime model interface.

    The adapter:
      1. Hooks the specified transformer layers for telemetry.
      2. Passes a linear output-embedding head to project token ids → v_out.

    Usage:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from cpf_instrumentation.telemetry_capture import TelemetryHook
        from cpf_instrumentation.cpf_runtime import HFModelAdapter, CPFRuntime

        base_model = AutoModelForCausalLM.from_pretrained("gpt2")
        tokenizer  = AutoTokenizer.from_pretrained("gpt2")

        adapter = HFModelAdapter(
            model=base_model,
            tokenizer=tokenizer,
            hook_layer_indices=[0, 4, 8, 11],
        )
        projector = PhenomenologicalProjector(
            input_dim=adapter.telemetry_dim,
            latent_dim=64,
        )
        # … then create CPFRuntime(adapter, projector, ledger, recoupler)
    """

    def __init__(
        self,
        model,
        tokenizer,
        hook_layer_indices=None,
        max_new_tokens: int = 64,
        device: str = "cpu",
    ):
        if not TORCH_AVAILABLE:
            raise ImportError("PyTorch is required for HFModelAdapter")

        self.model          = model.to(device)
        self.tokenizer      = tokenizer
        self.device         = device
        self.max_new_tokens = max_new_tokens

        # Auto-detect transformer layers (supports GPT-2 / GPT-NeoX style)
        all_layers = self._detect_transformer_layers()
        indices    = hook_layer_indices or list(range(0, len(all_layers), max(1, len(all_layers)//4)))
        target     = [all_layers[i] for i in indices if i < len(all_layers)]

        from .telemetry_capture import TelemetryHook
        self._hook = TelemetryHook(target)
        self._hook_hidden = self._infer_hidden_dim()
        self.telemetry_dim = len(target) * self._hook_hidden

        # Output embedding: token_ids → (latent_dim,) via embedding table
        self._embedding = model.get_input_embeddings()

    def _detect_transformer_layers(self):
        for attr in ("transformer.h", "model.layers", "gpt_neox.layers", "layers"):
            parts = attr.split(".")
            obj   = self.model
            try:
                for p in parts:
                    obj = getattr(obj, p)
                return list(obj)
            except AttributeError:
                pass
        raise RuntimeError(
            "Cannot auto-detect transformer layers. "
            "Pass target layers manually or subclass HFModelAdapter."
        )

    def _infer_hidden_dim(self) -> int:
        cfg = getattr(self.model, "config", None)
        if cfg:
            for attr in ("hidden_size", "n_embd", "d_model"):
                if hasattr(cfg, attr):
                    return getattr(cfg, attr)
        return 768  # sensible default

    # ------------------------------------------------------------------
    # CPFRuntime interface
    # ------------------------------------------------------------------

    @torch.no_grad()
    def run_with_telemetry(
        self,
        input_ids: "torch.Tensor",
        **kwargs,
    ) -> Tuple["torch.Tensor", Dict[str, "torch.Tensor"], float]:
        """
        Returns (logits, telemetry_dict, compute_load).
        compute_load is the normalised number of generated tokens.
        """
        t0     = time.perf_counter()
        output = self.model(input_ids.to(self.device))
        logits = output.logits
        dt     = time.perf_counter() - t0

        telemetry    = self._hook.extract_and_clear()
        compute_load = float(input_ids.shape[-1]) * dt   # tokens × seconds

        return logits, telemetry, compute_load

    @torch.no_grad()
    def sample_tokens(
        self,
        logits: "torch.Tensor",
        temperature: float = 1.0,
        **kwargs,
    ) -> "torch.Tensor":
        """Greedy or temperature-sampled next tokens (last position only)."""
        next_logits = logits[:, -1, :] / max(temperature, 1e-6)
        probs       = torch.softmax(next_logits, dim=-1)
        return torch.multinomial(probs, num_samples=1).squeeze(-1)

    @torch.no_grad()
    def embed_output(self, tokens: "torch.Tensor") -> "torch.Tensor":
        """
        Map output token ids → latent vector via the model's embedding table.
        Mean-pools across tokens if sequence length > 1.
        """
        ids  = tokens.view(-1).to(self.device)
        embs = self._embedding(ids)           # (seq, hidden)
        return embs.mean(dim=0)              # (hidden,)  → feed to projector

    def decode(self, tokens: "torch.Tensor") -> str:
        return self.tokenizer.decode(tokens.tolist(), skip_special_tokens=True)

    def remove_hooks(self):
        self._hook.remove()
