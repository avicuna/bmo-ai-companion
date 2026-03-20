#!/usr/bin/env python3
"""
BMO Voice Tuning Tool
======================
A/B compare voice effect chain settings and find the perfect BMO voice.

Modes:
  preview   — Apply current config settings to a WAV file and play it
  sweep     — Generate variants across a parameter range and compare
  ab        — Compare two specific configurations side by side
  export    — Apply settings and export a processed file

Usage:
  # Preview current config on a sample file
  python tools/tune_bmo_voice.py preview --input sample.wav

  # Sweep pitch shift from 0 to 3 semitones in 0.5 steps
  python tools/tune_bmo_voice.py sweep --input sample.wav --param pitch --min 0 --max 3 --step 0.5

  # Sweep lo-fi sample rate
  python tools/tune_bmo_voice.py sweep --input sample.wav --param lofi --min 8000 --max 22050 --step 2000

  # Sweep bitcrush bit depth
  python tools/tune_bmo_voice.py sweep --input sample.wav --param bitcrush --min 8 --max 16 --step 2

  # A/B compare two configs
  python tools/tune_bmo_voice.py ab --input sample.wav --a "pitch=1.5,lofi=16000,bitcrush=14" --b "pitch=2.0,lofi=12000,bitcrush=12"

  # Export with custom settings
  python tools/tune_bmo_voice.py export --input sample.wav --output bmo_voice.wav --pitch 1.5 --lofi 16000

Requirements:
  pip install sounddevice numpy scipy librosa pedalboard soundfile
"""

import os
import sys
import argparse
import json
import time

import numpy as np
import librosa
import soundfile as sf
import sounddevice as sd
import scipy.signal
from pedalboard import Pedalboard, HighpassFilter, LowpassFilter, Bitcrush, Reverb, Gain


# =========================================================================
# VOICE EFFECT ENGINE
# =========================================================================

# Defaults from config.json / agent.py
DEFAULT_PARAMS = {
    "pitch": 1.5,           # Semitones up (childlike register)
    "lofi": 16000,          # Lo-fi downsample rate (device feel)
    "highpass": 250,         # HPF cutoff (small speaker sim)
    "lowpass": 8500,         # LPF cutoff (toy speaker sim)
    "bitcrush": 14,          # Bit depth (digital crunch)
    "reverb_size": 0.05,     # Reverb room size (plastic box)
    "reverb_wet": 0.08,      # Reverb wet level
    "gain": 2.0,             # Output gain compensation (dB)
}

# Load from config.json if available
CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")

def load_config_params():
    """Load voice parameters from config.json, falling back to defaults."""
    params = DEFAULT_PARAMS.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                cfg = json.load(f)
            params["pitch"] = cfg.get("bmo_pitch_shift", params["pitch"])
            params["lofi"] = cfg.get("bmo_lofi_sample_rate", params["lofi"])
        except Exception:
            pass
    return params


def apply_voice_effect(audio, sr, params):
    """Apply BMO voice effect chain with given parameters.

    Pipeline:
      1. Pitch shift (childlike register)
      2. Lo-fi downsample trick (device aliasing)
      3. Pedalboard chain (small speaker + digital crunch + box reverb)
    Returns (processed_audio_int16, sample_rate).
    """
    y = audio.astype(np.float32)
    if np.max(np.abs(y)) > 1.0:
        y = y / 32768.0

    # Step 1: Pitch shift
    pitch = params.get("pitch", 1.5)
    if pitch != 0:
        y = librosa.effects.pitch_shift(y, sr=sr, n_steps=pitch)

    # Step 2: Lo-fi downsample trick
    lofi = params.get("lofi", 16000)
    if 0 < lofi < sr:
        y = librosa.resample(y, orig_sr=sr, target_sr=lofi)
        y = librosa.resample(y, orig_sr=lofi, target_sr=sr)

    # Step 3: Pedalboard chain
    chain = Pedalboard([
        HighpassFilter(cutoff_frequency_hz=params.get("highpass", 250)),
        LowpassFilter(cutoff_frequency_hz=params.get("lowpass", 8500)),
        Bitcrush(bit_depth=params.get("bitcrush", 14)),
        Reverb(room_size=params.get("reverb_size", 0.05),
               wet_level=params.get("reverb_wet", 0.08)),
        Gain(gain_db=params.get("gain", 2.0)),
    ])
    y_2d = y.reshape(1, -1)
    y_processed = chain(y_2d, sr).flatten()

    # Convert to int16
    y_processed = np.clip(y_processed, -1.0, 1.0)
    y_processed = (y_processed * 32767).astype(np.int16)

    return y_processed, sr


def load_audio(path, target_sr=22050):
    """Load audio file, return (int16_array, sample_rate)."""
    y, sr = librosa.load(path, sr=target_sr, mono=True)
    # Keep as float for processing
    return y, sr


def play_audio(audio_int16, sr):
    """Play int16 audio through default output device."""
    try:
        device_info = sd.query_devices(kind='output')
        native_rate = int(device_info['default_samplerate'])
    except Exception:
        native_rate = 48000

    playback_rate = sr
    playback_audio = audio_int16
    try:
        sd.check_output_settings(device=None, samplerate=sr)
    except Exception:
        num_samples = int(len(audio_int16) * (native_rate / sr))
        playback_audio = scipy.signal.resample(audio_int16, num_samples).astype(np.int16)
        playback_rate = native_rate

    sd.play(playback_audio, playback_rate)
    sd.wait()


def params_to_string(params):
    """Format params as a compact string."""
    return (f"pitch={params['pitch']}st "
            f"lofi={params['lofi']}Hz "
            f"hp={params['highpass']}Hz "
            f"lp={params['lowpass']}Hz "
            f"bits={params['bitcrush']} "
            f"reverb={params['reverb_size']}/{params['reverb_wet']} "
            f"gain={params['gain']}dB")


def parse_config_string(s):
    """Parse a config string like 'pitch=1.5,lofi=16000,bitcrush=14' into a params dict."""
    params = DEFAULT_PARAMS.copy()
    for part in s.split(","):
        key, val = part.strip().split("=")
        key = key.strip()
        val = float(val.strip())
        if key in params:
            params[key] = val
        else:
            print(f"  [WARN] Unknown param: {key}")
    return params


# =========================================================================
# COMMANDS
# =========================================================================

def cmd_preview(args):
    """Apply current settings to a file and play it."""
    params = load_config_params()

    # Apply any overrides from CLI
    if args.pitch is not None: params["pitch"] = args.pitch
    if args.lofi is not None: params["lofi"] = args.lofi
    if args.bitcrush is not None: params["bitcrush"] = args.bitcrush
    if args.lowpass is not None: params["lowpass"] = args.lowpass
    if args.highpass is not None: params["highpass"] = args.highpass

    print(f"\n[PREVIEW] {args.input}")
    print(f"  Settings: {params_to_string(params)}")

    audio, sr = load_audio(args.input)
    print(f"  Source: {len(audio)/sr:.1f}s at {sr}Hz")

    print("\n  Playing ORIGINAL...")
    original_int16 = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    play_audio(original_int16, sr)
    time.sleep(0.5)

    print("  Playing BMO EFFECT...")
    processed, _ = apply_voice_effect(audio, sr, params)
    play_audio(processed, sr)

    print("\n  Done! Adjust params with --pitch, --lofi, --bitcrush, etc.")


def cmd_sweep(args):
    """Generate and play variants across a parameter range."""
    params = load_config_params()
    audio, sr = load_audio(args.input)

    param_name = args.param
    if param_name not in DEFAULT_PARAMS:
        print(f"[ERROR] Unknown parameter: {param_name}")
        print(f"  Available: {', '.join(DEFAULT_PARAMS.keys())}")
        sys.exit(1)

    # Generate sweep values
    values = []
    v = args.min
    while v <= args.max + 0.001:
        values.append(round(v, 2))
        v += args.step

    print(f"\n[SWEEP] {param_name}: {values}")
    print(f"  Source: {args.input} ({len(audio)/sr:.1f}s)")
    print(f"  Base settings: {params_to_string(params)}")

    # Output directory for sweep files
    sweep_dir = os.path.join(os.path.dirname(args.input) or ".", "voice_sweep")
    os.makedirs(sweep_dir, exist_ok=True)

    for i, val in enumerate(values):
        sweep_params = params.copy()
        sweep_params[param_name] = val

        # Use int for integer-like params
        display_val = int(val) if val == int(val) else val

        print(f"\n  [{i+1}/{len(values)}] {param_name}={display_val}")
        processed, _ = apply_voice_effect(audio, sr, sweep_params)

        # Save to file
        filename = f"sweep_{param_name}_{display_val}.wav"
        filepath = os.path.join(sweep_dir, filename)
        sf.write(filepath, processed, sr, subtype="PCM_16")

        # Play
        print(f"    Playing... (saved: {filepath})")
        play_audio(processed, sr)
        time.sleep(0.3)

    print(f"\n  Sweep files saved to: {sweep_dir}/")
    print("  Listen to each and pick your favorite!")


def cmd_ab(args):
    """A/B compare two configurations."""
    audio, sr = load_audio(args.input)

    params_a = parse_config_string(args.a)
    params_b = parse_config_string(args.b)

    print(f"\n[A/B COMPARE] {args.input}")
    print(f"  Config A: {params_to_string(params_a)}")
    print(f"  Config B: {params_to_string(params_b)}")

    processed_a, _ = apply_voice_effect(audio, sr, params_a)
    processed_b, _ = apply_voice_effect(audio, sr, params_b)

    rounds = args.rounds
    for r in range(rounds):
        print(f"\n  Round {r+1}/{rounds}:")
        print("    Playing A...", end="", flush=True)
        play_audio(processed_a, sr)
        print(" done")
        time.sleep(0.5)
        print("    Playing B...", end="", flush=True)
        play_audio(processed_b, sr)
        print(" done")

        if r < rounds - 1:
            time.sleep(1.0)

    print("\n  Which sounds more like BMO? A or B?")


def cmd_export(args):
    """Apply settings and export processed audio."""
    params = load_config_params()

    if args.pitch is not None: params["pitch"] = args.pitch
    if args.lofi is not None: params["lofi"] = args.lofi
    if args.bitcrush is not None: params["bitcrush"] = args.bitcrush
    if args.lowpass is not None: params["lowpass"] = args.lowpass
    if args.highpass is not None: params["highpass"] = args.highpass

    audio, sr = load_audio(args.input)

    print(f"\n[EXPORT] {args.input} → {args.output}")
    print(f"  Settings: {params_to_string(params)}")

    processed, _ = apply_voice_effect(audio, sr, params)
    sf.write(args.output, processed, sr, subtype="PCM_16")
    print(f"  Saved: {args.output} ({len(processed)/sr:.1f}s)")


# =========================================================================
# MAIN
# =========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="BMO Voice Tuning Tool — find the perfect BMO voice effect settings",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- preview ---
    p_preview = subparsers.add_parser("preview", help="Play original vs processed")
    p_preview.add_argument("--input", "-i", required=True, help="Input WAV file")
    p_preview.add_argument("--pitch", type=float, help="Pitch shift (semitones)")
    p_preview.add_argument("--lofi", type=float, help="Lo-fi sample rate (Hz)")
    p_preview.add_argument("--bitcrush", type=float, help="Bitcrush bit depth")
    p_preview.add_argument("--lowpass", type=float, help="Lowpass cutoff (Hz)")
    p_preview.add_argument("--highpass", type=float, help="Highpass cutoff (Hz)")

    # --- sweep ---
    p_sweep = subparsers.add_parser("sweep", help="Sweep a parameter range")
    p_sweep.add_argument("--input", "-i", required=True, help="Input WAV file")
    p_sweep.add_argument("--param", "-p", required=True, help="Parameter to sweep")
    p_sweep.add_argument("--min", type=float, required=True, help="Minimum value")
    p_sweep.add_argument("--max", type=float, required=True, help="Maximum value")
    p_sweep.add_argument("--step", type=float, required=True, help="Step size")

    # --- ab ---
    p_ab = subparsers.add_parser("ab", help="A/B compare two configs")
    p_ab.add_argument("--input", "-i", required=True, help="Input WAV file")
    p_ab.add_argument("--a", required=True, help="Config A (e.g., 'pitch=1.5,lofi=16000')")
    p_ab.add_argument("--b", required=True, help="Config B")
    p_ab.add_argument("--rounds", type=int, default=3, help="Number of A/B rounds")

    # --- export ---
    p_export = subparsers.add_parser("export", help="Export processed audio")
    p_export.add_argument("--input", "-i", required=True, help="Input WAV file")
    p_export.add_argument("--output", "-o", required=True, help="Output WAV file")
    p_export.add_argument("--pitch", type=float, help="Pitch shift (semitones)")
    p_export.add_argument("--lofi", type=float, help="Lo-fi sample rate (Hz)")
    p_export.add_argument("--bitcrush", type=float, help="Bitcrush bit depth")
    p_export.add_argument("--lowpass", type=float, help="Lowpass cutoff (Hz)")
    p_export.add_argument("--highpass", type=float, help="Highpass cutoff (Hz)")

    args = parser.parse_args()

    if args.command == "preview":
        cmd_preview(args)
    elif args.command == "sweep":
        cmd_sweep(args)
    elif args.command == "ab":
        cmd_ab(args)
    elif args.command == "export":
        cmd_export(args)


if __name__ == "__main__":
    main()
