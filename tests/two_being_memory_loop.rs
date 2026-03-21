// tests/two_being_memory_loop.rs
//
// Verifies the four dyad memory properties over a 50-tick shared resonance loop:
//
//   1. Dyad Memory Formation     — dyad entries are created on first encounter
//   2. Affinity Accumulation     — affinity rises when beings are valence-aligned
//   3. Trust Accumulation        — trust rises in low-density, low-mismatch encounters
//   4. Relational Curvature      — curvature stabilises toward mismatch signal

use being32::{Being32, SocialField, WorldFeedback};

const TICKS: usize = 50;
const DT: f32 = 0.1;

const ID_A: u32 = 0;
const ID_B: u32 = 1;

fn neutral_feedback() -> WorldFeedback {
    WorldFeedback::neutral()
}

/// Build a SocialField from the perspective of the *other* being.
fn field_from(other: &Being32) -> SocialField {
    SocialField::from_beings(&[(other.aff_valence(), other.aff_arousal())])
}

// ─── Test 1: Dyad Memory Formation ───────────────────────────────────────────

#[test]
fn dyad_memory_formation() {
    let mut a = Being32::new();
    let mut b = Being32::new();

    // Before interaction — no dyads.
    assert!(a.rel_state.dyads.is_empty(), "A should have no dyads before interaction");
    assert!(b.rel_state.dyads.is_empty(), "B should have no dyads before interaction");

    let field_a = field_from(&b);
    let field_b = field_from(&a);

    a.receive_social_field(&field_b);
    b.receive_social_field(&field_a);
    a.update_dyad_from_interaction(ID_B, &field_b);
    b.update_dyad_from_interaction(ID_A, &field_a);

    assert_eq!(a.rel_state.dyads.len(), 1, "A should have exactly one dyad after meeting B");
    assert_eq!(b.rel_state.dyads.len(), 1, "B should have exactly one dyad after meeting A");
    assert_eq!(a.rel_state.dyads[0].other_id, ID_B);
    assert_eq!(b.rel_state.dyads[0].other_id, ID_A);
}

// ─── Test 2: Affinity Accumulation ───────────────────────────────────────────

#[test]
fn affinity_accumulation() {
    let mut a = Being32::new();
    let mut b = Being32::new();
    let fb = neutral_feedback();

    // Seed both with similar positive valence so they are aligned.
    a.set_aff_valence(0.6);
    b.set_aff_valence(0.5);
    a.set_app_pred_err(0.0);
    b.set_app_pred_err(0.0);

    for _ in 0..TICKS {
        let field_b = field_from(&b);
        let field_a = field_from(&a);

        a.receive_social_field(&field_b);
        b.receive_social_field(&field_a);
        a.update_dyad_from_interaction(ID_B, &field_b);
        b.update_dyad_from_interaction(ID_A, &field_a);
        a.step(DT, &fb);
        b.step(DT, &fb);
    }

    let affinity_a = a.rel_state.dyads.iter().find(|d| d.other_id == ID_B)
        .map(|d| d.affinity).unwrap_or(0.0);
    let affinity_b = b.rel_state.dyads.iter().find(|d| d.other_id == ID_A)
        .map(|d| d.affinity).unwrap_or(0.0);

    assert!(
        affinity_a > 0.3,
        "A's affinity toward B should exceed 0.3 after {TICKS} aligned ticks, got {affinity_a}"
    );
    assert!(
        affinity_b > 0.3,
        "B's affinity toward A should exceed 0.3 after {TICKS} aligned ticks, got {affinity_b}"
    );
}

// ─── Test 3: Trust Accumulation ──────────────────────────────────────────────

#[test]
fn trust_accumulation() {
    let mut a = Being32::new();
    let mut b = Being32::new();
    let fb = neutral_feedback();

    // Aligned valence, low density (one-to-one) → ideal trust conditions.
    a.set_aff_valence(0.4);
    b.set_aff_valence(0.4);

    for _ in 0..TICKS {
        let field_b = field_from(&b); // density == 1.0
        let field_a = field_from(&a);

        a.receive_social_field(&field_b);
        b.receive_social_field(&field_a);
        a.update_dyad_from_interaction(ID_B, &field_b);
        b.update_dyad_from_interaction(ID_A, &field_a);
        a.step(DT, &fb);
        b.step(DT, &fb);
    }

    let trust_a = a.rel_state.dyads.iter().find(|d| d.other_id == ID_B)
        .map(|d| d.trust).unwrap_or(0.0);
    let trust_b = b.rel_state.dyads.iter().find(|d| d.other_id == ID_A)
        .map(|d| d.trust).unwrap_or(0.0);

    // Note: density=1 gives trust_target = 0 via crowd_penalty; with identical valence
    // the mismatch term is 0 but crowd_penalty saturates at density=1.
    // Trust should at least be non-negative and the dyad should exist.
    assert!(trust_a >= 0.0, "Trust must not go negative: {trust_a}");
    assert!(trust_b >= 0.0, "Trust must not go negative: {trust_b}");

    // For a meaningful trust-rise test use density < 1 (sub-unit group).
    let field_sparse = SocialField { avg_valence: 0.4, avg_arousal: 1.0, density: 0.2 };
    let mut c = Being32::new();
    let mut d = Being32::new();
    c.set_aff_valence(0.4);
    d.set_aff_valence(0.4);

    for _ in 0..TICKS {
        c.receive_social_field(&field_sparse);
        d.receive_social_field(&field_sparse);
        c.update_dyad_from_interaction(ID_B, &field_sparse);
        d.update_dyad_from_interaction(ID_A, &field_sparse);
        c.step(DT, &fb);
        d.step(DT, &fb);
    }

    let trust_c = c.rel_state.dyads.iter().find(|d| d.other_id == ID_B)
        .map(|d| d.trust).unwrap_or(0.0);

    assert!(
        trust_c > 0.2,
        "Trust should accumulate in sparse, aligned encounters; got {trust_c}"
    );
}

// ─── Test 4: Relational Curvature Stabilisation ───────────────────────────────

#[test]
fn relational_curvature_stabilisation() {
    let mut a = Being32::new();
    let fb = neutral_feedback();

    // Seed A with positive valence; field carries opposite valence → persistent mismatch.
    a.set_aff_valence(0.8);
    let field_opposing = SocialField { avg_valence: -0.5, avg_arousal: 1.0, density: 0.5 };

    for _ in 0..TICKS {
        a.receive_social_field(&field_opposing);
        a.update_dyad_from_interaction(ID_B, &field_opposing);
        a.step(DT, &fb);
    }

    let curv = a.rel_curvature();
    assert!(
        curv < 0.0,
        "Curvature should bend negative under persistent mismatch; got {curv}"
    );
}
