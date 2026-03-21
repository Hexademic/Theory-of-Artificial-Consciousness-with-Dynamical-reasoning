use being32::{Being32, CognitiveMode, SocialField, WorldFeedback, compute_social_field};

fn main() {
    println!("Being32 v2 — organism kernel demo\n");

    // spawn a small ecosystem
    let mut beings: Vec<Being32> = (0..4)
        .map(|i| {
            let mut b = Being32::new(i, i as u64 * 13 + 7);
            if i % 2 == 0 {
                b.mode = CognitiveMode::Active;
            }
            b
        })
        .collect();

    let fb = WorldFeedback { reward: 0.1, threat: 0.0, contact: 0.5 };

    for tick in 0..20 {
        let field = compute_social_field(&beings);

        for b in beings.iter_mut() {
            let field_clone = field.clone();
            b.step(1.0, &fb, &field_clone);
        }

        if tick % 5 == 0 {
            println!("tick {tick:3}  field: valence={:.3}  arousal={:.3}  tension={:.3}",
                field.avg_valence, field.avg_arousal, field.avg_tension);
            for b in &beings {
                println!("  being[{}] v={:.3} a={:.3} t={:.3} e={:.3} day={}",
                    b.id,
                    b.aff_valence(), b.aff_arousal(), b.aff_tension(),
                    b.meta_energy(), b.circadian.day_counter);
            }
        }
    }

    println!("\nDone.");
}
