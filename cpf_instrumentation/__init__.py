"""
cpf_instrumentation — PyTorch-wired CPF measurement layer.

Wire to any HuggingFace-compatible model:

    from cpf_instrumentation import CPFRuntime, PhenomenologicalProjector
    from cpf_instrumentation import StabilityLedger, TelemetryHook, Recoupler

    hooks    = TelemetryHook(model.transformer.h[:4])   # grab first 4 blocks
    proj     = PhenomenologicalProjector(input_dim=4*768)
    ledger   = StabilityLedger("runs/ledger.jsonl")
    recoupler = Recoupler(mb_floor=0.1)
    runtime  = CPFRuntime(model, proj, ledger, recoupler)

    text, delta_H = runtime.generate(input_ids)
"""

from .core_types import PhenomenologicalState, LedgerEvent
from .telemetry_capture import TelemetryHook
from .projector import PhenomenologicalProjector
from .stability_ledger import StabilityLedger
from .recoupling_physics import Recoupler
from .cpf_runtime import CPFRuntime

__all__ = [
    "PhenomenologicalState",
    "LedgerEvent",
    "TelemetryHook",
    "PhenomenologicalProjector",
    "StabilityLedger",
    "Recoupler",
    "CPFRuntime",
]
