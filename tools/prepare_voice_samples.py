#!/usr/bin/env python3
"""
BMO Voice Sample Preparation Tool
==================================
Complete pipeline to prepare audio samples for ElevenLabs voice cloning.

Pipeline:
  1. Extract audio from video files (ffmpeg)
  2. Isolate vocals from music/SFX (Demucs htdemucs_ft)
  3. Split into individual utterances (Silero VAD)
  4. Clean and normalize (HPF + LUFS normalization + peak limiting)
  5. Generate summary report + ready-to-upload folder

Usage:
  # Full pipeline from video files
  python tools/prepare_voice_samples.py --input episodes/ --output voice_samples/

  # From pre-extracted audio (skip video extraction)
  python tools/prepare_voice_samples.py --input raw_audio/ --output voice_samples/ --skip-extract

  # Just clean/normalize existing utterances
  python tools/prepare_voice_samples.py --input utterances/ --output voice_samples/ --clean-only

  # Vocal isolation only (no splitting)
  python tools/prepare_voice_samples.py --input raw_audio/ --output voice_samples/ --isolate-only

Requirements:
  pip install demucs torch torchaudio librosa soundfile pyloudnorm noisereduce scipy numpy
  System: ffmpeg must be installed
"""

import os
import sys
import json
import shutil
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

import numpy as np
import librosa
import soundfile as sf
from scipy.signal import butter, sosfilt

# Optional deps with graceful fallback
try:
    import pyloudnorm as pyln
    HAS_LOUDNORM = True
except ImportError:
    HAS_LOUDNORM = False
    print("[WARN] pyloudnorm not installed — loudness normalization disabled")
    print("       Install: pip install pyloudnorm")

try:
    import noisereduce as nr
    HAS_DENOISE = True
except ImportError:
    HAS_DENOISE = False

# =========================================================================
# CONSTANTS
# =========================================================================

# Target audio specs for ElevenLabs PVC
TARGET_SR = 44100       # 44.1kHz preserves upper harmonics for high-pitched voices
TARGET_CHANNELS = 1     # Mono
TARGET_SUBTYPE = "PCM_16"

# Utterance splitting
MIN_UTTERANCE_SEC = 0.7   # Reject < 0.7s (likely SFX bleed)
MAX_UTTERANCE_SEC = 15.0  # Split > 15s
MIN_SILENCE_MS = 300      # Min silence between utterances
SPEECH_PAD_MS = 150       # Padding on each side of detection
VAD_THRESHOLD = 0.4       # Confidence threshold (lower for soft/breathy speech)

# Cleaning
HPF_CUTOFF = 80.0         # High-pass filter cutoff (Hz)
TARGET_LUFS = -18.0       # Broadcast standard loudness
PEAK_LIMIT_DBFS = -1.0    # Peak headroom
PEAK_LIMIT_LINEAR = 10 ** (PEAK_LIMIT_DBFS / 20)  # ~0.891

# Demucs
DEMUCS_MODEL = "htdemucs_ft"  # Fine-tuned, best for high-pitched voices
DEMUCS_SHIFTS = 5             # Quality: 1=draft, 5=good, 10=best

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".m4v"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac", ".opus"}


# =========================================================================
# STEP 1: EXTRACT AUDIO FROM VIDEO
# =========================================================================

def extract_audio_from_video(video_path, output_dir):
    """Extract audio track from video file as 44.1kHz mono WAV."""
    os.makedirs(output_dir, exist_ok=True)
    stem = Path(video_path).stem
    output_path = os.path.join(output_dir, f"{stem}.wav")

    if os.path.exists(output_path):
        print(f"  [SKIP] Already extracted: {stem}.wav")
        return output_path

    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn",                    # No video
        "-acodec", "pcm_s16le",   # 16-bit PCM
        "-ar", str(TARGET_SR),    # 44.1kHz
        "-ac", "1",               # Mono
        output_path
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"  [OK] Extracted: {stem}.wav")
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"  [ERROR] Failed to extract {video_path}: {e.stderr.decode()[:200]}")
        return None
    except FileNotFoundError:
        print("  [ERROR] ffmpeg not found! Install: brew install ffmpeg")
        sys.exit(1)


def extract_all_audio(input_dir, output_dir):
    """Extract audio from all video files in a directory."""
    files = []
    for f in sorted(Path(input_dir).rglob("*")):
        if f.suffix.lower() in VIDEO_EXTENSIONS:
            files.append(str(f))

    if not files:
        print(f"  No video files found in {input_dir}")
        return []

    print(f"\n[STEP 1] Extracting audio from {len(files)} video files...")
    results = []
    for f in files:
        result = extract_audio_from_video(f, output_dir)
        if result:
            results.append(result)
    return results


# =========================================================================
# STEP 2: VOCAL ISOLATION (DEMUCS)
# =========================================================================

def isolate_vocals(audio_path, output_dir, device="cpu", shifts=DEMUCS_SHIFTS):
    """Isolate vocals using Demucs htdemucs_ft model.

    Uses --two-stems=vocals for cleaner separation (only vocals vs everything else).
    The shifts parameter averages multiple random-shifted passes for quality.
    """
    stem = Path(audio_path).stem
    expected_output = os.path.join(output_dir, DEMUCS_MODEL, stem, "vocals.wav")

    if os.path.exists(expected_output):
        print(f"  [SKIP] Already isolated: {stem}")
        return expected_output

    cmd = [
        sys.executable, "-m", "demucs",
        "--two-stems", "vocals",
        "-n", DEMUCS_MODEL,
        "--device", device,
        "--clip-mode", "rescale",
        "--shifts", str(shifts),
        "-o", output_dir,
        audio_path,
    ]

    try:
        print(f"  [DEMUCS] Isolating vocals: {stem} (shifts={shifts}, this may take a while)...")
        subprocess.run(cmd, check=True, capture_output=True)
        if os.path.exists(expected_output):
            print(f"  [OK] Vocals isolated: {stem}")
            return expected_output
        else:
            print(f"  [ERROR] Expected output not found: {expected_output}")
            return None
    except subprocess.CalledProcessError as e:
        print(f"  [ERROR] Demucs failed on {stem}: {e.stderr.decode()[:300]}")
        return None


def isolate_all_vocals(audio_files, output_dir, device="cpu"):
    """Run vocal isolation on all audio files."""
    print(f"\n[STEP 2] Isolating vocals from {len(audio_files)} files (Demucs {DEMUCS_MODEL})...")
    results = []
    for f in audio_files:
        result = isolate_vocals(f, output_dir, device=device)
        if result:
            results.append(result)
    return results


# =========================================================================
# STEP 3: UTTERANCE SPLITTING (SILERO VAD)
# =========================================================================

_vad_model = None
_vad_utils = None

def _load_vad():
    """Lazy-load Silero VAD model."""
    global _vad_model, _vad_utils
    if _vad_model is not None:
        return _vad_model, _vad_utils

    import torch
    print("  [VAD] Loading Silero VAD model...")
    model, utils = torch.hub.load(
        repo_or_dir="snakers4/silero-vad",
        model="silero_vad",
        force_reload=False,
        onnx=False,
    )
    _vad_model = model
    _vad_utils = utils
    return model, utils


def split_utterances(audio_path, output_dir, threshold=VAD_THRESHOLD):
    """Split audio into individual utterances using Silero VAD."""
    import torch
    import torchaudio

    os.makedirs(output_dir, exist_ok=True)
    model, utils = _load_vad()
    get_speech_timestamps, save_audio, read_audio, _, _ = utils

    stem = Path(audio_path).stem

    # Load at target SR for export
    waveform, sr = torchaudio.load(audio_path)
    if sr != TARGET_SR:
        waveform = torchaudio.transforms.Resample(sr, TARGET_SR)(waveform)
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)

    # Silero needs 16kHz
    wav_16k = read_audio(audio_path, sampling_rate=16000)

    speech_timestamps = get_speech_timestamps(
        wav_16k,
        model,
        threshold=threshold,
        min_speech_duration_ms=int(MIN_UTTERANCE_SEC * 1000),
        max_speech_duration_s=MAX_UTTERANCE_SEC,
        min_silence_duration_ms=MIN_SILENCE_MS,
        speech_pad_ms=SPEECH_PAD_MS,
        return_seconds=False,
        sampling_rate=16000,
    )

    results = []
    for i, ts in enumerate(speech_timestamps):
        start_sec = ts["start"] / 16000
        end_sec = ts["end"] / 16000
        start_sample = int(start_sec * TARGET_SR)
        end_sample = int(end_sec * TARGET_SR)

        start_sample = max(0, start_sample)
        end_sample = min(waveform.shape[1], end_sample)

        chunk = waveform[:, start_sample:end_sample]
        duration = (end_sample - start_sample) / TARGET_SR

        if duration < MIN_UTTERANCE_SEC or duration > MAX_UTTERANCE_SEC:
            continue

        filename = f"{stem}_utt{i:04d}_{start_sec:.2f}-{end_sec:.2f}.wav"
        filepath = os.path.join(output_dir, filename)

        torchaudio.save(filepath, chunk, TARGET_SR,
                        encoding="PCM_S", bits_per_sample=16)

        results.append({
            "file": filepath,
            "start": round(start_sec, 2),
            "end": round(end_sec, 2),
            "duration": round(duration, 2),
        })

    print(f"  [OK] {len(results)} utterances from {stem} "
          f"(rejected {len(speech_timestamps) - len(results)} too short/long)")
    return results


def split_all_utterances(vocal_files, output_dir):
    """Split all vocal files into utterances."""
    print(f"\n[STEP 3] Splitting {len(vocal_files)} files into utterances (Silero VAD)...")
    all_results = []
    for f in vocal_files:
        results = split_utterances(f, output_dir)
        all_results.extend(results)
    return all_results


# =========================================================================
# STEP 4: CLEAN AND NORMALIZE
# =========================================================================

def highpass_filter(y, sr, cutoff=HPF_CUTOFF, order=4):
    """Gentle high-pass filter to remove rumble."""
    nyq = 0.5 * sr
    sos = butter(order, cutoff / nyq, btype='high', output='sos')
    return sosfilt(sos, y)


def clean_and_normalize(infile, outfile, apply_denoise=False, denoise_strength=0.5):
    """Clean a single utterance: HPF → optional denoise → LUFS normalize → peak limit.

    Minimal processing preserves voice character for cloning.
    """
    y, sr = librosa.load(infile, sr=TARGET_SR, mono=True)

    # 1. High-pass filter — remove rumble below 80Hz
    y = highpass_filter(y, sr)

    # 2. Optional noise reduction (conservative — only if needed)
    if apply_denoise and HAS_DENOISE:
        y = nr.reduce_noise(y=y, sr=sr, prop_decrease=denoise_strength)

    # 3. LUFS loudness normalization
    if HAS_LOUDNORM:
        meter = pyln.Meter(sr)
        loudness = meter.integrated_loudness(y)
        if not np.isinf(loudness):
            y = pyln.normalize.loudness(y, loudness, TARGET_LUFS)

    # 4. Peak limiting — cap at -1 dBFS
    peak = np.max(np.abs(y))
    if peak > PEAK_LIMIT_LINEAR:
        y = y * (PEAK_LIMIT_LINEAR / peak)

    sf.write(outfile, y, sr, subtype=TARGET_SUBTYPE)


def clean_all_utterances(utterances, output_dir, apply_denoise=False):
    """Clean and normalize all utterances."""
    print(f"\n[STEP 4] Cleaning {len(utterances)} utterances...")
    os.makedirs(output_dir, exist_ok=True)

    cleaned = []
    for utt in utterances:
        filename = Path(utt["file"]).name
        outpath = os.path.join(output_dir, filename)
        try:
            clean_and_normalize(utt["file"], outpath, apply_denoise=apply_denoise)
            cleaned.append({**utt, "file": outpath})
        except Exception as e:
            print(f"  [WARN] Failed to clean {filename}: {e}")

    print(f"  [OK] Cleaned {len(cleaned)}/{len(utterances)} utterances")
    return cleaned


# =========================================================================
# STEP 5: SUMMARY REPORT
# =========================================================================

def generate_report(cleaned_utterances, output_dir):
    """Generate a summary report of the prepared samples."""
    total_duration = sum(u["duration"] for u in cleaned_utterances)
    durations = [u["duration"] for u in cleaned_utterances]

    report = {
        "generated": datetime.now().isoformat(),
        "total_utterances": len(cleaned_utterances),
        "total_duration_sec": round(total_duration, 1),
        "total_duration_min": round(total_duration / 60, 1),
        "avg_duration_sec": round(np.mean(durations), 2) if durations else 0,
        "min_duration_sec": round(min(durations), 2) if durations else 0,
        "max_duration_sec": round(max(durations), 2) if durations else 0,
        "target_specs": {
            "sample_rate": TARGET_SR,
            "bit_depth": 16,
            "channels": TARGET_CHANNELS,
            "format": "WAV PCM",
            "lufs_target": TARGET_LUFS,
        },
        "elevenlabs_ready": total_duration >= 60,  # Min 1 minute for PVC
        "quality_tier": (
            "excellent" if total_duration >= 1800 else
            "good" if total_duration >= 600 else
            "usable" if total_duration >= 300 else
            "minimum" if total_duration >= 60 else
            "insufficient"
        ),
        "utterances": cleaned_utterances,
    }

    report_path = os.path.join(output_dir, "voice_samples_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"  BMO VOICE SAMPLE PREPARATION — COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Utterances:  {report['total_utterances']}")
    print(f"  Duration:    {report['total_duration_min']} minutes ({report['total_duration_sec']}s)")
    print(f"  Avg length:  {report['avg_duration_sec']}s")
    print(f"  Quality:     {report['quality_tier'].upper()}")
    print(f"  ElevenLabs:  {'READY' if report['elevenlabs_ready'] else 'NEED MORE SAMPLES'}")
    print(f"  Output:      {output_dir}/")
    print(f"  Report:      {report_path}")
    print()

    if not report["elevenlabs_ready"]:
        print(f"  ⚠ Need at least 1 minute of audio for ElevenLabs PVC.")
        print(f"    Currently have {report['total_duration_sec']}s. Add more source files.")
    elif report["quality_tier"] in ("minimum", "usable"):
        print(f"  Tip: 10-30 minutes of clean audio produces much better clones.")
        print(f"       Add more source files for better quality.")
    print()

    # Quality targets
    print("  ElevenLabs PVC quality targets:")
    print("    < 1 min  — Insufficient (won't work)")
    print("    1-5 min  — Minimum (robotic, limited)")
    print("    5-10 min — Usable (recognizable)")
    print("   10-30 min — Good (solid clone) ← AIM HERE")
    print("   30-60 min — Excellent (broadcast quality)")
    print()

    return report


# =========================================================================
# MAIN PIPELINE
# =========================================================================

def find_input_files(input_dir):
    """Find all video and audio files in input directory."""
    videos, audios = [], []
    for f in sorted(Path(input_dir).rglob("*")):
        if f.suffix.lower() in VIDEO_EXTENSIONS:
            videos.append(str(f))
        elif f.suffix.lower() in AUDIO_EXTENSIONS:
            audios.append(str(f))
    return videos, audios


def main():
    parser = argparse.ArgumentParser(
        description="BMO Voice Sample Preparation Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full pipeline from video files
  python tools/prepare_voice_samples.py --input episodes/ --output voice_samples/

  # From pre-extracted audio
  python tools/prepare_voice_samples.py --input raw_audio/ --output voice_samples/ --skip-extract

  # Just clean existing utterances
  python tools/prepare_voice_samples.py --input utterances/ --output voice_samples/ --clean-only

  # Use GPU for faster Demucs processing
  python tools/prepare_voice_samples.py --input episodes/ --output voice_samples/ --device cuda

  # Apply noise reduction (use carefully — can hurt clone quality)
  python tools/prepare_voice_samples.py --input episodes/ --output voice_samples/ --denoise
        """
    )
    parser.add_argument("--input", "-i", required=True, help="Input directory (videos, audio, or utterances)")
    parser.add_argument("--output", "-o", required=True, help="Output directory for prepared samples")
    parser.add_argument("--device", default="cpu", help="Demucs device: cpu, cuda, mps (default: cpu)")
    parser.add_argument("--shifts", type=int, default=DEMUCS_SHIFTS, help=f"Demucs quality shifts (default: {DEMUCS_SHIFTS})")
    parser.add_argument("--vad-threshold", type=float, default=VAD_THRESHOLD, help=f"VAD confidence threshold (default: {VAD_THRESHOLD})")
    parser.add_argument("--denoise", action="store_true", help="Apply noise reduction (conservative)")
    parser.add_argument("--skip-extract", action="store_true", help="Skip video→audio extraction")
    parser.add_argument("--isolate-only", action="store_true", help="Only run vocal isolation (no splitting/cleaning)")
    parser.add_argument("--clean-only", action="store_true", help="Only clean/normalize (input = utterance WAVs)")
    args = parser.parse_args()

    input_dir = args.input
    output_dir = args.output

    if not os.path.exists(input_dir):
        print(f"[ERROR] Input directory not found: {input_dir}")
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    # Working directories
    extracted_dir = os.path.join(output_dir, "01_extracted")
    separated_dir = os.path.join(output_dir, "02_separated")
    utterances_dir = os.path.join(output_dir, "03_utterances")
    cleaned_dir = os.path.join(output_dir, "04_cleaned")

    # --- CLEAN ONLY MODE ---
    if args.clean_only:
        audio_files = sorted(str(f) for f in Path(input_dir).rglob("*.wav"))
        if not audio_files:
            print(f"[ERROR] No WAV files found in {input_dir}")
            sys.exit(1)
        utterances = [{"file": f, "start": 0, "end": 0,
                       "duration": librosa.get_duration(path=f)} for f in audio_files]
        cleaned = clean_all_utterances(utterances, cleaned_dir, apply_denoise=args.denoise)
        generate_report(cleaned, output_dir)
        return

    # --- FIND INPUT FILES ---
    videos, audios = find_input_files(input_dir)
    print(f"\n[INPUT] Found {len(videos)} video files, {len(audios)} audio files in {input_dir}")

    # --- STEP 1: EXTRACT AUDIO ---
    if not args.skip_extract and videos:
        extracted = extract_all_audio(input_dir, extracted_dir)
        audios.extend(extracted)

    if not audios:
        print("[ERROR] No audio files to process. Provide video or audio files.")
        sys.exit(1)

    # --- STEP 2: VOCAL ISOLATION ---
    vocals = isolate_all_vocals(audios, separated_dir, device=args.device)

    if not vocals:
        print("[ERROR] Vocal isolation failed for all files.")
        sys.exit(1)

    if args.isolate_only:
        print(f"\n[DONE] Isolated vocals saved to: {separated_dir}/")
        print("  Run again without --isolate-only to continue the pipeline.")
        return

    # --- STEP 3: SPLIT UTTERANCES ---
    all_utterances = split_all_utterances(vocals, utterances_dir)

    if not all_utterances:
        print("[ERROR] No utterances detected. Try lowering --vad-threshold.")
        sys.exit(1)

    # --- STEP 4: CLEAN AND NORMALIZE ---
    cleaned = clean_all_utterances(all_utterances, cleaned_dir, apply_denoise=args.denoise)

    # --- STEP 5: REPORT ---
    generate_report(cleaned, output_dir)


if __name__ == "__main__":
    main()
