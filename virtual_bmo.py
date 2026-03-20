#!/usr/bin/env python3
"""
Virtual BMO — Full-Featured Desktop Simulator
Test BMO's personality, voice, vision, and streaming responses without hardware.

Features:
  - Streaming Claude responses (word-by-word display)
  - ElevenLabs TTS with BMO voice effect chain
  - Webcam vision via Claude Vision API
  - DuckDuckGo web search
  - Persistent memory (memory.json)
  - Thinking sounds + sound effects
  - Interrupt support (Escape key)
  - Graceful degradation (text-only if deps missing)

Usage: python virtual_bmo.py
"""

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import threading
import time
import json
import os
import random
import re
import datetime
import sys
import atexit
import base64
import io
import warnings

warnings.filterwarnings("ignore", category=RuntimeWarning, module="duckduckgo_search")

import anthropic

# =========================================================================
# GRACEFUL DEGRADATION FLAGS
# Each optional feature checks its flag before use.
# With zero optional deps, text-only chat still works.
# =========================================================================

HAS_AUDIO = False
try:
    import sounddevice as sd
    import numpy as np
    import scipy.signal
    import wave
    import struct
    # Voice effect deps
    import librosa
    from pedalboard import Pedalboard, HighpassFilter, LowpassFilter, Bitcrush, Reverb, Gain
    HAS_AUDIO = True
    print("[INIT] Audio: enabled (sounddevice + librosa + pedalboard)")
except ImportError as e:
    print(f"[INIT] Audio: disabled ({e})")

HAS_VISION = False
try:
    from PIL import ImageGrab
    HAS_VISION = True
    print("[INIT] Vision: enabled (screen capture via PIL.ImageGrab)")
except ImportError as e:
    print(f"[INIT] Vision: disabled ({e})")

HAS_SEARCH = False
try:
    from ddgs import DDGS
    HAS_SEARCH = True
    print("[INIT] Search: enabled (duckduckgo)")
except ImportError as e:
    print(f"[INIT] Search: disabled ({e})")


# =========================================================================
# CONFIGURATION
# =========================================================================

CONFIG_FILE = "config.json"
MEMORY_FILE = "memory.json"
FACE_DIR = "faces"
SOUNDS_DIR = "sounds"

DEFAULT_CONFIG = {
    "text_model": "claude-haiku-4-5-20251001",
    "smart_model": "claude-sonnet-4-6",
    "personality_file": "prompts/bmo_companion.txt",
    "system_prompt_extras": "",
    "max_tokens": 256,
    "smart_routing": True,
    "tts_engine": "elevenlabs",
    "elevenlabs_voice_id": "",
    "elevenlabs_model": "eleven_turbo_v2_5",
    "bmo_post_processing": True,
    "bmo_pitch_shift": 1.5,
    "bmo_lofi_sample_rate": 16000,
    "chat_memory": True,
}

def load_config():
    config = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                config.update(json.load(f))
        except Exception as e:
            print(f"Config Error: {e}")
    return config

CONFIG = load_config()

# Audio constants
ELEVEN_RATE = 22050
TTS_CHUNK_SIZE = 4096

# ElevenLabs client (optional)
ELEVENLABS_CLIENT = None
if HAS_AUDIO and CONFIG.get("tts_engine") == "elevenlabs":
    try:
        from elevenlabs.client import ElevenLabs
        ELEVENLABS_CLIENT = ElevenLabs()  # Uses ELEVEN_API_KEY env var
        print(f"[INIT] ElevenLabs TTS: enabled (voice: {CONFIG.get('elevenlabs_voice_id', 'not set')})")
    except Exception as e:
        print(f"[INIT] ElevenLabs TTS: disabled ({e})")

# BMO voice effect chain (built once, reused)
BMO_VOICE_CHAIN = None
if HAS_AUDIO:
    BMO_VOICE_CHAIN = Pedalboard([
        HighpassFilter(cutoff_frequency_hz=250),
        LowpassFilter(cutoff_frequency_hz=8500),
        Bitcrush(bit_depth=14),
        Reverb(room_size=0.05, wet_level=0.08),
        Gain(gain_db=2),
    ])

# Load personality
def load_personality():
    pfile = CONFIG.get("personality_file", "prompts/bmo_companion.txt")
    if os.path.exists(pfile):
        with open(pfile, "r") as f:
            prompt = f.read().strip()
        print(f"[INIT] Personality: {pfile}")
    else:
        prompt = "You are BMO, a helpful robot companion. Keep responses short and fun."
        print("[INIT] Personality file not found, using default")
    extras = CONFIG.get("system_prompt_extras", "")
    if extras:
        prompt += "\n\n" + extras
    return prompt

SYSTEM_PROMPT = load_personality()

# Claude client
API_KEY = os.environ.get("PERSONAL_ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
if not API_KEY:
    print("[ERROR] No API key found! Set PERSONAL_ANTHROPIC_API_KEY or ANTHROPIC_API_KEY")
    sys.exit(1)
CLIENT = anthropic.Anthropic(api_key=API_KEY)
TEXT_MODEL = CONFIG["text_model"]
SMART_MODEL = CONFIG.get("smart_model", TEXT_MODEL)
SMART_ROUTING = CONFIG.get("smart_routing", False)

# Import unified mood mapping
try:
    from generate_faces import MOOD_TO_FACE
except ImportError:
    MOOD_TO_FACE = {}


# =========================================================================
# MODULE-LEVEL FUNCTIONS
# =========================================================================

def apply_bmo_voice_effect(audio_array, sample_rate=22050):
    """Apply BMO game-console voice effect chain.
    Pitch shift → lo-fi downsample → pedalboard (highpass/lowpass/bitcrush/reverb/gain).
    """
    if not HAS_AUDIO or BMO_VOICE_CHAIN is None:
        return audio_array, sample_rate
    if not CONFIG.get("bmo_post_processing", True):
        return audio_array, sample_rate

    y = audio_array.astype(np.float32)
    if np.max(np.abs(y)) > 1.0:
        y = y / 32768.0

    pitch_shift = CONFIG.get("bmo_pitch_shift", 1.5)
    lofi_rate = CONFIG.get("bmo_lofi_sample_rate", 16000)

    # Step 1: Pitch shift up (childlike register)
    if pitch_shift != 0:
        y = librosa.effects.pitch_shift(y, sr=sample_rate, n_steps=pitch_shift)

    # Step 2: Lo-fi downsample trick (device-like aliasing)
    if 0 < lofi_rate < sample_rate:
        y = librosa.resample(y, orig_sr=sample_rate, target_sr=lofi_rate)
        y = librosa.resample(y, orig_sr=lofi_rate, target_sr=sample_rate)

    # Step 3: Pedalboard effects chain
    y_2d = y.reshape(1, -1)
    y_processed = BMO_VOICE_CHAIN(y_2d, sample_rate).flatten()

    # Convert back to int16
    y_processed = np.clip(y_processed, -1.0, 1.0)
    y_processed = (y_processed * 32767).astype(np.int16)

    print(f"[BMO VOICE] pitch={pitch_shift}st, lofi={lofi_rate}Hz, chain=on", flush=True)
    return y_processed, sample_rate


def get_random_sound(directory):
    """Get a random WAV file path from a directory."""
    if os.path.exists(directory):
        files = [f for f in os.listdir(directory) if f.lower().endswith(".wav")]
        return os.path.join(directory, random.choice(files)) if files else None
    return None


def play_sound(file_path):
    """Play a WAV file using sounddevice. No-op if audio disabled."""
    if not HAS_AUDIO or not file_path or not os.path.exists(file_path):
        return
    try:
        with wave.open(file_path, 'rb') as wf:
            file_sr = wf.getframerate()
            data = wf.readframes(wf.getnframes())
            audio = np.frombuffer(data, dtype=np.int16)

        try:
            device_info = sd.query_devices(kind='output')
            native_rate = int(device_info['default_samplerate'])
        except Exception:
            native_rate = 48000

        playback_rate = file_sr
        try:
            sd.check_output_settings(device=None, samplerate=file_sr)
        except Exception:
            playback_rate = native_rate
            num_samples = int(len(audio) * (native_rate / file_sr))
            audio = scipy.signal.resample(audio, num_samples).astype(np.int16)

        sd.play(audio, playback_rate)
        sd.wait()
    except Exception:
        pass


def search_web(query):
    """Search DuckDuckGo: news first, text fallback. Returns formatted result or error string."""
    if not HAS_SEARCH:
        return "SEARCH_UNAVAILABLE"
    try:
        with DDGS() as ddgs:
            results = []
            try:
                results = list(ddgs.news(query, region='us-en', max_results=1))
            except Exception:
                pass
            if not results:
                try:
                    results = list(ddgs.text(query, region='us-en', max_results=1))
                except Exception:
                    pass
            if results:
                r = results[0]
                title = r.get('title', 'No Title')
                body = r.get('body', r.get('snippet', 'No Body'))
                return f"SEARCH RESULTS for '{query}':\nTitle: {title}\nSnippet: {body[:300]}"
            return "SEARCH_EMPTY"
    except Exception as e:
        print(f"[SEARCH ERROR] {e}")
        return "SEARCH_ERROR"


# Smart routing
ROUTER_PROMPT = """Classify this user message as SIMPLE or COMPLEX. Reply with only one word.
SIMPLE = greetings, casual chat, jokes, simple questions, short factual answers
COMPLEX = explanations, analysis, advice, multi-step reasoning, detailed questions
Message: "{message}"
Classification:"""

def choose_model(text):
    if not SMART_ROUTING or TEXT_MODEL == SMART_MODEL:
        return TEXT_MODEL
    try:
        safe_text = text.replace("{", "{{").replace("}", "}}")
        resp = CLIENT.messages.create(
            model=TEXT_MODEL, max_tokens=4,
            messages=[{"role": "user", "content": ROUTER_PROMPT.format(message=safe_text)}]
        )
        classification = resp.content[0].text.strip().upper()
        chosen = SMART_MODEL if "COMPLEX" in classification else TEXT_MODEL
        print(f"[ROUTER] {classification} → {chosen}")
        return chosen
    except Exception as e:
        print(f"[ROUTER ERROR] {e}")
        return TEXT_MODEL


# Sound directories
THINKING_SOUNDS_DIR = os.path.join(SOUNDS_DIR, "thinking_sounds")
GREETING_SOUNDS_DIR = os.path.join(SOUNDS_DIR, "greeting_sounds")
ACK_SOUNDS_DIR = os.path.join(SOUNDS_DIR, "ack_sounds")


# =========================================================================
# VIRTUAL BMO GUI
# =========================================================================

class VirtualBMO:
    FACE_WIDTH = 800
    FACE_HEIGHT = 480

    def __init__(self, master):
        self.master = master
        self.running = True
        master.title("Virtual BMO")
        master.resizable(False, False)
        master.configure(bg="#1a1a2e")
        master.protocol("WM_DELETE_WINDOW", self.on_close)

        # --- State ---
        self.current_state = "warmup"
        self.animations = {}
        self.frame_index = 0
        self.is_processing = False
        self.idle_blink_timer = 0
        self.idle_next_blink = random.uniform(3.0, 6.0)
        self.idle_blinking = False
        self.idle_blink_frame = 0

        # --- Memory ---
        self.permanent_memory = []
        self.session_memory = []
        self.load_memory()

        # --- TTS state ---
        self.tts_queue = []
        self.tts_queue_lock = threading.Lock()
        self.tts_active = threading.Event()
        self.thinking_sound_active = threading.Event()
        self.interrupted = threading.Event()

        # Start TTS worker thread
        if HAS_AUDIO:
            tts_thread = threading.Thread(target=self._tts_worker, daemon=True)
            tts_thread.start()

        # Save memory on exit
        atexit.register(self.save_memory)

        # Load face animations
        self.load_animations()

        # --- FACE DISPLAY ---
        self.face_frame = tk.Frame(master, bg="#1a1a2e")
        self.face_frame.pack(pady=(10, 0))

        self.face_label = tk.Label(self.face_frame, bg="#1a1a2e")
        self.face_label.pack()

        # --- STATUS BAR ---
        self.status_var = tk.StringVar(value="BMO is waking up...")
        self.status_label = tk.Label(
            master, textvariable=self.status_var,
            bg="#1a1a2e", fg="#7ECDB0", font=("Courier", 12)
        )
        self.status_label.pack(pady=(5, 0))

        # --- CHAT DISPLAY ---
        self.chat_frame = tk.Frame(master, bg="#1a1a2e")
        self.chat_frame.pack(fill=tk.X, padx=20, pady=(5, 0))

        self.chat_text = tk.Text(
            self.chat_frame, height=6, wrap=tk.WORD,
            bg="#0d1117", fg="#7ECDB0", insertbackground="#7ECDB0",
            font=("Courier", 11), state=tk.DISABLED,
            relief=tk.FLAT, padx=10, pady=10
        )
        scrollbar = tk.Scrollbar(self.chat_frame, command=self.chat_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.chat_text.config(yscrollcommand=scrollbar.set)
        self.chat_text.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Tag configs
        self.chat_text.tag_config("you", foreground="#58a6ff")
        self.chat_text.tag_config("bmo", foreground="#7ECDB0")
        self.chat_text.tag_config("system", foreground="#666666")
        self.chat_text.tag_config("model", foreground="#444444")

        # --- INPUT ---
        self.input_frame = tk.Frame(master, bg="#1a1a2e")
        self.input_frame.pack(fill=tk.X, padx=20, pady=(5, 15))

        self.input_var = tk.StringVar()
        self.input_entry = tk.Entry(
            self.input_frame, textvariable=self.input_var,
            bg="#0d1117", fg="#c9d1d9", insertbackground="#c9d1d9",
            font=("Courier", 12), relief=tk.FLAT
        )
        self.input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=8, padx=(0, 10))
        self.input_entry.bind("<Return>", self.on_send)
        self.input_entry.focus_set()

        self.send_btn = tk.Button(
            self.input_frame, text="Send",
            bg="#238636", fg="white", font=("Courier", 11, "bold"),
            relief=tk.FLAT, padx=20, pady=5,
            command=self.on_send, activebackground="#2ea043"
        )
        self.send_btn.pack(side=tk.RIGHT)

        # --- KEYBOARD SHORTCUTS ---
        master.bind("<Escape>", lambda e: self.interrupt())

        # Start animation loop
        self.update_animation()

        # Warmup sequence
        threading.Thread(target=self.warmup, daemon=True).start()

    # =================================================================
    # ANIMATION
    # =================================================================

    def load_animations(self):
        if os.path.exists(FACE_DIR):
            for state in os.listdir(FACE_DIR):
                folder = os.path.join(FACE_DIR, state)
                if not os.path.isdir(folder):
                    continue
                self.animations[state] = []
                files = sorted([f for f in os.listdir(folder) if f.lower().endswith('.png')])
                for f in files:
                    img = Image.open(os.path.join(folder, f)).resize(
                        (self.FACE_WIDTH, self.FACE_HEIGHT))
                    self.animations[state].append(ImageTk.PhotoImage(img))
        if "idle" not in self.animations:
            blank = Image.new('RGB', (self.FACE_WIDTH, self.FACE_HEIGHT), color='#7ECDB0')
            self.animations["idle"] = [ImageTk.PhotoImage(blank)]
        print(f"[INIT] Loaded {sum(len(v) for v in self.animations.values())} face frames across {len(self.animations)} states")

    STATE_SPEEDS = {
        "speaking": 60, "listening": 150, "thinking": 180,
        "error": 250, "capturing": 300, "warmup": 200,
        "happy": 150, "sad": 350, "love": 200,
        "surprised": 180, "sleeping": 500, "winking": 200,
        "glitch": 100, "singing": 200, "game_mode": 400,
        "angry": 250, "confident": 200, "affectionate": 200,
    }

    def update_animation(self):
        if not self.running:
            return

        frames = self.animations.get(self.current_state, self.animations.get("idle", []))
        if not frames:
            self.master.after(200, self.update_animation)
            return

        speed = 200

        if self.current_state == "idle":
            speed = 100
            self.idle_blink_timer += speed / 1000.0

            if self.idle_blinking:
                blink_frames = [4, 5, 6]
                if self.idle_blink_frame < len(blink_frames):
                    idx = min(blink_frames[self.idle_blink_frame], len(frames) - 1)
                    self.face_label.config(image=frames[idx])
                    self.idle_blink_frame += 1
                else:
                    self.idle_blinking = False
                    self.idle_blink_frame = 0
                    self.idle_blink_timer = 0
                    self.idle_next_blink = random.uniform(3.0, 7.0)
                    if random.random() < 0.15:
                        self.idle_next_blink = random.uniform(0.3, 0.6)
                    if random.random() < 0.1 and len(frames) > 9:
                        self.face_label.config(image=frames[9])
                    else:
                        self.face_label.config(image=frames[0])
            else:
                if self.idle_blink_timer >= self.idle_next_blink:
                    self.idle_blinking = True
                    self.idle_blink_frame = 0
                else:
                    self.face_label.config(image=frames[0])

        elif self.current_state == "speaking":
            self.frame_index = random.randint(0, len(frames) - 1)
            self.face_label.config(image=frames[self.frame_index])
            speed = self.STATE_SPEEDS.get("speaking", 60)
        else:
            self.frame_index = (self.frame_index + 1) % len(frames)
            self.face_label.config(image=frames[self.frame_index])
            speed = self.STATE_SPEEDS.get(self.current_state, 200)

        self.master.after(speed, self.update_animation)

    # =================================================================
    # THREAD-SAFE GUI WRAPPERS
    # =================================================================

    def set_state(self, state, status_msg=""):
        self.current_state = state
        self.frame_index = 0
        if status_msg:
            self.status_var.set(status_msg)

    def _set_state_safe(self, state, status_msg=""):
        try:
            if self.running:
                self.master.after(0, lambda: self.set_state(state, status_msg))
        except tk.TclError:
            pass

    def append_chat(self, text, tag="bmo"):
        self.chat_text.config(state=tk.NORMAL)
        self.chat_text.insert(tk.END, text + "\n", tag)
        self.chat_text.see(tk.END)
        self.chat_text.config(state=tk.DISABLED)

    def _append_chat_safe(self, text, tag="bmo"):
        try:
            if self.running:
                self.master.after(0, lambda t=text, tg=tag: self.append_chat(t, tg))
        except tk.TclError:
            pass

    def _stream_to_chat(self, text, tag="bmo"):
        """Thread-safe: append text without newline (for streaming word-by-word)."""
        def _do():
            try:
                self.chat_text.config(state=tk.NORMAL)
                self.chat_text.insert(tk.END, text, tag)
                self.chat_text.see(tk.END)
                self.chat_text.config(state=tk.DISABLED)
            except tk.TclError:
                pass
        try:
            if self.running:
                self.master.after(0, _do)
        except tk.TclError:
            pass

    # =================================================================
    # TTS SYSTEM
    # =================================================================

    def _tts_worker(self):
        """Background thread: pulls sentences from tts_queue and speaks them."""
        while self.running:
            sentence = None
            with self.tts_queue_lock:
                if self.tts_queue:
                    sentence = self.tts_queue.pop(0)
                    self.tts_active.set()  # Set inside lock to prevent wait_for_tts race
            if sentence:
                self.speak(sentence)
                self.tts_active.clear()
            else:
                time.sleep(0.05)

    def speak(self, text):
        """Speak text using available TTS engine."""
        if not HAS_AUDIO:
            return
        clean = re.sub(r"[^\w\s,.!?:'()-]", "", text)
        if not clean.strip():
            return
        if ELEVENLABS_CLIENT:
            self.speak_elevenlabs(clean)
        else:
            print(f"[TTS] No TTS engine available. Would say: '{clean}'")

    def speak_elevenlabs(self, text):
        """Speak using ElevenLabs API with BMO voice post-processing."""
        voice_id = CONFIG.get("elevenlabs_voice_id", "")
        if not voice_id:
            print("[TTS] No ElevenLabs voice_id configured!", flush=True)
            return

        print(f"[ELEVENLABS] '{text}'", flush=True)
        try:
            audio_generator = ELEVENLABS_CLIENT.text_to_speech.convert(
                text=text,
                voice_id=voice_id,
                model_id=CONFIG.get("elevenlabs_model", "eleven_turbo_v2_5"),
                output_format="pcm_22050",
            )

            # Collect audio chunks
            audio_data = b""
            for chunk in audio_generator:
                if self.interrupted.is_set():
                    break
                audio_data += chunk

            if not audio_data or self.interrupted.is_set():
                return

            # Apply BMO voice post-processing
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            audio_array, _ = apply_bmo_voice_effect(audio_array, ELEVEN_RATE)

            # Determine playback rate
            try:
                device_info = sd.query_devices(kind='output')
                native_rate = int(device_info['default_samplerate'])
            except Exception:
                native_rate = 48000

            playback_rate = ELEVEN_RATE
            try:
                sd.check_output_settings(device=None, samplerate=ELEVEN_RATE)
            except Exception:
                num_samples = int(len(audio_array) * (native_rate / ELEVEN_RATE))
                audio_array = scipy.signal.resample(audio_array, num_samples).astype(np.int16)
                playback_rate = native_rate

            # Chunked playback with interrupt support
            with sd.RawOutputStream(samplerate=playback_rate, channels=1, dtype='int16',
                                    device=None, latency='low', blocksize=2048) as out_stream:
                for i in range(0, len(audio_array), TTS_CHUNK_SIZE):
                    if self.interrupted.is_set():
                        break
                    chunk = audio_array[i:i + TTS_CHUNK_SIZE]
                    out_stream.write(chunk.astype(np.int16).tobytes())
                time.sleep(0.3)

        except Exception as e:
            print(f"[ELEVENLABS ERROR] {e}", flush=True)

    def wait_for_tts(self):
        """Block until TTS queue is drained or interrupted."""
        while True:
            if self.interrupted.is_set():
                break
            with self.tts_queue_lock:
                if not self.tts_queue and not self.tts_active.is_set():
                    break
            time.sleep(0.1)

    # =================================================================
    # SOUND EFFECTS
    # =================================================================

    def _run_thinking_sound_loop(self):
        """Play random thinking sounds while thinking_sound_active is set."""
        time.sleep(0.5)
        while self.thinking_sound_active.is_set():
            sound = get_random_sound(THINKING_SOUNDS_DIR)
            if sound:
                play_sound(sound)
            # Check every 100ms for 5s total between sounds
            for _ in range(50):
                if not self.thinking_sound_active.is_set():
                    return
                time.sleep(0.1)

    # =================================================================
    # VISION (WEBCAM → CLAUDE VISION API)
    # =================================================================

    def capture_screen(self):
        """Capture the computer screen, return base64 JPEG or None.
        Virtual BMO sees the screen (not a webcam) — useful for desktop testing.
        """
        if not HAS_VISION:
            return None
        try:
            self._set_state_safe("capturing", "BMO is looking at the screen...")
            screenshot = ImageGrab.grab()
            # Resize to limit token usage (max 1024px on longest side)
            max_dim = 1024
            ratio = min(max_dim / screenshot.width, max_dim / screenshot.height, 1.0)
            if ratio < 1.0:
                new_size = (int(screenshot.width * ratio), int(screenshot.height * ratio))
                screenshot = screenshot.resize(new_size, Image.LANCZOS)

            # Encode as JPEG → base64
            buffer = io.BytesIO()
            screenshot.save(buffer, format="JPEG", quality=80)
            b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            print(f"[VISION] Screen captured ({screenshot.width}x{screenshot.height}, {len(b64)} bytes b64)")
            return b64
        except Exception as e:
            print(f"[VISION ERROR] {e}")
            return None

    # =================================================================
    # ACTION HANDLER
    # =================================================================

    def _handle_action(self, action_data, original_text):
        """Handle a tool action from Claude's response.
        Returns (reply_text, mood) or None if action triggers a re-chat (like vision).
        """
        action = action_data.get("action", "")
        value = action_data.get("value", action_data.get("query", ""))

        if action == "get_time":
            now = datetime.datetime.now().strftime("%I:%M %p")
            return f"It is {now}! That is a very good time!", "happy"

        elif action == "search_web":
            if not HAS_SEARCH:
                return "BMO cannot search the internet right now. BMO's search module is not installed!", "sad"

            self._set_state_safe("thinking", "BMO is searching...")
            result = search_web(value)

            if result in ("SEARCH_EMPTY", "SEARCH_ERROR", "SEARCH_UNAVAILABLE"):
                messages = {
                    "SEARCH_EMPTY": "BMO searched everywhere but could not find anything about that!",
                    "SEARCH_ERROR": "Oh no! BMO cannot reach the internet right now.",
                    "SEARCH_UNAVAILABLE": "BMO's search module is not available!",
                }
                return messages[result], "sad"

            # Ask Claude to summarize the search result in character
            self._set_state_safe("thinking", "BMO is reading...")
            summary_messages = [
                {"role": "user", "content": f"Here is a result BMO found:\n{result}\n\nThe user asked: {original_text}\n\nSummarize this in one short sentence, in character as BMO."}
            ]
            try:
                resp = CLIENT.messages.create(
                    model=TEXT_MODEL,
                    max_tokens=CONFIG.get("max_tokens", 256),
                    system=SYSTEM_PROMPT,
                    messages=summary_messages
                )
                raw = resp.content[0].text
                clean, mood = self.parse_mood_tag(raw)
                return clean, mood
            except Exception as e:
                return f"BMO found something but got confused reading it! ({e})", "error"

        elif action == "capture_image":
            b64_image = self.capture_screen()
            if not b64_image:
                if not HAS_VISION:
                    return "BMO cannot see the screen right now! BMO's vision module is not installed.", "sad"
                return "BMO tried to look at the screen but something went wrong!", "sad"

            # Send image to Claude Vision for description
            self._set_state_safe("thinking", "BMO is looking at the screen...")
            try:
                vision_messages = [
                    {"role": "user", "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64_image}},
                        {"type": "text", "text": f"The user said: \"{original_text}\"\n\nThis is a screenshot of the user's computer screen. Describe what you see, in character as BMO. Keep it short and fun!"}
                    ]}
                ]
                resp = CLIENT.messages.create(
                    model=SMART_MODEL,
                    max_tokens=CONFIG.get("max_tokens", 256),
                    system=SYSTEM_PROMPT,
                    messages=vision_messages
                )
                raw = resp.content[0].text
                clean, mood = self.parse_mood_tag(raw)
                return clean, mood if mood != "idle" else "happy"
            except Exception as e:
                return f"BMO can see but cannot think about what it sees! ({e})", "error"

        return None, "idle"

    # =================================================================
    # STREAMING CHAT
    # =================================================================

    def process_message(self, text):
        """Process a user message: streaming Claude response + sentence TTS + actions + mood."""
        assistant_replied = False
        try:
            time.sleep(0.3)
            self._set_state_safe("thinking", "BMO is thinking...")
            self.interrupted.clear()

            # Start thinking sounds
            if HAS_AUDIO:
                self.thinking_sound_active.set()
                threading.Thread(target=self._run_thinking_sound_loop, daemon=True).start()

            # Choose model via smart routing
            model = choose_model(text)
            model_label = "haiku" if "haiku" in model else "sonnet"

            # Build messages
            self.session_memory.append({"role": "user", "content": text})

            # Vision trigger: if user says look/see/what do you see, capture first
            vision_triggers = ["look", "see", "what do you see", "show me", "take a photo", "take a picture"]
            is_vision_request = any(trigger in text.lower() for trigger in vision_triggers)
            image_b64 = None

            if is_vision_request and HAS_VISION:
                image_b64 = self.capture_screen()

            # Build chat messages with image if captured
            chat_messages = list((self.permanent_memory + self.session_memory)[-20:])
            if image_b64 and chat_messages:
                # Replace the last user message with a multimodal one
                last_msg = chat_messages[-1]
                if last_msg["role"] == "user":
                    chat_messages[-1] = {
                        "role": "user",
                        "content": [
                            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
                            {"type": "text", "text": text}
                        ]
                    }

            max_tokens = CONFIG.get("max_tokens", 256)
            if model == SMART_MODEL and model != TEXT_MODEL:
                max_tokens = max(max_tokens, 512)

            self._set_state_safe("thinking", f"BMO is thinking... [{model_label}]")

            # --- Streaming response ---
            full_response = ""
            sentence_buffer = ""
            is_action_mode = False
            started_speaking = False

            try:
                with CLIENT.messages.stream(
                    model=model,
                    max_tokens=max_tokens,
                    system=SYSTEM_PROMPT,
                    messages=chat_messages
                ) as stream:
                    for content in stream.text_stream:
                        if self.interrupted.is_set():
                            break
                        full_response += content

                        # Detect action JSON mid-stream (check accumulated buffer
                        # to handle tokens split across chunk boundaries)
                        if not is_action_mode and '"action"' in full_response:
                            is_action_mode = True
                            self.thinking_sound_active.clear()
                            continue

                        if is_action_mode:
                            continue

                        # Stop thinking sounds, switch to speaking
                        self.thinking_sound_active.clear()
                        if not started_speaking:
                            self._set_state_safe("speaking", "BMO is talking!")
                            self._stream_to_chat(f"BMO [{model_label}]: ", "bmo")
                            started_speaking = True

                        # Stream text to GUI word-by-word (strip mood tags)
                        display_content = re.sub(r'\[mood:\w+\]\s*', '', content)
                        if display_content:
                            self._stream_to_chat(display_content, "bmo")

                        # Sentence splitting for TTS
                        sentence_buffer += content
                        if any(punct in content for punct in ".!?\n"):
                            clean_sentence = sentence_buffer.strip()
                            if clean_sentence and re.search(r'[a-zA-Z0-9]', clean_sentence):
                                with self.tts_queue_lock:
                                    self.tts_queue.append(clean_sentence)
                            sentence_buffer = ""

            except Exception as e:
                print(f"[STREAM ERROR] {e}")
                self.thinking_sound_active.clear()
                self._set_state_safe("error", f"Stream error: {str(e)[:40]}")
                self._append_chat_safe(f"* Stream error: {e} *", "system")
                time.sleep(2)
                self._set_state_safe("idle", "BMO recovered!")
                return

            # --- Handle action mode ---
            if is_action_mode:
                action_data = self._extract_json(full_response)
                if action_data:
                    reply, mood = self._handle_action(action_data, text)
                    if reply:
                        self.thinking_sound_active.clear()
                        face = mood if mood != "idle" else "speaking"
                        self._set_state_safe(face, f"BMO is {mood}!")
                        self._append_chat_safe(f"BMO [{model_label}]: {reply}", "bmo")
                        with self.tts_queue_lock:
                            self.tts_queue.append(reply)
                        self.session_memory.append({"role": "assistant", "content": reply})
                        assistant_replied = True
                else:
                    # JSON parse failed — speak raw response
                    fallback = "BMO got confused trying to do that! Let me just talk instead."
                    self.thinking_sound_active.clear()
                    self._set_state_safe("speaking", "Speaking...")
                    self._append_chat_safe(f"BMO [{model_label}]: {fallback}", "bmo")
                    with self.tts_queue_lock:
                        self.tts_queue.append(fallback)
                    self.session_memory.append({"role": "assistant", "content": fallback})
                    assistant_replied = True
            else:
                # Flush remaining sentence buffer
                if sentence_buffer.strip():
                    with self.tts_queue_lock:
                        self.tts_queue.append(sentence_buffer.strip())
                # End the streamed line
                self._stream_to_chat("\n", "bmo")

                # Extract mood and set expression
                clean_response, face_state = self.parse_mood_tag(full_response)
                self.session_memory.append({"role": "assistant", "content": clean_response})
                assistant_replied = True
                if face_state != "idle":
                    self._set_state_safe(face_state, f"BMO is {face_state}!")

            # Wait for TTS to finish
            self.wait_for_tts()

            # Trim session memory
            if len(self.session_memory) > 40:
                self.session_memory = self.session_memory[-20:]
                while len(self.session_memory) > 1 and self.session_memory[0]["role"] != "user":
                    self.session_memory.pop(0)

            # Hold expression briefly
            time.sleep(1.5)
            self._set_state_safe("idle", "BMO is ready!")

        except Exception as e:
            self.thinking_sound_active.clear()
            print(f"[ERROR] {e}")
            self._set_state_safe("error", f"Brain freeze! {str(e)[:40]}")
            self._append_chat_safe(f"* Error: {e} *", "system")
            time.sleep(2)
            self._set_state_safe("idle", "BMO recovered!")
        finally:
            self.is_processing = False
            # Remove dangling user message only if assistant never replied
            if not assistant_replied and self.session_memory and self.session_memory[-1]["role"] == "user":
                self.session_memory.pop()
            try:
                if self.running:
                    self.master.after(0, lambda: self.send_btn.config(state=tk.NORMAL))
                    self.master.after(0, lambda: self.input_entry.config(state=tk.NORMAL))
            except tk.TclError:
                pass

    def _extract_json(self, text):
        """Extract first flat JSON object containing 'action' from text.
        Uses [^{}]* to avoid matching across nested braces.
        """
        for match in re.finditer(r'\{[^{}]*"action"[^{}]*\}', text):
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                continue
        return None

    # =================================================================
    # MEMORY
    # =================================================================

    def load_memory(self):
        """Load persistent memory from memory.json."""
        if not CONFIG.get("chat_memory", True):
            return
        if os.path.exists(MEMORY_FILE):
            try:
                with open(MEMORY_FILE, "r") as f:
                    history = json.load(f)
                    self.permanent_memory = [m for m in history if m.get("role") in ("user", "assistant")]
                    print(f"[MEMORY] Loaded {len(self.permanent_memory)} messages from {MEMORY_FILE}")
            except Exception as e:
                print(f"[MEMORY] Load error: {e}")

    @staticmethod
    def _sanitize_message(msg):
        """Ensure message content is a plain string (strip multimodal/image data)."""
        if isinstance(msg.get("content"), list):
            text_parts = [p["text"] for p in msg["content"]
                          if isinstance(p, dict) and p.get("type") == "text"]
            return {"role": msg["role"], "content": " ".join(text_parts)}
        return msg

    def save_memory(self):
        """Save conversation to memory.json."""
        if not CONFIG.get("chat_memory", True):
            return
        conv = self.permanent_memory + self.session_memory
        conv = [self._sanitize_message(m) for m in conv if m.get("role") in ("user", "assistant")]
        # Keep last 20 messages (10 exchanges)
        if len(conv) > 20:
            conv = conv[-20:]
        try:
            with open(MEMORY_FILE, "w") as f:
                json.dump(conv, f, indent=4)
            print(f"[MEMORY] Saved {len(conv)} messages to {MEMORY_FILE}")
        except Exception as e:
            print(f"[MEMORY] Save error: {e}")

    def parse_mood_tag(self, reply):
        """Extract [mood:STATE] tag from Claude's response."""
        match = re.search(r'\[mood:(\w+)\]\s*$', reply.strip())
        if match:
            mood = match.group(1)
            clean = re.sub(r'\n?\[mood:\w+\]\s*$', '', reply.strip())
            if mood in MOOD_TO_FACE:
                face = MOOD_TO_FACE[mood]
                print(f"[MOOD] {mood} → {face}")
                return clean.strip(), face
            else:
                print(f"[MOOD] unknown '{mood}', defaulting to idle")
                return clean.strip(), "idle"
        return reply.strip(), "idle"

    # =================================================================
    # UI HANDLERS
    # =================================================================

    def on_send(self, event=None):
        text = self.input_var.get().strip()
        if not text or self.is_processing:
            return

        self.input_var.set("")
        self.is_processing = True
        self.send_btn.config(state=tk.DISABLED)
        self.input_entry.config(state=tk.DISABLED)

        self.append_chat(f"You: {text}", "you")
        self.set_state("listening", "BMO heard you!")

        # Play ack sound
        if HAS_AUDIO:
            threading.Thread(target=lambda: play_sound(get_random_sound(ACK_SOUNDS_DIR)), daemon=True).start()

        threading.Thread(target=self.process_message, args=(text,), daemon=True).start()

    def warmup(self):
        # Play greeting sound
        if HAS_AUDIO:
            sound = get_random_sound(GREETING_SOUNDS_DIR)
            if sound:
                play_sound(sound)

        time.sleep(1.5)
        self._set_state_safe("idle", "BMO is ready! Type something!")
        self._append_chat_safe("* BMO boots up *", "system")
        self._append_chat_safe("Hi hi hi! BMO is here! What should we do today?", "bmo")

    def interrupt(self):
        """Escape key: stop speech, clear TTS queue, cancel thinking."""
        if not self.is_processing:
            return
        print("[INTERRUPT] User pressed Escape")
        self.interrupted.set()
        self.thinking_sound_active.clear()
        with self.tts_queue_lock:
            self.tts_queue.clear()
        # Stop any playing audio
        if HAS_AUDIO:
            try:
                sd.stop()
            except Exception:
                pass
        self._set_state_safe("idle", "BMO stopped! What's up?")

    def on_close(self):
        self.running = False
        self.interrupted.set()
        self.thinking_sound_active.clear()
        self.save_memory()
        self.master.after(100, self.master.destroy)


# =========================================================================
# MAIN
# =========================================================================

if __name__ == "__main__":
    print("=== Virtual BMO (Full-Featured) ===")
    print(f"Model: {TEXT_MODEL}")
    print(f"Smart routing: {SMART_ROUTING} → {SMART_MODEL}")
    print(f"Personality: {CONFIG.get('personality_file')}")
    print(f"Mood mapping: {len(MOOD_TO_FACE)} entries")
    print(f"Audio: {'enabled' if HAS_AUDIO else 'disabled'}")
    print(f"Vision: {'enabled' if HAS_VISION else 'disabled'}")
    print(f"Search: {'enabled' if HAS_SEARCH else 'disabled'}")
    print(f"TTS: {'ElevenLabs' if ELEVENLABS_CLIENT else 'none'}")
    print(f"Memory: {MEMORY_FILE}")
    print()

    root = tk.Tk()
    app = VirtualBMO(root)
    root.mainloop()
