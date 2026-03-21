// src/world.rs

/// Environmental feedback delivered to a being each tick.
#[derive(Clone, Debug)]
pub struct WorldFeedback {
    /// Positive signal: outcome matched or exceeded expectation. [0, 1]
    pub reward: f32,
    /// Threat level in the environment. [0, 1]
    pub threat: f32,
    /// Quality of social contact (presence, attunement). [0, 1]
    pub contact: f32,
}

impl WorldFeedback {
    pub fn neutral() -> Self {
        Self { reward: 0.0, threat: 0.0, contact: 0.0 }
    }
}
