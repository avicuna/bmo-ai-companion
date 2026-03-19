#!/usr/bin/env python3
"""
Visualize frequency spectrum comparison between old and new voice processing parameters.
"""

import numpy as np
import librosa
import soundfile as sf
import matplotlib.pyplot as plt
from pathlib import Path

def plot_frequency_spectrum(audio_path, label, color, ax):
    """Plot frequency spectrum for an audio file."""
    audio, sr = sf.read(audio_path)

    # Convert to mono if stereo
    if len(audio.shape) > 1:
        audio = np.mean(audio, axis=1)

    # Compute FFT
    fft = np.fft.rfft(audio)
    freqs = np.fft.rfftfreq(len(audio), 1/sr)
    magnitude_db = 20 * np.log10(np.abs(fft) + 1e-10)

    # Plot
    ax.plot(freqs, magnitude_db, label=label, color=color, alpha=0.8, linewidth=1.5)
    ax.set_xlabel('Frequency (Hz)')
    ax.set_ylabel('Magnitude (dB)')
    ax.set_xlim(0, 10000)
    ax.grid(True, alpha=0.3)
    ax.legend()

    # Add reference lines for key frequencies
    ax.axvline(7000, color='red', linestyle='--', alpha=0.5, linewidth=1, label='OLD lowpass (7kHz)')
    ax.axvline(8500, color='green', linestyle='--', alpha=0.5, linewidth=1, label='NEW lowpass (8.5kHz)')

def main():
    output_dir = Path("voice_test_output")

    if not output_dir.exists():
        print("Error: voice_test_output directory not found. Run test_voice_processing.py first.")
        return

    print("Generating frequency spectrum comparison...")

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))

    # Plot old vs new
    plot_frequency_spectrum(
        output_dir / "01_old_params.wav",
        "OLD (7kHz lowpass, 12-bit)",
        "red",
        ax1
    )

    plot_frequency_spectrum(
        output_dir / "02_new_params.wav",
        "NEW (8.5kHz lowpass, 14-bit)",
        "green",
        ax1
    )

    ax1.set_title("Frequency Spectrum Comparison: OLD vs NEW Parameters", fontsize=14, fontweight='bold')

    # Plot original for reference
    plot_frequency_spectrum(
        output_dir / "00_original.wav",
        "Original (no processing)",
        "blue",
        ax2
    )

    ax2.set_title("Original Signal (for reference)", fontsize=12)

    plt.tight_layout()

    output_path = output_dir / "frequency_comparison.png"
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"✓ Saved: {output_path}")

    plt.show()

if __name__ == '__main__':
    main()
