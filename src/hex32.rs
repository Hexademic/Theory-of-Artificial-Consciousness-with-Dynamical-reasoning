// src/hex32.rs
// 128-byte substrate: 32 × u32 words, little-endian IEEE-754 f32.

#[derive(Clone, Debug)]
pub struct Hex32 {
    words: [u32; 32],
}

impl Hex32 {
    pub fn new() -> Self {
        Self { words: [0u32; 32] }
    }

    #[inline]
    pub fn get_word(&self, idx: usize) -> u32 {
        self.words[idx]
    }

    #[inline]
    pub fn set_word(&mut self, idx: usize, val: u32) {
        self.words[idx] = val;
    }
}
