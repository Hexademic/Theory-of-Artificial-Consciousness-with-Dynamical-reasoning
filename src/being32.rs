// src/being32.rs

use crate::hex32::Hex32;
use crate::relational_state::RelationalState;
use crate::social::{LocalContext, SocialField};
use crate::world::WorldFeedback;

//
// 2. ActionVector (motor simplex, v1.1)
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

//
// 3. Being32 struct
//

#[derive(Clone, Debug)]
pub struct Being32 {
    pub core: Hex32,                 // 128-byte substrate
    pub rel_state: RelationalState,  // runtime relational/mood state
}

impl Being32 {
    pub fn new() -> Self {
        Self {
            core: Hex32::new(),
            rel_state: RelationalState::new(),
        }
    }

    // -------------------------
    // 6. Helpers
    // -------------------------

    #[inline]
    fn clamp(x: f32, lo: f32, hi: f32) -> f32 {
        x.max(lo).min(hi)
    }

    #[inline]
    fn get_f32(&self, idx: usize) -> f32 {
        f32::from_bits(self.core.get_word(idx))
    }

    #[inline]
    fn set_f32(&mut self, idx: usize, val: f32) {
        self.core.set_word(idx, val.to_bits());
    }

    // -------------------------
    // 4. Typed organ accessors
    // -------------------------
    // Identity (0–2)

    pub fn id_trait(&self) -> [f32; 3] {
        [self.get_f32(0), self.get_f32(1), self.get_f32(2)]
    }

    pub fn set_id_trait(&mut self, v: [f32; 3]) {
        self.set_f32(0, v[0]);
        self.set_f32(1, v[1]);
        self.set_f32(2, v[2]);
    }

    // Affect (3–6)

    pub fn aff_valence(&self) -> f32 { self.get_f32(3) }
    pub fn set_aff_valence(&mut self, v: f32) {
        self.set_f32(3, Self::clamp(v, -1.0, 1.0));
    }

    pub fn aff_arousal(&self) -> f32 { self.get_f32(4) }
    pub fn set_aff_arousal(&mut self, v: f32) {
        self.set_f32(4, Self::clamp(v, 0.0, 2.0));
    }

    pub fn aff_tension(&self) -> f32 { self.get_f32(5) }
    pub fn set_aff_tension(&mut self, v: f32) {
        self.set_f32(5, Self::clamp(v, -1.0, 2.0));
    }

    pub fn aff_coherence(&self) -> f32 { self.get_f32(6) }
    pub fn set_aff_coherence(&mut self, v: f32) {
        self.set_f32(6, Self::clamp(v, 0.0, 1.0));
    }

    // Interoception (7–9)

    pub fn int_load(&self) -> f32 { self.get_f32(7) }
    pub fn set_int_load(&mut self, v: f32) {
        self.set_f32(7, Self::clamp(v, 0.0, 1.0));
    }

    pub fn int_fatigue(&self) -> f32 { self.get_f32(8) }
    pub fn set_int_fatigue(&mut self, v: f32) {
        self.set_f32(8, Self::clamp(v, 0.0, 1.0));
    }

    pub fn int_osc(&self) -> f32 { self.get_f32(9) }
    pub fn set_int_osc(&mut self, v: f32) {
        self.set_f32(9, Self::clamp(v, -1.0, 1.0));
    }

    // Appraisal (10–12)

    pub fn app_pred_err(&self) -> f32 { self.get_f32(10) }
    pub fn set_app_pred_err(&mut self, v: f32) {
        self.set_f32(10, Self::clamp(v, 0.0, 1.0));
    }

    pub fn app_relevance(&self) -> f32 { self.get_f32(11) }
    pub fn set_app_relevance(&mut self, v: f32) {
        self.set_f32(11, Self::clamp(v, 0.0, 1.0));
    }

    pub fn app_expect_impact(&self) -> f32 { self.get_f32(12) }
    pub fn set_app_expect_impact(&mut self, v: f32) {
        self.set_f32(12, Self::clamp(v, 0.0, 1.0));
    }

    // Cascade (13–15)

    pub fn cas_phase(&self) -> f32 { self.get_f32(13) }
    pub fn set_cas_phase(&mut self, v: f32) {
        self.set_f32(13, Self::clamp(v, 0.0, 1.0));
    }

    pub fn cas_intensity(&self) -> f32 { self.get_f32(14) }
    pub fn set_cas_intensity(&mut self, v: f32) {
        self.set_f32(14, Self::clamp(v, 0.0, 1.0));
    }

    pub fn cas_complete(&self) -> f32 { self.get_f32(15) }
    pub fn set_cas_complete(&mut self, v: f32) {
        self.set_f32(15, Self::clamp(v, 0.0, 1.0));
    }

    // Expression (16–17)

    pub fn exp_open(&self) -> f32 { self.get_f32(16) }
    pub fn set_exp_open(&mut self, v: f32) {
        self.set_f32(16, Self::clamp(v, 0.0, 1.0));
    }

    pub fn exp_modulation(&self) -> f32 { self.get_f32(17) }
    pub fn set_exp_modulation(&mut self, v: f32) {
        self.set_f32(17, Self::clamp(v, -1.0, 1.0));
    }

    // Boundary (18–19)

    pub fn bnd_soc_load(&self) -> f32 { self.get_f32(18) }
    pub fn set_bnd_soc_load(&mut self, v: f32) {
        self.set_f32(18, Self::clamp(v, 0.0, 1.0));
    }

    pub fn bnd_permeability(&self) -> f32 { self.get_f32(19) }
    pub fn set_bnd_permeability(&mut self, v: f32) {
        self.set_f32(19, Self::clamp(v, 0.0, 1.0));
    }

    // Relational (20–22)

    pub fn rel_curvature(&self) -> f32 { self.get_f32(20) }
    pub fn set_rel_curvature(&mut self, v: f32) {
        self.set_f32(20, Self::clamp(v, -1.0, 1.0));
    }

    pub fn rel_trust(&self) -> f32 { self.get_f32(21) }
    pub fn set_rel_trust(&mut self, v: f32) {
        self.set_f32(21, Self::clamp(v, 0.0, 1.0));
    }

    pub fn rel_stability(&self) -> f32 { self.get_f32(22) }
    pub fn set_rel_stability(&mut self, v: f32) {
        self.set_f32(22, Self::clamp(v, 0.0, 1.0));
    }

    // Narrative (23–24)

    pub fn nar_self_cont(&self) -> f32 { self.get_f32(23) }
    pub fn set_nar_self_cont(&mut self, v: f32) {
        self.set_f32(23, Self::clamp(v, 0.0, 1.0));
    }

    pub fn nar_drift(&self) -> f32 { self.get_f32(24) }
    pub fn set_nar_drift(&mut self, v: f32) {
        self.set_f32(24, Self::clamp(v, -1.0, 1.0));
    }

    // Somatic (25–27)

    pub fn som_heart(&self) -> f32 { self.get_f32(25) }
    pub fn set_som_heart(&mut self, v: f32) {
        self.set_f32(25, Self::clamp(v, 0.0, 2.0));
    }

    pub fn som_breath(&self) -> f32 { self.get_f32(26) }
    pub fn set_som_breath(&mut self, v: f32) {
        self.set_f32(26, Self::clamp(v, 0.0, 2.0));
    }

    pub fn som_tremor(&self) -> f32 { self.get_f32(27) }
    pub fn set_som_tremor(&mut self, v: f32) {
        self.set_f32(27, Self::clamp(v, 0.0, 1.0));
    }

    // Meta (28–30)

    pub fn meta_energy(&self) -> f32 { self.get_f32(28) }
    pub fn set_meta_energy(&mut self, v: f32) {
        self.set_f32(28, Self::clamp(v, 0.0, 1.0));
    }

    pub fn meta_absence_delta(&self) -> f32 { self.get_f32(29) }
    pub fn set_meta_absence_delta(&mut self, v: f32) {
        self.set_f32(29, Self::clamp(v, -1.0, 1.0));
    }

    pub fn meta_error_corr(&self) -> f32 { self.get_f32(30) }
    pub fn set_meta_error_corr(&mut self, v: f32) {
        self.set_f32(30, Self::clamp(v, -1.0, 1.0));
    }

    // Flags (31)

    pub fn flags(&self) -> u32 {
        self.core.get_word(31)
    }

    pub fn set_flags(&mut self, v: u32) {
        self.core.set_word(31, v);
    }

    // -------------------------
    // 5. Physiology
    // -------------------------

    // v1.3 Social resonance
    pub fn receive_social_field(&mut self, field: &SocialField) {
        let v = self.aff_valence();
        let a = self.aff_arousal();
        let p = self.bnd_permeability();

        // Affective resonance
        let new_v = v + 0.05 * (field.avg_valence - v);
        let new_a = a + 0.05 * (field.avg_arousal - a);
        self.set_aff_valence(new_v);
        self.set_aff_arousal(new_a);

        // Boundary contagion
        let new_perm = p * (1.0 - 0.1 * field.density.min(5.0));
        self.set_bnd_permeability(new_perm);

        // Curvature from mismatch
        let mismatch = (v - field.avg_valence).abs();
        let curv = self.rel_curvature() + 0.05 * (mismatch - self.rel_curvature());
        self.set_rel_curvature(curv.clamp(-1.0, 1.0));
    }

    // v1.1 + v2.0-R + v2.1-H Action computation
    pub fn compute_action(&self, ctx: &LocalContext) -> ActionVector {
        let v = self.aff_valence();
        let a = self.aff_arousal();
        let t = self.aff_tension();

        let mut act = ActionVector {
            approach: v.max(0.0) * (0.3 + 0.7 * a.min(1.0)),
            avoid: (-v).max(0.0) * (0.3 + 0.7 * t.clamp(0.0, 1.0)),
            freeze: (a - 1.2).max(0.0) + (t - 1.0).max(0.0),
        };

        // Dyadic bias
        for n in &ctx.neighbors {
            if let Some(d) = self.rel_state.dyads.iter().find(|d| d.other_id == n.id) {
                let w = 1.0 - n.distance;
                let bias = d.affinity * w;

                if bias > 0.0 {
                    act.approach += bias;
                } else {
                    act.avoid += -bias;
                }

                act.freeze *= 1.0 - 0.5 * d.trust;
            }
        }

        // Mood bias
        let m = &self.rel_state.mood;
        act.approach += m.valence.max(0.0) * m.openness;
        act.avoid += (-m.valence).max(0.0) * m.fatigue;
        act.freeze += m.fatigue * 0.3;

        act.normalize();
        act
    }

    // Somatic + boundary feedback
    pub fn apply_action(&mut self, act: ActionVector) {
        let heart = self.som_heart() + 0.1 * (act.approach - act.avoid);
        let breath = self.som_breath() + 0.05 * (act.approach - act.avoid);
        let tremor = self.som_tremor() + 0.1 * act.freeze;

        self.set_som_heart(heart.clamp(0.0, 2.0));
        self.set_som_breath(breath.clamp(0.0, 2.0));
        self.set_som_tremor(tremor.clamp(0.0, 1.0));

        let load = self.bnd_soc_load() + 0.1 * act.avoid - 0.05 * act.approach;
        self.set_bnd_soc_load(load.clamp(0.0, 1.0));

        let drift = self.nar_drift() + 0.02 * (act.avoid - act.approach);
        self.set_nar_drift(drift.clamp(-1.0, 1.0));
    }

    // v1.0–v1.2 core dynamics (with inertial valence)
    pub fn step(&mut self, dt: f32, fb: &WorldFeedback) {
        // Affect manifold
        let pred_err = self.app_pred_err();
        let rel = self.app_relevance();
        let coh = self.aff_coherence();
        let curv = self.rel_curvature();
        let drift = self.nar_drift();

        // target valence from appraisal (inertial lerp)
        let target_val = (-pred_err + coh).clamp(-1.0, 1.0);
        let old_val = self.aff_valence();
        let new_val = old_val + 0.1 * (target_val - old_val);
        self.set_aff_valence(new_val);

        // coherence update (inertial lerp, reuses captured coh)
        let target_coh = (-curv + (1.0 - drift.abs())).clamp(0.0, 1.0);
        let new_coh = coh + 0.1 * (target_coh - coh);
        self.set_aff_coherence(new_coh);

        // Cascade engine
        let mut phase = self.cas_phase();
        let mut intensity = self.cas_intensity();

        if rel > 0.5 && pred_err > 0.2 {
            // mood_factor scales the increment, not accumulated phase — avoids stall at low arousal
            let mood_factor = 0.5 + 0.5 * (self.rel_state.mood.arousal / 2.0); // [0.5, 1.0]
            phase += dt * (0.5 + intensity) * mood_factor;
        }

        if phase >= 1.0 {
            self.set_cas_complete(1.0);
            phase = 0.0;
            intensity *= 0.5;
        } else {
            self.set_cas_complete(0.0);
        }

        self.set_cas_phase(phase);
        self.set_cas_intensity(intensity.clamp(0.0, 1.0));

        // Learning (pulse-gated)
        if self.cas_complete() > 0.5 {
            let reward = fb.reward;
            let threat = fb.threat;
            let contact = fb.contact;

            let reward_p = reward * (0.5 + 0.5 * contact);
            let stress = (threat + self.aff_tension()) / 2.0;
            let safety = 1.0 - stress;

            let e = self.app_expect_impact();
            self.set_app_expect_impact(e + 0.05 * (reward_p - e));

            let tr = self.rel_trust();
            self.set_rel_trust(tr + 0.01 * (safety - tr));

            let bp = self.bnd_permeability();
            self.set_bnd_permeability(bp + 0.01 * (contact - bp));
        }

        // Somatic oscillation
        let osc = self.int_osc() + dt * (self.som_heart() - 1.0);
        self.set_int_osc(osc.clamp(-1.0, 1.0));
    }

    // v2.0-R + v2.1-H perceptual radius (used by World)
    pub fn perceptual_radius(&self) -> f32 {
        let base = 1.0;
        let coherence = self.aff_coherence().clamp(0.0, 1.0);
        let arousal = self.aff_arousal().clamp(0.0, 2.0);
        let mood_open = self.rel_state.mood.openness.clamp(0.0, 1.0);

        base * coherence * (2.0 - arousal).max(0.1) * (0.5 + 0.5 * mood_open)
    }
}
