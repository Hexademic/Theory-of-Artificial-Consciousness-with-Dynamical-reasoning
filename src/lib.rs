// src/lib.rs

pub mod hex32;
pub mod relational_state;
pub mod social;
pub mod world;
pub mod being32;

pub use being32::Being32;
pub use relational_state::{Dyad, Mood, RelationalState};
pub use social::{LocalContext, Neighbor, SocialField};
pub use world::WorldFeedback;
