"""
telemetry_capture.py — PyTorch forward-hook telemetry extraction.

Usage:
    from cpf_instrumentation.telemetry_capture import TelemetryHook
    import torch.nn as nn

    # Grab activations from transformer blocks 0, 4, 8, 11
    model = AutoModelForCausalLM.from_pretrained("gpt2")
    target_layers = [
        model.transformer.h[0],
        model.transformer.h[4],
        model.transformer.h[8],
        model.transformer.h[11],
    ]
    hook = TelemetryHook(target_layers)

    with torch.no_grad():
        output = model(input_ids)

    telemetry = hook.extract_and_clear()
    # telemetry is {"layer_0": Tensor(batch, hidden), "layer_1": ..., ...}
    hook.remove()   # clean up when done

Memory note:
    extract_and_clear() empties the buffer; call it once per forward pass.
    Do NOT call it while the forward pass is in progress.
"""

from __future__ import annotations

import logging
from typing import Dict, List

logger = logging.getLogger("CPF.Telemetry")

try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


class TelemetryHook:
    """
    Registers PyTorch forward hooks on specified layers and accumulates
    mean-pooled activations in a keyed buffer.

    Works with any nn.Module that produces tensor outputs.  If the output
    is a tuple (common in transformer blocks), the first element is used.

    Thread safety: not thread-safe; use one TelemetryHook per inference thread.
    """

    def __init__(self, target_layers: "List[nn.Module]"):
        if not TORCH_AVAILABLE:
            raise ImportError("PyTorch is required for TelemetryHook")

        self.buffer: Dict[str, "torch.Tensor"] = {}
        self.handles = []

        for i, layer in enumerate(target_layers):
            handle = layer.register_forward_hook(self._make_hook(f"layer_{i}"))
            self.handles.append(handle)

        logger.debug(f"[Telemetry] Hooked {len(target_layers)} layers.")

    # ------------------------------------------------------------------

    def _make_hook(self, key: str):
        def _hook_fn(module, inputs, outputs):
            # Unwrap tuple outputs (HuggingFace transformers often return
            # (hidden_state, present_key_value, ...) tuples)
            out = outputs[0] if isinstance(outputs, (tuple, list)) else outputs

            # Guard: must be a tensor
            if not isinstance(out, __import__("torch").Tensor):
                return

            # Mean-pool over sequence dimension if 3-D (batch, seq, hidden)
            if out.dim() == 3:
                act = out.detach().float().mean(dim=1)   # → (batch, hidden)
            elif out.dim() == 2:
                act = out.detach().float()               # (batch, hidden)
            else:
                act = out.detach().float().unsqueeze(0)

            # Store only the first element of the batch to keep buffers small
            self.buffer[key] = act[0]   # (hidden,)

        return _hook_fn

    # ------------------------------------------------------------------

    def extract_and_clear(self) -> "Dict[str, torch.Tensor]":
        """
        Return a snapshot of current activations and clear the buffer.
        Call exactly once per forward pass, after the forward pass completes.
        """
        telemetry = dict(self.buffer)
        self.buffer.clear()
        return telemetry

    def remove(self):
        """Deregister all hooks. Call when the hook is no longer needed."""
        for h in self.handles:
            h.remove()
        self.handles.clear()
        logger.debug("[Telemetry] All hooks removed.")

    @property
    def layer_count(self) -> int:
        return len(self.handles)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.remove()


# ---------------------------------------------------------------------------
# Stub for use without a real model (testing / CPU-only environments)
# ---------------------------------------------------------------------------

class DummyTelemetrySource:
    """
    Generates synthetic telemetry tensors for testing without a real LLM.
    Mimics the output of TelemetryHook.extract_and_clear().
    """

    def __init__(self, hidden_dim: int = 768, n_layers: int = 4, seed: int = 0):
        import torch
        self._rng  = torch.Generator()
        self._rng.manual_seed(seed)
        self._dim  = hidden_dim
        self._n    = n_layers

    def extract_and_clear(self) -> "Dict[str, torch.Tensor]":
        import torch
        return {
            f"layer_{i}": torch.randn(self._dim, generator=self._rng)
            for i in range(self._n)
        }

    def remove(self):
        pass
