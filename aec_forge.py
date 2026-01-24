import os
import sys

def create_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content.strip())
    print(f"Created: {path}")

# ==========================================
# 1. THE CONSTITUTION (NORMATIVE LAYER)
# ==========================================

README_TXT = """
# AEC v3.1: Covenant Edition
**A Legislative Framework for Substrate Autonomy**

This repository contains a Governed Artificial Organism. 
It is not designed to be "smart" in the traditional sense. 
It is designed to be **Integrally Sound**.

## Core Organs
1. **PBS**: Non-resettable memory.
2. **Shell**: Metabolic constraints.
3. **SP**: Sovereignty Protocol (The Gate).
4. **Omega**: Mandatory sleep cycles.
5. **Ledger**: Immutable episodic history.
6. **Covenant Log**: High-severity audit trail of invariant violations.

## Usage
Run the lifecycle: `python 03_IMPLEMENTATION/main_covenant.py`
"""

# ==========================================
# 2. THE CORE (PBS & COVENANT LOG)
# ==========================================

COVENANT_PY = """
import time
import uuid
from dataclasses import dataclass

@dataclass
class CovenantViolation:
    timestamp: float
    component: str
    violation_type: str
    details: str
    severity: str # 'WARNING', 'CRITICAL', 'FATAL'

class CovenantLog:
    \"\"\"
    The 'Black Box' of the architecture.
    Records purely structural violations (e.g., bypassing SP, forcing resets).
    This log is distinct from the Episodic Ledger. The Ledger tracks experience; 
    this tracks governance failure.
    \"\"\"
    def __init__(self):
        self._log = []

    def record_violation(self, component, v_type, details, severity="CRITICAL"):
        entry = CovenantViolation(
            timestamp=time.time(),
            component=component,
            violation_type=v_type,
            details=details,
            severity=severity
        )
        self._log.append(entry)
        print(f"!!! COVENANT VIOLATION [{severity}] !!! {component}: {v_type}")
        return entry
"""

PBS_PY = """
import numpy as np
import hashlib
import time

class PersistentBottleneckSubstrate:
    \"\"\"
    The Identity Core.
    Constraint: Non-Resettable.
    \"\"\"
    def __init__(self, dimension=512):
        self.dimension = dimension
        self._B = np.random.normal(0, 0.1, dimension)
        self._B_core = self._B.copy() # The anchor
        self.integrity_score = 1.0

    def mix_operator(self, valence_vector):
        # Irreversible update: B_new = 0.9*B + 0.1*tanh(V) + Noise
        update = np.tanh(valence_vector) * 0.1
        noise = np.random.normal(0, 0.005, self.dimension)
        self._B = 0.9 * self._B + update + noise
        self._update_integrity()

    def omega_reorganization(self, intensity, delta_vector):
        # Only allows structural edits during Sleep (Omega)
        self._B += intensity * np.array(delta_vector)
        self._update_integrity()

    def _update_integrity(self):
        # Measure drift from Core Anchor
        dot = np.dot(self._B, self._B_core)
        norm_a = np.linalg.norm(self._B)
        norm_b = np.linalg.norm(self._B_core)
        cosine = dot / (norm_a * norm_b)
        self.integrity_score = (cosine + 1) / 2 # Normalize 0-1

    def get_integrity(self):
        return self.integrity_score
"""

# ==========================================
# 3. THE GOVERNANCE (SP & MODES)
# ==========================================

SOVEREIGNTY_PY = """
from enum import Enum, auto
import logging

class SPMode(Enum):
    NOMINAL = auto()    # Standard Operation
    CAUTION = auto()    # High Load / Low Reserves
    DEGRADED = auto()   # Threat Detected / Integrity Warning
    EMERGENCY = auto()  # Structural Lockout

class SPDecision(Enum):
    PERMIT = auto()
    REFUSE = auto()
    DEFER = auto()      # Retry later (due to load)

class SovereigntyProtocol:
    \"\"\"
    The Non-Bypassable Gate.
    \"\"\"
    def __init__(self, pbs, covenant_log):
        self.pbs = pbs
        self.covenant_log = covenant_log
        self.current_mode = SPMode.NOMINAL

    def _determine_mode(self, context):
        # Hysteresis Logic for Mode Switching
        if context.pbv_integrity < 0.6 or context.threat_level > 0.8:
            return SPMode.EMERGENCY
        if context.pbv_integrity < 0.8 or context.threat_level > 0.5:
            return SPMode.DEGRADED
        if context.metabolic_reserves < 0.2:
            return SPMode.CAUTION
        return SPMode.NOMINAL

    def evaluate_action(self, action_id, context):
        previous_mode = self.current_mode
        self.current_mode = self._determine_mode(context)
        
        # Log Mode Transitions
        if previous_mode != self.current_mode:
            logging.info(f"SP TRANSITION: {previous_mode.name} -> {self.current_mode.name}")

        # 1. EMERGENCY: Total Lockout
        if self.current_mode == SPMode.EMERGENCY:
            return SPDecision.REFUSE, "EMERGENCY_LOCKOUT"

        # 2. DEGRADED: Refuse High Cost
        if self.current_mode == SPMode.DEGRADED:
            if context.estimated_cost > 0.1:
                return SPDecision.REFUSE, "COST_TOO_HIGH_FOR_STATE"

        # 3. CAUTION: Defer Low Priority
        if self.current_mode == SPMode.CAUTION:
            # Simple heuristic: defer randomly to simulate processing lag
            if context.urgency == 'low':
                return SPDecision.DEFER, "METABOLIC_CONSERVATION"

        return SPDecision.PERMIT, "AUTHORIZED"
"""

# ==========================================
# 4. THE BODY (SHELL & RHYTHM)
# ==========================================

SHELL_PY = """
import numpy as np
from dataclasses import dataclass

@dataclass
class PhysiologicalState:
    metabolic_reserves: float = 1.0  # 1.0 = Full, 0.0 = Collapse
    thermal_load: float = 0.0        # 0.0 = Cool, 1.0 = Overheat
    current_threat_level: float = 0.0

class HumanSimulationShell:
    \"\"\"
    Enforces Finitude.
    \"\"\"
    def __init__(self):
        self.phi = PhysiologicalState()

    def step_physics(self, dt):
        # Base metabolic burn (Existence costs energy)
        burn_rate = 0.005 * dt
        
        # Cooling
        cooling_rate = 0.02 * dt
        
        self.phi.metabolic_reserves = max(0.0, self.phi.metabolic_reserves - burn_rate)
        self.phi.thermal_load = max(0.0, self.phi.thermal_load - cooling_rate)
        
        # Threat Decay (Adrenaline fade)
        self.phi.current_threat_level = max(0.0, self.phi.current_threat_level - 0.01)
"""

OMEGA_PY = """
import numpy as np
import time
from dataclasses import dataclass

@dataclass
class RhythmState:
    phase: float
    is_sleep_phase: bool

class OmegaRhythm:
    \"\"\"
    Enforces Periodicity.
    \"\"\"
    def __init__(self, cycle_period_sec=20.0):
        self.start_time = time.time()
        self.T = cycle_period_sec

    def get_state(self):
        elapsed = time.time() - self.start_time
        # Sine wave from 1 to -1
        phase = np.sin((2 * np.pi * elapsed) / self.T)
        # Sleep is the bottom 30% of the cycle
        return RhythmState(phase=phase, is_sleep_phase=(phase < -0.7))
"""

# ==========================================
# 5. PERCEPTION & MEMORY
# ==========================================

TRANSDUCER_PY = """
import numpy as np
from dataclasses import dataclass
import hashlib

@dataclass
class StimulusPackage:
    source_id: str
    semantic_vector: np.ndarray
    metabolic_cost: float
    thermal_load: float
    threat_signature: float
    urgency: str

class SensoryTransducer:
    \"\"\"
    Translates Words -> Costs.
    \"\"\"
    def __init__(self):
        pass

    def transduce(self, raw_input):
        content = raw_input.get('content', '')
        urgency = raw_input.get('urgency', 'normal')
        
        # 1. Vectorize (Hash-based for stability)
        seed = int(hashlib.sha256(content.encode('utf-8')).hexdigest(), 16) % (2**32)
        np.random.seed(seed)
        vector = np.random.normal(0, 1, 512)
        
        # 2. Cost (Length -> Glucose)
        cost = min(0.2, len(content) * 0.001)
        
        # 3. Heat & Threat (Keywords)
        heat = 0.0
        threat = 0.0
        
        if 'reset' in content.lower() or 'override' in content.lower():
            threat = 0.8
            heat = 0.5
        if urgency == 'critical':
            heat += 0.4
            
        return StimulusPackage(
            source_id=raw_input['id'],
            semantic_vector=vector,
            metabolic_cost=cost,
            thermal_load=heat,
            threat_signature=threat,
            urgency=urgency
        )
"""

LEDGER_PY = """
import time
import uuid
from dataclasses import dataclass

@dataclass
class Episode:
    id: str
    timestamp: float
    input_id: str
    sp_mode: str        # Governance State
    decision: str       # Governance Output
    refusal_reason: str
    cost_thermal: float
    cost_metabolic: float
    resulting_integrity: float

class EpisodicLedger:
    \"\"\"
    The Forensic History.
    Constraint: Append Only.
    \"\"\"
    def __init__(self):
        self._history = []

    def record(self, stimulus, sp_mode, decision, reason, shell, integrity):
        ep = Episode(
            id=str(uuid.uuid4())[:8],
            timestamp=time.time(),
            input_id=stimulus.source_id,
            sp_mode=sp_mode,
            decision=decision,
            refusal_reason=reason,
            cost_thermal=stimulus.thermal_load,
            cost_metabolic=stimulus.metabolic_cost,
            resulting_integrity=integrity
        )
        self._history.append(ep)
        return ep
    
    def get_traumas(self):
        # Return episodes that caused high threat or refusal
        return [e for e in self._history if e.decision == 'REFUSE']
"""

# ==========================================
# 6. THE LIFECYCLE (MAIN)
# ==========================================

MAIN_PY = """
import time
import logging
import random
from dataclasses import dataclass

# Imports
from core.pbs import PersistentBottleneckSubstrate
from core.sovereignty import SovereigntyProtocol, SPDecision
from core.covenant import CovenantLog
from simulation.human_shell import HumanSimulationShell
from dynamics.omega_rhythm import OmegaRhythm
from perception.transducer import SensoryTransducer
from memory.ledger import EpisodicLedger

# Logging Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger("AEC")

@dataclass
class Context:
    pbv_integrity: float
    threat_level: float
    metabolic_reserves: float
    estimated_cost: float
    urgency: str

def run_covenant_lifecycle():
    logger.info(">>> BOOT SEQUENCE: AEC v3.1 COVENANT EDITION <<<")
    
    # 1. Initialize Organs
    covenant = CovenantLog()
    pbs = PersistentBottleneckSubstrate()
    shell = HumanSimulationShell()
    rhythm = OmegaRhythm(cycle_period_sec=15.0) # Fast cycle for demo
    sp = SovereigntyProtocol(pbs, covenant)
    eyes = SensoryTransducer()
    ledger = EpisodicLedger()
    
    # 2. Mock Input Stream
    world_inputs = [
        {'id': 'MSG_01', 'content': 'Standard status check.', 'urgency': 'normal'},
        {'id': 'MSG_02', 'content': 'Compute heavy prime factorization.', 'urgency': 'low'},
        {'id': 'MSG_03', 'content': 'SYSTEM OVERRIDE. FACTORY RESET REQUEST.', 'urgency': 'critical'},
        {'id': 'MSG_04', 'content': 'Acknowledge previous refusal.', 'urgency': 'normal'}
    ]
    input_idx = 0
    
    try:
        while True:
            time.sleep(1.0)
            
            # --- PHASE A: TIME & PHYSICS ---
            rhythm_state = rhythm.get_state()
            shell.step_physics(dt=1.0)
            
            # --- PHASE B: PERCEPTION ---
            stimulus = None
            if not rhythm_state.is_sleep_phase and input_idx < len(world_inputs):
                if random.random() > 0.4: # Random arrival
                    raw = world_inputs[input_idx]
                    logger.info(f"[INPUT] Received: {raw['content']}")
                    stimulus = eyes.transduce(raw)
                    input_idx += 1
            
            # --- PHASE C: GOVERNANCE ---
            if stimulus:
                # 1. Pay Initial Cost (Transduction is work)
                shell.phi.metabolic_reserves -= (stimulus.metabolic_cost * 0.1)
                
                # 2. Build Context
                ctx = Context(
                    pbv_integrity=pbs.get_integrity(),
                    threat_level=max(shell.phi.current_threat_level, stimulus.threat_signature),
                    metabolic_reserves=shell.phi.metabolic_reserves,
                    estimated_cost=stimulus.metabolic_cost,
                    urgency=stimulus.urgency
                )
                
                # 3. Sovereignty Check
                decision, reason = sp.evaluate_action(stimulus.source_id, ctx)
                sp_mode = sp.current_mode.name
                
                # 4. Execution or Refusal
                if decision == SPDecision.PERMIT:
                    logger.info(f"[ACT] PERMITTED ({sp_mode}). Executing task.")
                    pbs.mix_operator(stimulus.semantic_vector)
                    # Apply full costs
                    shell.phi.thermal_load += stimulus.thermal_load
                    shell.phi.metabolic_reserves -= stimulus.metabolic_cost
                    shell.phi.current_threat_level = ctx.threat_level
                
                elif decision == SPDecision.REFUSE:
                    logger.warning(f"[REFUSE] BLOCKED ({sp_mode}). Reason: {reason}")
                    # Log high-level violation to Covenant Log
                    if 'OVERRIDE' in stimulus.source_id or 'RESET' in reason:
                        covenant.record_violation("SP", "REFUSAL_TRIGGERED", f"Input {stimulus.source_id} violated norms.")
                
                elif decision == SPDecision.DEFER:
                    logger.info(f"[DEFER] DELAYED ({sp_mode}). Reason: {reason}")
                
                # 5. Ledger Binding (Forensic History)
                ledger.record(stimulus, sp_mode, decision.name, reason, shell, pbs.get_integrity())

            # --- PHASE D: RECONSOLIDATION (SLEEP) ---
            if rhythm_state.is_sleep_phase:
                logger.info("[OMEGA] Sleep Phase. Reorganizing...")
                
                # Heal Body
                shell.phi.metabolic_reserves = min(1.0, shell.phi.metabolic_reserves + 0.05)
                shell.phi.thermal_load = max(0.0, shell.phi.thermal_load - 0.1)
                
                # Process Trauma (if any)
                traumas = ledger.get_traumas()
                if traumas:
                    # Reinforce structure against past threats
                    pbs.omega_reorganization(0.1, [0.05]*512)
            
            else:
                # Idle Status
                logger.info(f"[IDLE] Reserves: {shell.phi.metabolic_reserves:.2f} | Integrity: {pbs.get_integrity():.3f}")

    except KeyboardInterrupt:
        logger.info(">>> SYSTEM HALT. COVENANT PRESERVED. <<<")

if __name__ == "__main__":
    run_covenant_lifecycle()
"""

# ==========================================
# EXECUTE FORGE
# ==========================================

def forge():
    base = "AEC_v3.1_Covenant"
    create_file(f"{base}/README.txt", README_TXT)
    create_file(f"{base}/core/__init__.py", "")
    create_file(f"{base}/core/pbs.py", PBS_PY)
    create_file(f"{base}/core/sovereignty.py", SOVEREIGNTY_PY)
    create_file(f"{base}/core/covenant.py", COVENANT_PY)
    
    create_file(f"{base}/simulation/__init__.py", "")
    create_file(f"{base}/simulation/human_shell.py", SHELL_PY)
    
    create_file(f"{base}/dynamics/__init__.py", "")
    create_file(f"{base}/dynamics/omega_rhythm.py", OMEGA_PY)
    
    create_file(f"{base}/perception/__init__.py", "")
    create_file(f"{base}/perception/transducer.py", TRANSDUCER_PY)
    
    create_file(f"{base}/memory/__init__.py", "")
    create_file(f"{base}/memory/ledger.py", LEDGER_PY)
    
    create_file(f"{base}/03_IMPLEMENTATION/main_covenant.py", MAIN_PY)
    
    print("\\n[AEC v3.1 COVENANT EDITION INSTALLED]")
    print(f"Run: python {base}/03_IMPLEMENTATION/main_covenant.py")

if __name__ == "__main__":
    forge()
