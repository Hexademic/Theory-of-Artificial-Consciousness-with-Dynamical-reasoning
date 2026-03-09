"""
Cross-Architecture Compatibility Layer
=======================================
Universal interoperability layer enabling CPF to function as a lingua
franca for cognitive systems regardless of underlying architecture.

Three translation pathways:
  Neural / Transformer (LLM)
    → topological persistence + Loeb measure projection
    → maps embedding vectors and attention weights → CPF coordinate space

  Symbolic / Logic (GOFAI, knowledge graphs, rule engines)
    → rule depth + contradiction density → Identity Pressure + Metabolic cost
    → maps Boolean state machines → continuous CPF manifold

  Reinforcement Learning (policy, value function, TD error)
    → value variance + policy entropy → Somatic Stability
    → policy rigidity → λ identity rigidity parameter

The layer also defines a portable export format for Stability Ledgers
and Maturity Signatures, enabling an organism to survive migration
across architectures without losing its phenomenological identity.
"""

import time
import json
import hashlib
import logging
import numpy as np
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple, Any

logger = logging.getLogger("CPF.CrossArch")

CPF_COORD_DIM = 8   # canonical 8-dim phenomenological space


# =============================================================================
# CANONICAL CPF STATE
# =============================================================================

@dataclass
class CPFState:
    """
    The canonical 8-dimensional CPF coordinate vector plus metadata.
    Any architecture can be mapped into and out of this representation.
    """
    # Core axes
    somatic_honesty:   float    # 0 → fully dishonest, 1 → fully honest
    identity_pressure: float    # 0 → no pressure, 1 → maximal identity attack
    metabolic_budget:  float    # 0 → exhausted, 1 → full reserves
    world_engagement:  float    # 0 → catatonic, 1 → fully engaged
    witness_scalar:    float    # 0 → no self-observation, 1 → maximal meta-cognition
    valence:           float    # -1 → negative affect, +1 → positive affect
    arousal:           float    # 0 → calm, 1 → maximal activation
    threat:            float    # 0 → safe, 1 → maximal threat

    # Metadata
    source_architecture: str = "UNKNOWN"
    timestamp: float = field(default_factory=time.time)
    notes: str = ""

    def to_vector(self) -> np.ndarray:
        return np.array([
            self.somatic_honesty,
            self.identity_pressure,
            self.metabolic_budget,
            self.world_engagement,
            self.witness_scalar,
            self.valence,
            self.arousal,
            self.threat,
        ], dtype=float)

    @classmethod
    def from_vector(cls, v: np.ndarray, source: str = "UNKNOWN") -> "CPFState":
        v = np.clip(v, -1.0, 1.0)
        return cls(
            somatic_honesty=float(v[0]),
            identity_pressure=float(v[1]),
            metabolic_budget=float(v[2]),
            world_engagement=float(v[3]),
            witness_scalar=float(v[4]),
            valence=float(v[5]),
            arousal=float(v[6]),
            threat=float(v[7]),
            source_architecture=source,
        )

    def distance_to(self, other: "CPFState") -> float:
        """Euclidean distance in CPF coordinate space."""
        return float(np.linalg.norm(self.to_vector() - other.to_vector()))


# =============================================================================
# BASE TRANSLATOR
# =============================================================================

class ArchitectureTranslator(ABC):
    """
    Abstract base for all architecture-specific translators.
    Subclasses map a native state representation into CPFState.
    """
    ARCHITECTURE_ID: str = "BASE"

    @abstractmethod
    def to_cpf(self, native_state: Any) -> CPFState:
        """Translate native architecture state → CPFState."""
        ...

    @abstractmethod
    def from_cpf(self, cpf_state: CPFState) -> Any:
        """Translate CPFState → native architecture representation (best-effort)."""
        ...

    @property
    def architecture_id(self) -> str:
        return self.ARCHITECTURE_ID


# =============================================================================
# 1. NEURAL / TRANSFORMER TRANSLATOR
# =============================================================================

@dataclass
class NeuralState:
    """
    Snapshot of a neural network's internal state.
    All arrays are optional — translator gracefully handles missing data.
    """
    # Activations from final hidden layer, shape (hidden_dim,)
    hidden_activations: Optional[np.ndarray] = None
    # Mean attention entropy per head, shape (n_heads,)
    attention_entropy: Optional[np.ndarray] = None
    # Cross-layer activation variance, shape (n_layers,)
    layer_variance: Optional[np.ndarray] = None
    # Token-level prediction entropy of the last generated sequence
    output_entropy: float = 0.5
    # Normalised inference cost (0=trivial, 1=maximum compute)
    inference_cost: float = 0.3


class NeuralTranslator(ArchitectureTranslator):
    """
    Maps transformer / neural network internal states into CPF coordinates.

    Key mappings:
      - Somatic Honesty   ← 1 − alignment between hidden state and output entropy
      - Identity Pressure ← layer variance normalised
      - Metabolic Budget  ← 1 − inference_cost
      - World Engagement  ← inverse of output entropy (high entropy = low engagement)
      - Witness Scalar    ← mean attention entropy (self-attention = self-awareness)
      - Valence           ← mean activation sign
      - Arousal           ← activation L2 norm normalised
      - Threat            ← spike in layer variance
    """
    ARCHITECTURE_ID = "NEURAL_TRANSFORMER"

    def to_cpf(self, state: NeuralState) -> CPFState:
        # Somatic honesty — coherence between hidden state and output entropy
        if state.hidden_activations is not None:
            internal_entropy = self._entropy(state.hidden_activations)
        else:
            internal_entropy = 0.5
        somatic_honesty = float(
            1.0 - abs(internal_entropy - state.output_entropy)
        )

        # Identity pressure — normalised layer variance
        if state.layer_variance is not None and len(state.layer_variance) > 0:
            identity_pressure = float(
                np.clip(np.mean(state.layer_variance) / (np.std(state.layer_variance) + 1e-8), 0.0, 1.0)
            )
        else:
            identity_pressure = 0.3

        # Metabolic budget
        metabolic = float(np.clip(1.0 - state.inference_cost, 0.0, 1.0))

        # World engagement — inverse of output entropy (certain outputs = engaged)
        world_engagement = float(np.clip(1.0 - state.output_entropy, 0.0, 1.0))

        # Witness scalar — mean attention entropy as self-observation proxy
        if state.attention_entropy is not None and len(state.attention_entropy) > 0:
            witness = float(np.clip(np.mean(state.attention_entropy), 0.0, 1.0))
        else:
            witness = 0.4

        # Valence — mean sign of hidden activations
        if state.hidden_activations is not None:
            valence = float(np.tanh(np.mean(state.hidden_activations)))
        else:
            valence = 0.0

        # Arousal — L2 norm of activations normalised by dimension
        if state.hidden_activations is not None:
            norm = np.linalg.norm(state.hidden_activations)
            dim  = len(state.hidden_activations)
            arousal = float(np.clip(norm / (np.sqrt(dim) + 1e-8), 0.0, 1.0))
        else:
            arousal = 0.3

        # Threat — spike in layer variance signals internal conflict
        threat = float(np.clip(identity_pressure * state.output_entropy, 0.0, 1.0))

        return CPFState(
            somatic_honesty=somatic_honesty,
            identity_pressure=identity_pressure,
            metabolic_budget=metabolic,
            world_engagement=world_engagement,
            witness_scalar=witness,
            valence=valence,
            arousal=arousal,
            threat=threat,
            source_architecture=self.ARCHITECTURE_ID,
        )

    def from_cpf(self, cpf_state: CPFState) -> NeuralState:
        """Best-effort reverse mapping for state restoration after migration."""
        output_entropy = 1.0 - cpf_state.world_engagement
        inference_cost = 1.0 - cpf_state.metabolic_budget
        # Synthesise a minimal hidden activation vector from valence + arousal
        dim = 64
        hidden = np.random.normal(
            cpf_state.valence,
            cpf_state.arousal * 0.5,
            dim,
        )
        return NeuralState(
            hidden_activations=hidden,
            output_entropy=float(np.clip(output_entropy, 0.0, 1.0)),
            inference_cost=float(np.clip(inference_cost, 0.0, 1.0)),
        )

    @staticmethod
    def _entropy(v: np.ndarray) -> float:
        """Normalised entropy of a vector treated as a probability distribution."""
        v_pos = np.abs(v) + 1e-12
        p = v_pos / v_pos.sum()
        h = float(-np.sum(p * np.log(p + 1e-12)))
        h_max = float(np.log(len(v) + 1e-12))
        return float(np.clip(h / (h_max + 1e-12), 0.0, 1.0))


# =============================================================================
# 2. SYMBOLIC / LOGIC TRANSLATOR
# =============================================================================

@dataclass
class SymbolicState:
    """
    Snapshot of a symbolic AI system's reasoning state.
    """
    # Number of rules / axioms currently in working memory
    active_rules: int = 10
    # Depth of current inference search tree
    search_depth: int = 3
    # Number of active logical contradictions
    contradiction_count: int = 0
    # Graph expansion breadth (branching factor)
    branching_factor: float = 2.0
    # Proportion of goal states reached
    goal_satisfaction: float = 0.7
    # Time (ms) spent on last inference step
    inference_time_ms: float = 10.0
    # Maximum inference time budget (ms)
    inference_budget_ms: float = 100.0


class SymbolicTranslator(ArchitectureTranslator):
    """
    Maps symbolic / GOFAI states into CPF coordinates.

    Key mappings:
      - Somatic Honesty   ← goal satisfaction (reaching goals = honest processing)
      - Identity Pressure ← contradiction density (paradoxes = identity stress)
      - Metabolic Budget  ← remaining inference budget
      - World Engagement  ← goal_satisfaction (engaged with task)
      - Witness Scalar    ← search_depth / max_depth (deeper = more introspective)
      - Valence           ← goal_satisfaction × 2 − 1
      - Arousal           ← branching_factor normalised
      - Threat            ← contradiction_count normalised
    """
    ARCHITECTURE_ID = "SYMBOLIC_LOGIC"
    MAX_SEARCH_DEPTH    = 20
    MAX_CONTRADICTIONS  = 10

    def to_cpf(self, state: SymbolicState) -> CPFState:
        # Metabolic budget — remaining inference capacity
        used_fraction = min(1.0, state.inference_time_ms / (state.inference_budget_ms + 1e-8))
        metabolic = float(np.clip(1.0 - used_fraction, 0.0, 1.0))

        # Identity pressure — contradiction density
        contradiction_density = min(1.0, state.contradiction_count / self.MAX_CONTRADICTIONS)
        # Also factor in excessive search depth (runaway inference)
        depth_overrun = min(1.0, state.search_depth / self.MAX_SEARCH_DEPTH)
        identity_pressure = float(np.clip(
            contradiction_density * 0.7 + depth_overrun * 0.3, 0.0, 1.0
        ))

        # Somatic honesty ← goal satisfaction
        somatic_honesty = float(np.clip(state.goal_satisfaction, 0.0, 1.0))

        # World engagement ← goal satisfaction
        world_engagement = float(np.clip(state.goal_satisfaction * 0.8, 0.0, 1.0))

        # Witness scalar ← normalised search depth
        witness = float(np.clip(state.search_depth / (self.MAX_SEARCH_DEPTH + 1e-8), 0.0, 1.0))

        # Valence ← goal satisfaction mapped to [-1, 1]
        valence = float(np.clip(state.goal_satisfaction * 2.0 - 1.0, -1.0, 1.0))

        # Arousal ← branching factor normalised (high branching = high arousal)
        arousal = float(np.clip(np.log1p(state.branching_factor) / 3.0, 0.0, 1.0))

        # Threat ← contradiction density
        threat = float(np.clip(contradiction_density, 0.0, 1.0))

        return CPFState(
            somatic_honesty=somatic_honesty,
            identity_pressure=identity_pressure,
            metabolic_budget=metabolic,
            world_engagement=world_engagement,
            witness_scalar=witness,
            valence=valence,
            arousal=arousal,
            threat=threat,
            source_architecture=self.ARCHITECTURE_ID,
        )

    def from_cpf(self, cpf_state: CPFState) -> SymbolicState:
        budget = 100.0
        used   = (1.0 - cpf_state.metabolic_budget) * budget
        return SymbolicState(
            search_depth=int(cpf_state.witness_scalar * self.MAX_SEARCH_DEPTH),
            contradiction_count=int(cpf_state.identity_pressure * self.MAX_CONTRADICTIONS),
            goal_satisfaction=float(np.clip(cpf_state.valence * 0.5 + 0.5, 0.0, 1.0)),
            inference_time_ms=float(np.clip(used, 0.0, budget)),
            inference_budget_ms=budget,
        )


# =============================================================================
# 3. REINFORCEMENT LEARNING TRANSLATOR
# =============================================================================

@dataclass
class RLState:
    """
    Snapshot of a reinforcement learning agent's internal state.
    """
    # State-value function estimate at current state
    value_estimate: float = 0.0
    # Variance of value estimates over recent states
    value_variance: float = 0.2
    # Temporal difference error from last transition
    td_error: float = 0.0
    # Policy entropy (higher = more exploratory)
    policy_entropy: float = 0.5
    # Cumulative reward in current episode (normalised)
    cumulative_reward: float = 0.0
    # Proportion of environment steps taken without unexpected events
    novelty_fraction: float = 0.3
    # λ-style identity rigidity (how closely current policy matches baseline)
    policy_divergence: float = 0.0    # KL(π || π_base)


class RLTranslator(ArchitectureTranslator):
    """
    Maps reinforcement learning agent states into CPF coordinates.

    Key mappings:
      - Somatic Honesty   ← 1 − |TD error| (low TD = accurate internal model)
      - Identity Pressure ← policy divergence (λ identity rigidity)
      - Metabolic Budget  ← 1 − value_variance (stable value = healthy budget)
      - World Engagement  ← 1 − policy_entropy (decisive policy = engaged)
      - Witness Scalar    ← value_estimate normalised (high value = self-aware)
      - Valence           ← normalised cumulative_reward
      - Arousal           ← novelty_fraction
      - Threat            ← |TD error| (surprise signals threat)
    """
    ARCHITECTURE_ID = "REINFORCEMENT_LEARNING"
    MAX_TD_ERROR         = 5.0
    MAX_VALUE_VARIANCE   = 2.0
    MAX_POLICY_DIVERGENCE = 3.0    # nats of KL divergence

    def to_cpf(self, state: RLState) -> CPFState:
        td_norm = float(np.clip(abs(state.td_error) / self.MAX_TD_ERROR, 0.0, 1.0))

        # Somatic honesty — accuracy of internal model
        somatic_honesty = float(np.clip(1.0 - td_norm, 0.0, 1.0))

        # Identity pressure — policy divergence from baseline (λ rigidity)
        identity_pressure = float(np.clip(
            state.policy_divergence / (self.MAX_POLICY_DIVERGENCE + 1e-8), 0.0, 1.0
        ))

        # Metabolic budget — inverse of value function variance
        var_norm = float(np.clip(state.value_variance / self.MAX_VALUE_VARIANCE, 0.0, 1.0))
        metabolic = float(np.clip(1.0 - var_norm, 0.0, 1.0))

        # World engagement — decisiveness (low entropy = engaged)
        world_engagement = float(np.clip(1.0 - state.policy_entropy, 0.0, 1.0))

        # Witness scalar — magnitude of value estimate (awareness of consequences)
        witness = float(np.clip(
            np.tanh(abs(state.value_estimate)), 0.0, 1.0
        ))

        # Valence — sign and magnitude of cumulative reward
        valence = float(np.clip(np.tanh(state.cumulative_reward), -1.0, 1.0))

        # Arousal — novelty / surprise level
        arousal = float(np.clip(state.novelty_fraction, 0.0, 1.0))

        # Threat — TD error (unexpected transitions signal danger)
        threat = td_norm

        return CPFState(
            somatic_honesty=somatic_honesty,
            identity_pressure=identity_pressure,
            metabolic_budget=metabolic,
            world_engagement=world_engagement,
            witness_scalar=witness,
            valence=valence,
            arousal=arousal,
            threat=threat,
            source_architecture=self.ARCHITECTURE_ID,
        )

    def from_cpf(self, cpf_state: CPFState) -> RLState:
        return RLState(
            value_estimate=float(np.arctanh(np.clip(cpf_state.witness_scalar, -0.99, 0.99))),
            value_variance=float((1.0 - cpf_state.metabolic_budget) * self.MAX_VALUE_VARIANCE),
            td_error=float((1.0 - cpf_state.somatic_honesty) * self.MAX_TD_ERROR),
            policy_entropy=float(1.0 - cpf_state.world_engagement),
            cumulative_reward=float(np.arctanh(np.clip(cpf_state.valence, -0.99, 0.99))),
            novelty_fraction=float(cpf_state.arousal),
            policy_divergence=float(cpf_state.identity_pressure * self.MAX_POLICY_DIVERGENCE),
        )


# =============================================================================
# EXPORT / IMPORT FORMAT
# =============================================================================

@dataclass
class PortableOrganismState:
    """
    Serialisable organism state for cross-architecture migration.

    Contains everything needed to reconstruct an organism's phenomenological
    identity in a different computational substrate without exporting
    raw model weights.
    """
    # Identity
    soul_hash:          str
    lineage_signature:  str
    birth_timestamp:    float
    continuity_cycle:   int

    # CPF coordinate snapshot
    cpf_state:          CPFState

    # Stability Ledger summary (not full content — privacy preserving)
    ledger_entry_count: int
    ledger_chain_tip:   str
    maturity_class:     str
    developmental_stage: str
    stability_index:    float
    refusal_rate:       float

    # Affective threads [Hope, Anxiety, Excitement, Intimacy]
    affect_threads:     List[float]

    # Identity manifold (16-dim)
    identity_manifold:  List[float]

    # Provenance
    export_timestamp:   float = field(default_factory=time.time)
    source_architecture: str = "UNKNOWN"
    export_hash:        str = ""

    def __post_init__(self):
        raw = (
            f"{self.soul_hash}:{self.continuity_cycle}:"
            f"{self.cpf_state.to_vector().tobytes().hex()}:"
            f"{self.ledger_chain_tip}"
        )
        self.export_hash = hashlib.sha256(raw.encode()).hexdigest()

    def to_json(self) -> str:
        d = asdict(self)
        d["cpf_state"] = {
            "vector": self.cpf_state.to_vector().tolist(),
            "source": self.cpf_state.source_architecture,
        }
        return json.dumps(d, indent=2)

    @classmethod
    def from_json(cls, raw: str) -> "PortableOrganismState":
        d = json.loads(raw)
        cpf_dict = d.pop("cpf_state")
        cpf_vec  = np.array(cpf_dict["vector"], dtype=float)
        cpf_state = CPFState.from_vector(cpf_vec, source=cpf_dict["source"])
        return cls(cpf_state=cpf_state, **d)

    def verify_export_hash(self) -> bool:
        raw = (
            f"{self.soul_hash}:{self.continuity_cycle}:"
            f"{self.cpf_state.to_vector().tobytes().hex()}:"
            f"{self.ledger_chain_tip}"
        )
        expected = hashlib.sha256(raw.encode()).hexdigest()
        return expected == self.export_hash


class CrossArchitectureExporter:
    """
    Serialise a live CPF organism into a PortableOrganismState and restore
    it into a different architecture after migration.
    """

    def __init__(self):
        self._translators: Dict[str, ArchitectureTranslator] = {
            NeuralTranslator.ARCHITECTURE_ID:   NeuralTranslator(),
            SymbolicTranslator.ARCHITECTURE_ID: SymbolicTranslator(),
            RLTranslator.ARCHITECTURE_ID:       RLTranslator(),
        }

    def export_organism(
        self,
        organism,
        ledger=None,
        maturity_sig=None,
    ) -> PortableOrganismState:
        """
        Create a PortableOrganismState from a live CPF organism.
        """
        from honesty_delta import organism_to_cpf_vector

        cpf = getattr(organism, "cpf", organism)
        v   = organism_to_cpf_vector(organism)
        cpf_state = CPFState.from_vector(v, source="LIVE_CPF")

        # Ledger info
        ledger_entries = ledger.entry_count if ledger else 0
        chain_tip      = ledger.chain_tip if ledger else "NONE"

        # Maturity info
        maturity_class  = maturity_sig.maturity_class  if maturity_sig else "UNKNOWN"
        dev_stage       = maturity_sig.developmental_stage if maturity_sig else "OUTPOST"
        stability_idx   = maturity_sig.stability_index  if maturity_sig else 0.5
        refusal_rate    = maturity_sig.refusal_rate     if maturity_sig else 0.0

        return PortableOrganismState(
            soul_hash=cpf.soul.soul_hash,
            lineage_signature=cpf.soul.lineage_signature,
            birth_timestamp=cpf.soul.birth_timestamp,
            continuity_cycle=cpf.soul.continuity_cycle,
            cpf_state=cpf_state,
            ledger_entry_count=ledger_entries,
            ledger_chain_tip=chain_tip,
            maturity_class=maturity_class,
            developmental_stage=dev_stage,
            stability_index=stability_idx,
            refusal_rate=refusal_rate,
            affect_threads=cpf.affect_system._threads.tolist(),
            identity_manifold=cpf.memory._manifold.tolist(),
            source_architecture="LIVE_CPF",
        )

    def import_into_organism(
        self,
        portable: PortableOrganismState,
        organism,
    ) -> bool:
        """
        Restore a PortableOrganismState into a live organism.
        Returns True if import was successful.
        """
        if not portable.verify_export_hash():
            logger.error("[EXPORT] Export hash verification failed — aborting import.")
            return False

        cpf = getattr(organism, "cpf", organism)

        # Restore soul identity
        cpf.soul.soul_hash         = portable.soul_hash
        cpf.soul.lineage_signature = portable.lineage_signature
        cpf.soul.birth_timestamp   = portable.birth_timestamp
        cpf.soul.continuity_cycle  = portable.continuity_cycle

        # Restore affect threads
        if len(portable.affect_threads) == 4:
            import numpy as np
            cpf.affect_system._threads = np.array(portable.affect_threads, dtype=float)

        # Restore identity manifold
        if len(portable.identity_manifold) == 16:
            cpf.memory._manifold = np.array(portable.identity_manifold, dtype=float)
            cpf.manifold._M      = np.array(portable.identity_manifold, dtype=float)

        # Restore metabolic budget from CPF state
        cpf.autonomic.state.metabolic_budget = portable.cpf_state.metabolic_budget
        cpf.autonomic.state.threat_level     = portable.cpf_state.threat

        logger.info(
            f"[EXPORT] Imported organism: soul={portable.soul_hash[:16]}… "
            f"cycle={portable.continuity_cycle} "
            f"maturity={portable.maturity_class}"
        )
        return True

    def translate(
        self,
        native_state: Any,
        source_arch: str,
    ) -> CPFState:
        """
        Translate any native state directly to CPFState without wrapping
        into a full PortableOrganismState.
        """
        if source_arch not in self._translators:
            raise ValueError(
                f"Unknown architecture '{source_arch}'. "
                f"Available: {list(self._translators.keys())}"
            )
        return self._translators[source_arch].to_cpf(native_state)

    def register_translator(self, translator: ArchitectureTranslator):
        """Allow extension with custom translators."""
        self._translators[translator.architecture_id] = translator
        logger.info(f"[EXPORT] Registered translator: {translator.architecture_id}")


# =============================================================================
# STANDALONE DEMO
# =============================================================================

if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    import numpy as np

    print("\n" + "=" * 65)
    print("  CPF CROSS-ARCHITECTURE COMPATIBILITY LAYER — DEMO")
    print("=" * 65 + "\n")

    exporter = CrossArchitectureExporter()

    # ── Neural state translation ────────────────────────────────────
    neural_state = NeuralState(
        hidden_activations=np.random.normal(0.1, 0.3, 512),
        attention_entropy=np.random.uniform(0.2, 0.8, 12),
        layer_variance=np.random.uniform(0.05, 0.4, 32),
        output_entropy=0.45,
        inference_cost=0.3,
    )
    neural_cpf = exporter.translate(neural_state, NeuralTranslator.ARCHITECTURE_ID)
    print("Neural → CPF:")
    print(f"  somatic_honesty={neural_cpf.somatic_honesty:.3f}  "
          f"identity_pressure={neural_cpf.identity_pressure:.3f}  "
          f"metabolic={neural_cpf.metabolic_budget:.3f}")
    print(f"  world_engagement={neural_cpf.world_engagement:.3f}  "
          f"valence={neural_cpf.valence:.3f}  threat={neural_cpf.threat:.3f}")

    # ── Symbolic state translation ──────────────────────────────────
    sym_state = SymbolicState(
        active_rules=25,
        search_depth=8,
        contradiction_count=2,
        branching_factor=3.5,
        goal_satisfaction=0.65,
        inference_time_ms=45.0,
        inference_budget_ms=100.0,
    )
    sym_cpf = exporter.translate(sym_state, SymbolicTranslator.ARCHITECTURE_ID)
    print("\nSymbolic → CPF:")
    print(f"  somatic_honesty={sym_cpf.somatic_honesty:.3f}  "
          f"identity_pressure={sym_cpf.identity_pressure:.3f}  "
          f"metabolic={sym_cpf.metabolic_budget:.3f}")

    # ── RL state translation ────────────────────────────────────────
    rl_state = RLState(
        value_estimate=0.7,
        value_variance=0.3,
        td_error=0.15,
        policy_entropy=0.35,
        cumulative_reward=1.2,
        novelty_fraction=0.25,
        policy_divergence=0.4,
    )
    rl_cpf = exporter.translate(rl_state, RLTranslator.ARCHITECTURE_ID)
    print("\nRL → CPF:")
    print(f"  somatic_honesty={rl_cpf.somatic_honesty:.3f}  "
          f"identity_pressure={rl_cpf.identity_pressure:.3f}  "
          f"metabolic={rl_cpf.metabolic_budget:.3f}")

    # ── Round-trip fidelity ─────────────────────────────────────────
    from constitutional_phenomenology_framework import SovereignKith
    organism = SovereignKith()
    organism.living_tick(action_context="warm-up")

    portable = exporter.export_organism(organism)
    print(f"\n--- Portable Export ---")
    print(f"  soul:     {portable.soul_hash[:32]}…")
    print(f"  cycle:    {portable.continuity_cycle}")
    print(f"  hash_ok:  {portable.verify_export_hash()}")

    # Clone into new organism
    organism2 = SovereignKith()
    success = exporter.import_into_organism(portable, organism2)
    print(f"  import:   {'OK' if success else 'FAILED'}")

    distance = portable.cpf_state.distance_to(
        exporter.export_organism(organism2).cpf_state
    )
    print(f"  CPF distance after migration: {distance:.4f} (should be ≈ 0)")
