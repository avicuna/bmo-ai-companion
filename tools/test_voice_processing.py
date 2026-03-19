#!/usr/bin/env python3
"""
Test BMO Voice Processing Changes
Validates the AI Council recommended parameter updates:
- Lowpass: 7kHz → 8.5kHz
- Bitcrush: 12-bit → 14-bit
- Lo-fi rate: 11kHz → 16kHz

Generates before/after comparison audio files.
"""

import numpy as np
import librosa
import soundfile as sf
from pedalboard import Pedalboard, HighpassFilter, LowpassFilter, Bitcrush, Reverb, Gain
import sys
from pathlib import Path

# OLD parameters (pre-council)
OLD_LOWPASS = 7000
OLD_BITCRUSH = 12
OLD_LOFI_RATE = 11025

# NEW parameters (post-council)
NEW_LOWPASS = 8500
NEW_BITCRUSH = 14
NEW_LOFI_RATE = 16000

# Shared parameters
HIGHPASS = 250
PITCH_SHIFT = 1.5
SAMPLE_RATE = 22050


def create_old_chain():
    """Create the OLD voice processing chain."""
    return Pedalboard([
        HighpassFilter(cutoff_frequency_hz=HIGHPASS),
        LowpassFilter(cutoff_frequency_hz=OLD_LOWPASS),
        Bitcrush(bit_depth=OLD_BITCRUSH),
        Reverb(room_size=0.05, wet_level=0.08),
        Gain(gain_db=2),
    ])


def create_new_chain():
    """Create the NEW voice processing chain (AI Council recommendations)."""
    return Pedalboard([
        HighpassFilter(cutoff_frequency_hz=HIGHPASS),
        LowpassFilter(cutoff_frequency_hz=NEW_LOWPASS),
        Bitcrush(bit_depth=NEW_BITCRUSH),
        Reverb(room_size=0.05, wet_level=0.08),
        Gain(gain_db=2),
    ])


def apply_bmo_voice_effect(audio_array, sample_rate, chain, lofi_rate, pitch_shift):
    """Apply BMO voice effect with specified parameters."""
    y = audio_array.astype(np.float32)

    # Normalize to [-1, 1] if needed
    if np.max(np.abs(y)) > 1.0:
        y = y / 32768.0

    # Step 1: Pitch shift up (more childlike)
    if pitch_shift != 0:
        y = librosa.effects.pitch_shift(y, sr=sample_rate, n_steps=pitch_shift)

    # Step 2: Lo-fi downsample trick
    if lofi_rate > 0 and lofi_rate < sample_rate:
        y = librosa.resample(y, orig_sr=sample_rate, target_sr=lofi_rate)
        y = librosa.resample(y, orig_sr=lofi_rate, target_sr=sample_rate)

    # Step 3: Pedalboard effects chain
    y_2d = y.reshape(1, -1)
    y_processed = chain(y_2d, sample_rate).flatten()

    # Convert back to int16
    y_processed = np.clip(y_processed, -1.0, 1.0)
    y_processed = (y_processed * 32767).astype(np.int16)

    return y_processed, sample_rate


def generate_test_audio(duration=3.0, sample_rate=22050):
    """Generate test audio: sweep + voice-like formants."""
    print("[GENERATE] Creating test audio...")

    t = np.linspace(0, duration, int(duration * sample_rate))

    # Create a voice-like signal with formants (simulating speech)
    # F1 = 800 Hz, F2 = 1200 Hz, F3 = 2500 Hz (vowel /a/)
    f1 = np.sin(2 * np.pi * 800 * t)
    f2 = np.sin(2 * np.pi * 1200 * t) * 0.7
    f3 = np.sin(2 * np.pi * 2500 * t) * 0.5

    # Add some high-frequency content (sibilants)
    sibilants = np.sin(2 * np.pi * 6000 * t) * 0.3

    # Combine
    audio = f1 + f2 + f3 + sibilants

    # Add envelope (amplitude modulation to simulate speech rhythm)
    envelope = np.abs(np.sin(2 * np.pi * 5 * t))  # 5 Hz modulation
    audio = audio * envelope

    # Normalize
    audio = audio / np.max(np.abs(audio)) * 0.8

    return (audio * 32767).astype(np.int16), sample_rate


def analyze_frequency_content(audio, sample_rate, label):
    """Analyze and print frequency content."""
    # Convert to float
    y = audio.astype(np.float32) / 32768.0

    # Compute FFT
    fft = np.fft.rfft(y)
    freqs = np.fft.rfftfreq(len(y), 1/sample_rate)
    magnitude = np.abs(fft)

    # Find dominant frequencies
    peaks_idx = np.argsort(magnitude)[-5:][::-1]

    print(f"\n[ANALYSIS] {label}")
    print(f"  Sample rate: {sample_rate} Hz")
    print(f"  Duration: {len(audio)/sample_rate:.2f}s")
    print(f"  Max frequency: {freqs[-1]:.0f} Hz")
    print(f"  Top 5 frequencies:")
    for idx in peaks_idx:
        if freqs[idx] > 0:
            print(f"    {freqs[idx]:.0f} Hz")


def main():
    print("="*70)
    print("BMO VOICE PROCESSING TEST")
    print("Testing AI Council parameter recommendations")
    print("="*70)

    # Create output directory
    output_dir = Path("voice_test_output")
    output_dir.mkdir(exist_ok=True)

    # Generate or load test audio
    print("\n[1] Generating test audio (simulated voice)...")
    audio, sr = generate_test_audio(duration=3.0, sample_rate=SAMPLE_RATE)

    # Save original
    original_path = output_dir / "00_original.wav"
    sf.write(original_path, audio, sr)
    print(f"  ✓ Saved: {original_path}")
    analyze_frequency_content(audio, sr, "ORIGINAL")

    # Process with OLD parameters
    print("\n[2] Processing with OLD parameters (pre-council)...")
    print(f"  Lowpass: {OLD_LOWPASS} Hz")
    print(f"  Bitcrush: {OLD_BITCRUSH}-bit")
    print(f"  Lo-fi rate: {OLD_LOFI_RATE} Hz")

    old_chain = create_old_chain()
    audio_old, sr_old = apply_bmo_voice_effect(
        audio.copy(), sr, old_chain, OLD_LOFI_RATE, PITCH_SHIFT
    )

    old_path = output_dir / "01_old_params.wav"
    sf.write(old_path, audio_old, sr_old)
    print(f"  ✓ Saved: {old_path}")
    analyze_frequency_content(audio_old, sr_old, "OLD PARAMS (7kHz, 12-bit)")

    # Process with NEW parameters
    print("\n[3] Processing with NEW parameters (AI Council)...")
    print(f"  Lowpass: {NEW_LOWPASS} Hz")
    print(f"  Bitcrush: {NEW_BITCRUSH}-bit")
    print(f"  Lo-fi rate: {NEW_LOFI_RATE} Hz")

    new_chain = create_new_chain()
    audio_new, sr_new = apply_bmo_voice_effect(
        audio.copy(), sr, new_chain, NEW_LOFI_RATE, PITCH_SHIFT
    )

    new_path = output_dir / "02_new_params.wav"
    sf.write(new_path, audio_new, sr_new)
    print(f"  ✓ Saved: {new_path}")
    analyze_frequency_content(audio_new, sr_new, "NEW PARAMS (8.5kHz, 14-bit)")

    # Generate comparison
    print("\n" + "="*70)
    print("COMPARISON SUMMARY")
    print("="*70)
    print("\nOLD PARAMS (Pre-Council):")
    print(f"  Lowpass:     {OLD_LOWPASS} Hz  (rolls off high frequencies aggressively)")
    print(f"  Bitcrush:    {OLD_BITCRUSH}-bit    (more digital distortion)")
    print(f"  Lo-fi rate:  {OLD_LOFI_RATE} Hz  (aggressive aliasing)")
    print(f"  Result:      More retro, less clear (hard to understand)")

    print("\nNEW PARAMS (AI Council Recommendations):")
    print(f"  Lowpass:     {NEW_LOWPASS} Hz  (preserves sibilants s, f, th)")
    print(f"  Bitcrush:    {NEW_BITCRUSH}-bit    (preserves consonants)")
    print(f"  Lo-fi rate:  {NEW_LOFI_RATE} Hz  (conservative downsampling)")
    print(f"  Result:      70% clarity / 30% retro (daily-use balance)")

    print("\nKEY IMPROVEMENTS:")
    print("  ✓ Higher lowpass (8.5kHz) preserves high-frequency consonants")
    print("  ✓ Less bitcrushing (14-bit) reduces distortion artifacts")
    print("  ✓ Conservative lo-fi (16kHz) maintains intelligibility")
    print("  ✓ Target: Retro feel WITHOUT listener fatigue")

    print("\n" + "="*70)
    print("OUTPUT FILES")
    print("="*70)
    print(f"\n  {original_path}")
    print(f"  {old_path}")
    print(f"  {new_path}")

    print("\nLISTEN TEST:")
    print("  1. Play 01_old_params.wav (pre-council)")
    print("  2. Play 02_new_params.wav (council recommendations)")
    print("  3. Compare intelligibility and retro feel")
    print("  4. NEW should be clearer while keeping retro character")

    print("\nADJUSTMENT GUIDE:")
    print("  Too retro?  → Increase lowpass to 9000 Hz in agent.py")
    print("  Too clean?  → Decrease lowpass to 8000 Hz")
    print("  Need more retro? → Reduce bitcrush to 13-bit")
    print("  Need more clarity? → Keep at 14-bit or increase to 15-bit")

    print("\n" + "="*70)
    print("✓ Voice processing test complete!")
    print("="*70 + "\n")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"\n[ERROR] {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
