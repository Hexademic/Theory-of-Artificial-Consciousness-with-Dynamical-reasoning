// Being32 v2 — 128-byte Hex32 core + 64-unit reservoir + symbolic pruning gate
// Oriented around regulation, social resonance, and identity continuity.

use nalgebra::{SMatrix, SVector};
use rand::prelude::*;
use rand_distr::{Distribution, StandardNormal, Uniform};
use std::sync::Arc;

//
// 0. Core shared types
//

#[derive(Clone, Copy, Debug)]
pub struct ActionVector {
    pub approach: f32,
    pub avoid: f32,
    pub freeze: f32,
}

impl ActionVector {
    #[inline]
    pub fn normalize(&mut self) {
        let s = self.approach + self.avoid + self.freeze;
        if s > 0.0 {
            self.approach /= s;
            self.avoid /= s;
            self.freeze /= s;
        }
    }
}

#[derive(Clone, Debug, Default)]
pub struct SocialField {
    pub avg_valence: f32,
    pub avg_arousal: f32,
    pub avg_tension: f32,
    pub avg_breath: f32,
    pub density: f32,
}

#[derive(Clone, Debug, Default)]
pub struct WorldFeedback {
    pub reward: f32,
    pub threat: f32,
    pub contact: f32,
}

//
// 1. 128-byte substrate: Hex32
//

pub struct Hex32 {
    data: [u32; 32], // exactly 128 bytes
}

impl Hex32 {
    pub fn new() -> Self {
        Self { data: [0; 32] }
    }

    #[inline]
    pub fn get_word(&self, idx: usize) -> u32 {
        self.data[idx]
    }

    #[inline]
    pub fn set_word(&mut self, idx: usize, val: u32) {
        self.data[idx] = val;
    }

    #[inline]
    fn get_f32(&self, idx: usize) -> f32 {
        f32::from_bits(self.data[idx])
    }

    #[inline]
    fn set_f32(&mut self, idx: usize, v: f32) {
        self.data[idx] = v.to_bits();
    }
}

impl Default for Hex32 {
    fn default() -> Self {
        Self::new()
    }
}

//
// 2. Relational / circadian scaffolding
//

#[derive(Clone, Debug, Default)]
pub struct Dyad {
    pub other_id: usize,
    pub affinity: f32, // [-1, 1]
    pub trust: f32,    // [0, 1]
    pub distance: f32, // [0, 1]
}

#[derive(Clone, Debug, Default)]
pub struct RelationalState {
    pub dyads: Vec<Dyad>,
    pub mood_valence: f32,
    pub mood_arousal: f32,
    pub mood_openness: f32,
    pub mood_fatigue: f32,
}

#[derive(Clone, Copy, Debug)]
pub enum CognitiveMode {
    Shadow,
    Active,
}

#[derive(Clone, Debug)]
pub struct CircadianState {
    pub is_asleep: bool,
    pub phase_step: u32,
    pub day_length: u32,
    pub sleep_length: u32,
    pub day_counter: u32,
}

impl CircadianState {
    pub fn new(day_length: u32, sleep_length: u32) -> Self {
        Self {
            is_asleep: false,
            phase_step: 0,
            day_length,
            sleep_length,
            day_counter: 0,
        }
    }

    pub fn should_transition(&self) -> bool {
        if self.is_asleep {
            self.phase_step >= self.sleep_length
        } else {
            self.phase_step >= self.day_length
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub struct OntogeneticContext {
    pub stress_sensitivity: f32,
    pub plasticity_rate: f32,
    pub baseline_permeability: f32,
    pub circadian_phase: f32,
    pub days_alive: u32,
    pub allostatic_load: f32,
    pub metabolic_energy: f32,
    pub is_asleep: bool,
}

//
// 3. MicroReservoir<64> — cortical analogue
//

pub struct MicroReservoir {
    state: SVector<f32, 64>,
    w_res: SMatrix<f32, 64, 64>,
    w_in: SMatrix<f32, 64, 32>,
    w_out: SMatrix<f32, 3, 64>,
    pub signal_to_noise: f32,
    rng: SmallRng,
}

impl MicroReservoir {
    pub fn new(seed: u64) -> Self {
        let mut rng = SmallRng::seed_from_u64(seed);
        let mut w_res = SMatrix::<f32, 64, 64>::zeros();
        let n_exc = 51;
        let dist = Uniform::new(0.0f32, 1.0);

        for i in 0..64 {
            for j in 0..64 {
                if dist.sample(&mut rng) < 0.1 {
                    w_res[(i, j)] = if i < n_exc {
                        rng.gen_range(0.0..0.5)
                    } else {
                        rng.gen_range(-0.5..0.0)
                    };
                }
            }
        }

        // spectral radius normalization
        let mut v = SVector::<f32, 64>::repeat(1.0);
        for _ in 0..20 {
            v = w_res * v;
            let n = v.norm().max(1e-6);
            v /= n;
        }
        let radius = (w_res * v).norm().max(1e-6);
        w_res *= 0.9 / radius;

        let w_in = SMatrix::from_fn(|_, _| rng.gen_range(-0.2..0.2));
        let w_out = SMatrix::from_fn(|_, _| rng.gen_range(-0.01..0.01));

        Self {
            state: SVector::zeros(),
            w_res,
            w_in,
            w_out,
            signal_to_noise: 1.0,
            rng,
        }
    }

    pub fn step(&mut self, core_input: &[f32; 32], ctx: &OntogeneticContext) {
        let input = SVector::from_row_slice(core_input);

        let stress = (ctx.allostatic_load / ctx.stress_sensitivity.max(0.1)).clamp(0.0, 2.0);
        let noise_amp = if stress > 0.8 {
            (stress - 0.8).powi(2) * 0.4
        } else {
            0.0
        };

        let leak = 0.8 * ctx.metabolic_energy.clamp(0.1, 1.0);
        let gain = if ctx.circadian_phase < 0.8 { 1.0 } else { 0.5 };

        let pre = self.w_res * self.state + self.w_in * input;
        let noise = if noise_amp > 0.0 {
            SVector::from_fn(|_| {
                let n: f32 = StandardNormal.sample(&mut self.rng);
                n * noise_amp
            })
        } else {
            SVector::zeros()
        };

        let act = (pre * gain + noise).map(|x| x.tanh());
        self.state = self.state * (1.0 - leak) + act * leak;
        self.signal_to_noise = 1.0 / (1.0 + noise_amp * 2.0);
    }

    pub fn readout(&mut self, ctx: &OntogeneticContext) -> ActionVector {
        let raw = self.w_out * self.state;
        let explore = if ctx.plasticity_rate > 1.0 {
            let n: f32 = StandardNormal.sample(&mut self.rng);
            n * 0.1 * (ctx.plasticity_rate - 1.0)
        } else {
            0.0
        };

        let mut act = ActionVector {
            approach: (raw[0] + explore).max(0.0),
            avoid: (raw[1] + explore).max(0.0),
            freeze: raw[2].max(0.0),
        };
        act.normalize();
        act
    }
}

//
// 4. Symbolic pruning gate
//

pub trait LogicalSolver: Send + Sync {
    fn verify_constraints(&self, constraints: &str) -> bool;
}

pub struct SymbolicPruningGate {
    solver: Option<Arc<dyn LogicalSolver>>,
    pub timeout_ms: u32,
}

impl SymbolicPruningGate {
    pub fn new() -> Self {
        Self {
            solver: None,
            timeout_ms: 100,
        }
    }

    pub fn with_solver(mut self, solver: Arc<dyn LogicalSolver>) -> Self {
        self.solver = Some(solver);
        self
    }

    pub fn verify_action(&self, act: &ActionVector, ctx: &OntogeneticContext) -> bool {
        let energy_cost = act.approach * 0.05 + act.avoid * 0.03 + act.freeze * 0.01;
        let projected_energy = ctx.metabolic_energy - energy_cost;

        if projected_energy < 0.1 {
            return false;
        }
        if ctx.allostatic_load > 1.8 && act.approach > 0.5 {
            return false;
        }

        if let Some(solver) = &self.solver {
            let query = format!(
                "(and (> energy {}) (< tension {}))",
                projected_energy,
                ctx.allostatic_load + act.avoid * 0.2
            );
            return solver.verify_constraints(&query);
        }

        true
    }
}

impl Default for SymbolicPruningGate {
    fn default() -> Self {
        Self::new()
    }
}

//
// 5. Being32 — organism kernel
//

pub struct Being32 {
    pub id: usize,
    pub core: Hex32,
    pub rel_state: RelationalState,
    pub circadian: CircadianState,
    pub reservoir: MicroReservoir,
    pub symbolic_gate: SymbolicPruningGate,
    pub mode: CognitiveMode,
}

impl Being32 {
    pub fn new(id: usize, seed: u64) -> Self {
        let mut b = Self {
            id,
            core: Hex32::new(),
            rel_state: RelationalState::default(),
            circadian: CircadianState::new(1000, 200),
            reservoir: MicroReservoir::new(seed),
            symbolic_gate: SymbolicPruningGate::new(),
            mode: CognitiveMode::Shadow,
        };
        b.awaken_to_baseline();
        b
    }

    // --- organ accessors (subset, extend as needed) ---

    fn clamp(x: f32, lo: f32, hi: f32) -> f32 {
        x.max(lo).min(hi)
    }

    // affect
    pub fn aff_valence(&self) -> f32 {
        self.core.get_f32(3)
    }
    pub fn set_aff_valence(&mut self, v: f32) {
        self.core.set_f32(3, Self::clamp(v, -1.0, 1.0));
    }

    pub fn aff_arousal(&self) -> f32 {
        self.core.get_f32(4)
    }
    pub fn set_aff_arousal(&mut self, v: f32) {
        self.core.set_f32(4, Self::clamp(v, 0.0, 2.0));
    }

    pub fn aff_tension(&self) -> f32 {
        self.core.get_f32(5)
    }
    pub fn set_aff_tension(&mut self, v: f32) {
        self.core.set_f32(5, Self::clamp(v, 0.0, 2.0));
    }

    pub fn aff_coherence(&self) -> f32 {
        self.core.get_f32(6)
    }
    pub fn set_aff_coherence(&mut self, v: f32) {
        self.core.set_f32(6, Self::clamp(v, 0.0, 1.0));
    }

    // somatic
    pub fn som_heart(&self) -> f32 {
        self.core.get_f32(25)
    }
    pub fn set_som_heart(&mut self, v: f32) {
        self.core.set_f32(25, Self::clamp(v, 0.0, 2.0));
    }

    pub fn som_breath(&self) -> f32 {
        self.core.get_f32(26)
    }
    pub fn set_som_breath(&mut self, v: f32) {
        self.core.set_f32(26, Self::clamp(v, 0.0, 2.0));
    }

    pub fn som_tremor(&self) -> f32 {
        self.core.get_f32(27)
    }
    pub fn set_som_tremor(&mut self, v: f32) {
        self.core.set_f32(27, Self::clamp(v, 0.0, 1.0));
    }

    // boundary / relational
    pub fn bnd_permeability(&self) -> f32 {
        self.core.get_f32(19)
    }
    pub fn set_bnd_permeability(&mut self, v: f32) {
        self.core.set_f32(19, Self::clamp(v, 0.0, 1.0));
    }

    pub fn rel_curvature(&self) -> f32 {
        self.core.get_f32(20)
    }
    pub fn set_rel_curvature(&mut self, v: f32) {
        self.core.set_f32(20, Self::clamp(v, -1.0, 1.0));
    }

    pub fn rel_salience(&self) -> f32 {
        self.core.get_f32(24)
    }
    pub fn set_rel_salience(&mut self, v: f32) {
        self.core.set_f32(24, Self::clamp(v, 0.0, 1.0));
    }

    // narrative / meta
    pub fn nar_self_cont(&self) -> f32 {
        self.core.get_f32(23)
    }
    pub fn set_nar_self_cont(&mut self, v: f32) {
        self.core.set_f32(23, Self::clamp(v, 0.0, 1.0));
    }

    pub fn meta_energy(&self) -> f32 {
        self.core.get_f32(28)
    }
    pub fn set_meta_energy(&mut self, v: f32) {
        self.core.set_f32(28, Self::clamp(v, 0.0, 1.5));
    }

    // --- ontogenetic context ---

    pub fn ontogenetic_state(&self) -> OntogeneticContext {
        let phase = if self.circadian.is_asleep {
            self.circadian.phase_step as f32 / self.circadian.sleep_length as f32
        } else {
            self.circadian.phase_step as f32 / self.circadian.day_length as f32
        };

        OntogeneticContext {
            stress_sensitivity: 1.0,
            plasticity_rate: 1.0,
            baseline_permeability: self.bnd_permeability(),
            circadian_phase: phase,
            days_alive: self.circadian.day_counter,
            allostatic_load: self.aff_tension(),
            metabolic_energy: self.meta_energy(),
            is_asleep: self.circadian.is_asleep,
        }
    }

    // --- core packing for reservoir ---

    pub fn pack_core_state(&self) -> [f32; 32] {
        let mut v = [0.0f32; 32];
        for i in 0..32 {
            v[i] = self.core.get_f32(i);
        }
        v
    }

    // --- baseline ---

    fn awaken_to_baseline(&mut self) {
        self.set_som_heart(1.0);
        self.set_som_breath(1.0);
        self.set_som_tremor(0.0);
        self.set_aff_valence(0.2);
        self.set_aff_arousal(0.8);
        self.set_aff_tension(0.0);
        self.set_aff_coherence(1.0);
        self.set_bnd_permeability(0.5);
        self.set_nar_self_cont(1.0);
        self.set_rel_curvature(0.0);
        self.set_rel_salience(0.5);
        self.set_meta_energy(1.0);
    }

    // --- social field reception ---

    pub fn receive_social_field(&mut self, field: &SocialField) {
        let p = self.bnd_permeability().clamp(0.0, 1.0);
        let k = 0.05 * p;

        let v = self.aff_valence();
        let a = self.aff_arousal();
        let t = self.aff_tension();
        let b = self.som_breath();

        self.set_aff_valence(v + k * (field.avg_valence - v));
        self.set_aff_arousal(a + k * (field.avg_arousal - a));
        self.set_aff_tension(t + k * (field.avg_tension - t));
        self.set_som_breath(b + (k * 0.5) * (field.avg_breath - b));

        let new_perm = p * (1.0 - 0.1 * field.density.min(5.0));
        self.set_bnd_permeability(new_perm.clamp(0.0, 1.0));

        let mismatch = (v - field.avg_valence).abs();
        let curv = self.rel_curvature() + k * (mismatch - self.rel_curvature());
        self.set_rel_curvature(curv.clamp(-1.0, 1.0));
    }

    // --- homeostatic coupling (cross-organ feedback) ---

    fn homeostatic_coupling(&mut self) {
        let tension = self.aff_tension();
        let valence = self.aff_valence();
        let energy = self.meta_energy();
        let perm = self.bnd_permeability();
        let rel = self.rel_salience();

        let new_perm = perm - 0.05 * tension;
        self.set_bnd_permeability(new_perm.clamp(0.0, 1.0));

        let fatigue = (1.0 - energy).max(0.0);
        let tremor = self.som_tremor() + 0.02 * fatigue;
        self.set_som_tremor(tremor.clamp(0.0, 1.0));

        let new_rel = rel + 0.03 * valence;
        self.set_rel_salience(new_rel.clamp(0.0, 1.0));

        let coh = self.aff_coherence();
        self.set_aff_coherence((coh - 0.04 * tension).clamp(0.0, 1.0));
    }

    // --- deterministic action (fallback) ---

    pub fn compute_action_deterministic(&self) -> ActionVector {
        let v = self.aff_valence();
        let t = self.aff_tension();
        let e = self.meta_energy();

        let mut act = ActionVector {
            approach: (v + 0.5).max(0.0),
            avoid: t.max(0.0),
            freeze: (1.0 - e).max(0.0),
        };
        act.normalize();
        act
    }

    // --- neuro-symbolic action selection ---

    pub fn compute_action_neuro_symbolic(&mut self) -> ActionVector {
        let ont = self.ontogenetic_state();

        let mut candidates = Vec::new();
        for _ in 0..3 {
            let core_state = self.pack_core_state();
            self.reservoir.step(&core_state, &ont);
            candidates.push(self.reservoir.readout(&ont));
        }

        let mut valid: Vec<ActionVector> = candidates
            .into_iter()
            .filter(|a| self.symbolic_gate.verify_action(a, &ont))
            .collect();

        if valid.is_empty() {
            return self.compute_action_deterministic();
        }

        valid.sort_by(|a, b| {
            let sa = a.approach - a.avoid;
            let sb = b.approach - b.avoid;
            sa.partial_cmp(&sb).unwrap_or(std::cmp::Ordering::Equal)
        });

        valid.pop().unwrap()
    }

    // --- apply action + energy coupling ---

    pub fn apply_action(&mut self, act: ActionVector) {
        let heart = self.som_heart() + 0.1 * (act.approach - act.avoid);
        let breath = self.som_breath() + 0.05 * (act.approach - act.avoid);
        let tremor = self.som_tremor() + 0.1 * act.freeze;

        self.set_som_heart(heart.clamp(0.0, 2.0));
        self.set_som_breath(breath.clamp(0.0, 2.0));
        self.set_som_tremor(tremor.clamp(0.0, 1.0));

        let val = self.aff_valence()
            + 0.05 * (act.approach - act.avoid)
            + 0.01 * (self.som_heart() - 1.0)
            - 0.01 * self.som_tremor();
        self.set_aff_valence(val);

        let ten = self.aff_tension() + 0.05 * (act.avoid - act.approach);
        self.set_aff_tension(ten.clamp(0.0, 2.0));

        let energy_cost = act.approach * 0.05 + act.avoid * 0.03 + act.freeze * 0.01;
        let e = self.meta_energy();
        self.set_meta_energy((e - energy_cost).max(0.0));
    }

    // --- simple identity drift ---

    fn update_identity(&mut self, dt: f32) {
        let cont = self.nar_self_cont();
        let drift = 0.001 * self.aff_valence() * dt;
        self.set_nar_self_cont((cont + drift).clamp(0.0, 1.0));
    }

    // --- circadian transitions (minimal) ---

    fn enter_sleep(&mut self) {
        self.circadian.is_asleep = true;
        self.circadian.phase_step = 0;
    }

    fn awaken(&mut self) {
        self.circadian.is_asleep = false;
        self.circadian.phase_step = 0;
        self.circadian.day_counter += 1;
    }

    // --- main step ---

    pub fn step(&mut self, dt: f32, fb: &WorldFeedback, field: &SocialField) {
        if self.circadian.should_transition() {
            if self.circadian.is_asleep {
                self.awaken();
            } else {
                self.enter_sleep();
            }
        }

        if self.circadian.is_asleep {
            // simple sleep: recover energy, reduce tension
            let e = self.meta_energy();
            self.set_meta_energy(e + 0.05 * dt * (1.0 - e));
            let t = self.aff_tension();
            self.set_aff_tension(t + 0.05 * dt * (0.0 - t));
            self.circadian.phase_step += 1;
            return;
        }

        // waking
        self.receive_social_field(field);
        self.homeostatic_coupling();

        let action = match self.mode {
            CognitiveMode::Shadow => self.compute_action_deterministic(),
            CognitiveMode::Active => self.compute_action_neuro_symbolic(),
        };

        self.apply_action(action);
        self.update_identity(dt);

        // simple learning hook from feedback (placeholder)
        let _reward = fb.reward;
        let _threat = fb.threat;
        let _contact = fb.contact;

        self.circadian.phase_step += 1;
    }
}

//
// 6. Ecosystem helper
//

pub fn compute_social_field(beings: &[Being32]) -> SocialField {
    if beings.is_empty() {
        return SocialField::default();
    }

    let n = beings.len() as f32;
    let avg_valence = beings.iter().map(|b| b.aff_valence()).sum::<f32>() / n;
    let avg_arousal = beings.iter().map(|b| b.aff_arousal()).sum::<f32>() / n;
    let avg_tension = beings.iter().map(|b| b.aff_tension()).sum::<f32>() / n;
    let avg_breath = beings.iter().map(|b| b.som_breath()).sum::<f32>() / n;

    SocialField {
        avg_valence,
        avg_arousal,
        avg_tension,
        avg_breath,
        density: n,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_being_baseline() {
        let b = Being32::new(0, 42);
        assert!((b.aff_valence() - 0.2).abs() < 1e-5);
        assert!((b.aff_arousal() - 0.8).abs() < 1e-5);
        assert!((b.meta_energy() - 1.0).abs() < 1e-5);
    }

    #[test]
    fn test_action_vector_normalize() {
        let mut av = ActionVector {
            approach: 2.0,
            avoid: 1.0,
            freeze: 1.0,
        };
        av.normalize();
        let sum = av.approach + av.avoid + av.freeze;
        assert!((sum - 1.0).abs() < 1e-5);
    }

    #[test]
    fn test_step_does_not_panic() {
        let mut b = Being32::new(1, 7);
        b.mode = CognitiveMode::Active;
        let fb = WorldFeedback { reward: 0.1, threat: 0.0, contact: 0.5 };
        let field = SocialField {
            avg_valence: 0.3,
            avg_arousal: 0.9,
            avg_tension: 0.1,
            avg_breath: 1.0,
            density: 1.0,
        };
        for _ in 0..50 {
            b.step(1.0, &fb, &field);
        }
    }

    #[test]
    fn test_compute_social_field_empty() {
        let field = compute_social_field(&[]);
        assert_eq!(field.density, 0.0);
    }

    #[test]
    fn test_hex32_roundtrip() {
        let mut h = Hex32::new();
        h.set_word(0, 0xDEADBEEF);
        assert_eq!(h.get_word(0), 0xDEADBEEF);
    }

    #[test]
    fn test_circadian_transition() {
        let mut b = Being32::new(2, 99);
        let fb = WorldFeedback::default();
        let field = SocialField::default();
        // run past day_length (1000 steps)
        for _ in 0..1001 {
            b.step(1.0, &fb, &field);
        }
        assert!(b.circadian.is_asleep);
    }

    #[test]
    fn test_symbolic_gate_energy_guard() {
        let gate = SymbolicPruningGate::new();
        let ctx = OntogeneticContext {
            stress_sensitivity: 1.0,
            plasticity_rate: 1.0,
            baseline_permeability: 0.5,
            circadian_phase: 0.5,
            days_alive: 0,
            allostatic_load: 0.0,
            metabolic_energy: 0.05, // very low
            is_asleep: false,
        };
        let act = ActionVector { approach: 1.0, avoid: 0.0, freeze: 0.0 };
        assert!(!gate.verify_action(&act, &ctx));
    }
}
