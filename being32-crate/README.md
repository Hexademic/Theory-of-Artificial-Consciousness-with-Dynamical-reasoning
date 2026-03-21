# being32

**Being32 v2** — a minimal organism kernel for artificial consciousness research.

A 128-byte `Hex32` substrate + 64-unit echo-state reservoir + symbolic pruning gate,
oriented around regulation, social resonance, and identity continuity.

## Architecture

```
Being32
├── Hex32 (128 bytes)          — raw state substrate, organ-mapped
├── MicroReservoir<64>         — cortical analogue (echo-state network)
├── SymbolicPruningGate        — logical constraint filter on action candidates
├── RelationalState            — dyad graph + mood
└── CircadianState             — wake/sleep cycle
```

### Hex32 slot map (partial)

| Slot | Field               | Range      |
|------|---------------------|------------|
| 3    | `aff_valence`       | [-1, 1]    |
| 4    | `aff_arousal`       | [0, 2]     |
| 5    | `aff_tension`       | [0, 2]     |
| 6    | `aff_coherence`     | [0, 1]     |
| 19   | `bnd_permeability`  | [0, 1]     |
| 20   | `rel_curvature`     | [-1, 1]    |
| 23   | `nar_self_cont`     | [0, 1]     |
| 24   | `rel_salience`      | [0, 1]     |
| 25   | `som_heart`         | [0, 2]     |
| 26   | `som_breath`        | [0, 2]     |
| 27   | `som_tremor`        | [0, 1]     |
| 28   | `meta_energy`       | [0, 1.5]   |

## Usage

```rust
use being32::{Being32, CognitiveMode, SocialField, WorldFeedback, compute_social_field};

let mut beings: Vec<Being32> = (0..8).map(|i| Being32::new(i, i as u64)).collect();
beings[0].mode = CognitiveMode::Active; // enable neuro-symbolic action

let fb = WorldFeedback { reward: 0.1, threat: 0.0, contact: 0.5 };

for _ in 0..1000 {
    let field = compute_social_field(&beings);
    for b in beings.iter_mut() {
        b.step(1.0, &fb, &field.clone());
    }
}
```

## Dependencies

- [`nalgebra`](https://nalgebra.org) — matrix ops for the reservoir
- [`rand`](https://docs.rs/rand) + [`rand_distr`](https://docs.rs/rand_distr) — stochastic dynamics

## License

MIT
