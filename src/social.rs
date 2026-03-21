// src/social.rs

/// A snapshot of the ambient social field (many beings → one aggregate).
#[derive(Clone, Debug)]
pub struct SocialField {
    /// Mean valence of all beings projecting into the field.
    pub avg_valence: f32,
    /// Mean arousal of all beings projecting into the field.
    pub avg_arousal: f32,
    /// Number of beings per unit area — higher means denser crowd.
    pub density: f32,
}

impl SocialField {
    pub fn empty() -> Self {
        Self { avg_valence: 0.0, avg_arousal: 1.0, density: 0.0 }
    }

    /// Build a field from a slice of (valence, arousal) pairs.
    pub fn from_beings(beings: &[(f32, f32)]) -> Self {
        if beings.is_empty() {
            return Self::empty();
        }
        let n = beings.len() as f32;
        let avg_v = beings.iter().map(|(v, _)| v).sum::<f32>() / n;
        let avg_a = beings.iter().map(|(_, a)| a).sum::<f32>() / n;
        Self {
            avg_valence: avg_v,
            avg_arousal: avg_a,
            density: n,
        }
    }
}

/// A nearby being as seen from the perceiving being's frame.
#[derive(Clone, Debug)]
pub struct Neighbor {
    /// Stable id matching Dyad.other_id.
    pub id: u32,
    /// Normalised distance in [0, 1] — 0 is touching, 1 is perceptual horizon.
    pub distance: f32,
}

/// The perceiving being's local perceptual context.
#[derive(Clone, Debug)]
pub struct LocalContext {
    pub neighbors: Vec<Neighbor>,
}

impl LocalContext {
    pub fn empty() -> Self {
        Self { neighbors: Vec::new() }
    }
}
