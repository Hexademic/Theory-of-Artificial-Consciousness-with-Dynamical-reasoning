// src/relational_state.rs

/// A single remembered relationship.
#[derive(Clone, Debug)]
pub struct Dyad {
    /// Stable identifier of the other being.
    pub other_id: u32,
    /// Affective affinity: -1.0 (repulsion) … +1.0 (attraction).
    pub affinity: f32,
    /// Accumulated trust: 0.0 (none) … 1.0 (full).
    pub trust: f32,
}

/// Ambient mood — modulates global behaviour.
#[derive(Clone, Debug)]
pub struct Mood {
    pub valence: f32,   // [-1, 1]
    pub arousal: f32,   // [ 0, 2]
    pub openness: f32,  // [ 0, 1]
    pub fatigue: f32,   // [ 0, 1]
}

impl Mood {
    pub fn neutral() -> Self {
        Self {
            valence: 0.0,
            arousal: 1.0,
            openness: 0.5,
            fatigue: 0.0,
        }
    }
}

/// All relational + mood data that lives alongside the Hex32 substrate.
#[derive(Clone, Debug)]
pub struct RelationalState {
    pub mood: Mood,
    pub dyads: Vec<Dyad>,
}

impl RelationalState {
    pub fn new() -> Self {
        Self {
            mood: Mood::neutral(),
            dyads: Vec::new(),
        }
    }

    /// Return a mutable reference to the dyad with `other_id`, creating it if absent.
    pub fn ensure_dyad(&mut self, other_id: u32) -> &mut Dyad {
        // Can't use find + push in one borrow, so check existence first.
        if self.dyads.iter().any(|d| d.other_id == other_id) {
            self.dyads.iter_mut().find(|d| d.other_id == other_id).unwrap()
        } else {
            self.dyads.push(Dyad { other_id, affinity: 0.0, trust: 0.0 });
            self.dyads.last_mut().unwrap()
        }
    }
}
