#!/usr/bin/env python3
"""
Virtual BMO — Desktop Simulator
Test BMO's personality, face animations, and responses without hardware.

Usage: python virtual_bmo.py
Type messages in the text field and press Enter to talk to BMO.
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

import anthropic

# =========================================================================
# CONFIGURATION
# =========================================================================

CONFIG_FILE = "config.json"
FACE_DIR = "faces"
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600  # Extra height for chat panel below face

DEFAULT_CONFIG = {
    "text_model": "claude-haiku-4-5-20251001",
    "smart_model": "claude-sonnet-4-5-20241022",
    "personality_file": "prompts/bmo_companion.txt",
    "system_prompt_extras": "",
    "max_tokens": 256,
    "smart_routing": True
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

# Load personality
def load_personality():
    pfile = CONFIG.get("personality_file", "prompts/bmo_companion.txt")
    if os.path.exists(pfile):
        with open(pfile, "r") as f:
            prompt = f.read().strip()
        print(f"[INIT] Personality: {pfile}")
    else:
        prompt = "You are BMO, a helpful robot companion. Keep responses short and fun."
        print(f"[INIT] Personality file not found, using default")
    extras = CONFIG.get("system_prompt_extras", "")
    if extras:
        prompt += "\n\n" + extras
    return prompt

SYSTEM_PROMPT = load_personality()

# Claude client
CLIENT = anthropic.Anthropic()
TEXT_MODEL = CONFIG["text_model"]
SMART_MODEL = CONFIG.get("smart_model", TEXT_MODEL)
SMART_ROUTING = CONFIG.get("smart_routing", False)

# Router prompt
ROUTER_PROMPT = """Classify this user message as SIMPLE or COMPLEX. Reply with only one word.
SIMPLE = greetings, casual chat, jokes, simple questions, short factual answers
COMPLEX = explanations, analysis, advice, multi-step reasoning, detailed questions
Message: "{message}"
Classification:"""

def choose_model(text):
    if not SMART_ROUTING or TEXT_MODEL == SMART_MODEL:
        return TEXT_MODEL
    try:
        resp = CLIENT.messages.create(
            model=TEXT_MODEL, max_tokens=4,
            messages=[{"role": "user", "content": ROUTER_PROMPT.format(message=text)}]
        )
        classification = resp.content[0].text.strip().upper()
        chosen = SMART_MODEL if "COMPLEX" in classification else TEXT_MODEL
        print(f"[ROUTER] {classification} → {chosen}")
        return chosen
    except:
        return TEXT_MODEL


# =========================================================================
# VIRTUAL BMO GUI
# =========================================================================

class VirtualBMO:
    FACE_WIDTH = 800
    FACE_HEIGHT = 480

    STATES = ["idle", "listening", "thinking", "speaking", "error", "capturing", "warmup"]

    def __init__(self, master):
        self.master = master
        master.title("Virtual BMO")
        master.resizable(False, False)
        master.configure(bg="#1a1a2e")

        # State
        self.current_state = "warmup"
        self.animations = {}
        self.frame_index = 0
        self.session_memory = []
        self.is_processing = False

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
        self.chat_text.pack(fill=tk.X)

        # Tag configs for different speakers
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
        master.bind("<Escape>", lambda e: master.quit())

        # Start animation loop
        self.update_animation()

        # Warmup sequence
        threading.Thread(target=self.warmup, daemon=True).start()

    def load_animations(self):
        for state in self.STATES:
            folder = os.path.join(FACE_DIR, state)
            self.animations[state] = []
            if os.path.exists(folder):
                files = sorted([f for f in os.listdir(folder) if f.lower().endswith('.png')])
                for f in files:
                    img = Image.open(os.path.join(folder, f)).resize(
                        (self.FACE_WIDTH, self.FACE_HEIGHT))
                    self.animations[state].append(ImageTk.PhotoImage(img))
            if not self.animations[state]:
                # Fallback: mint green screen
                blank = Image.new('RGB', (self.FACE_WIDTH, self.FACE_HEIGHT), color='#7ECDB0')
                self.animations[state].append(ImageTk.PhotoImage(blank))
        print(f"[INIT] Loaded {sum(len(v) for v in self.animations.values())} face frames")

    def update_animation(self):
        frames = self.animations.get(self.current_state, self.animations.get("idle", []))
        if frames:
            if self.current_state == "speaking":
                self.frame_index = random.randint(0, len(frames) - 1)
            else:
                self.frame_index = (self.frame_index + 1) % len(frames)
            self.face_label.config(image=frames[self.frame_index])

        speed = 80 if self.current_state == "speaking" else 500
        self.master.after(speed, self.update_animation)

    def set_state(self, state, status_msg=""):
        self.current_state = state
        self.frame_index = 0
        if status_msg:
            self.status_var.set(status_msg)

    def append_chat(self, text, tag="bmo"):
        self.chat_text.config(state=tk.NORMAL)
        self.chat_text.insert(tk.END, text + "\n", tag)
        self.chat_text.see(tk.END)
        self.chat_text.config(state=tk.DISABLED)

    def warmup(self):
        time.sleep(1.5)
        self.set_state("idle", "BMO is ready! Type something!")
        self.append_chat("* BMO boots up *", "system")
        self.append_chat("Hi hi hi! BMO is here! What should we do today?", "bmo")

    def on_send(self, event=None):
        text = self.input_var.get().strip()
        if not text or self.is_processing:
            return

        self.input_var.set("")
        self.is_processing = True
        self.send_btn.config(state=tk.DISABLED)

        self.append_chat(f"You: {text}", "you")
        self.set_state("listening", "BMO heard you!")

        threading.Thread(target=self.process_message, args=(text,), daemon=True).start()

    def process_message(self, text):
        try:
            # Thinking state
            time.sleep(0.3)
            self.set_state("thinking", "BMO is thinking...")

            # Choose model
            model = choose_model(text)
            model_label = "haiku" if "haiku" in model else "sonnet"

            # Build messages
            chat_messages = []
            for msg in self.session_memory[-10:]:
                chat_messages.append(msg)
            chat_messages.append({"role": "user", "content": text})

            max_tokens = CONFIG.get("max_tokens", 256)
            if model == SMART_MODEL and model != TEXT_MODEL:
                max_tokens = max(max_tokens, 512)

            # Call Claude
            self.set_state("thinking", f"BMO is thinking... [{model_label}]")

            response = CLIENT.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=SYSTEM_PROMPT,
                messages=chat_messages
            )

            reply = response.content[0].text

            # Check for tool actions
            action_match = re.search(r'\{.*"action".*\}', reply, re.DOTALL)
            if action_match:
                try:
                    action_data = json.loads(action_match.group(0))
                    action = action_data.get("action", "")
                    if action == "get_time":
                        import datetime
                        now = datetime.datetime.now().strftime("%I:%M %p")
                        reply = f"It is {now}! That is a very good time!"
                    elif action == "capture_image":
                        reply = "BMO would take a photo now! But BMO has no camera in virtual mode. BMO chop!"
                    elif action == "search_web":
                        query = action_data.get("value", action_data.get("query", ""))
                        reply = f"BMO would search for \"{query}\" now! But BMO is in virtual mode. Try asking BMO directly!"
                except:
                    pass

            # Speaking state
            self.set_state("speaking", "BMO is talking!")
            self.append_chat(f"BMO [{model_label}]: {reply}", "bmo")

            # Store in memory
            self.session_memory.append({"role": "user", "content": text})
            self.session_memory.append({"role": "assistant", "content": reply})

            # Brief speaking animation
            time.sleep(max(1.0, len(reply) * 0.02))

            self.set_state("idle", "BMO is ready!")

        except Exception as e:
            self.set_state("error", f"Brain freeze! {str(e)[:40]}")
            self.append_chat(f"* Error: {e} *", "system")
            time.sleep(2)
            self.set_state("idle", "BMO recovered!")
        finally:
            self.is_processing = False
            self.master.after(0, lambda: self.send_btn.config(state=tk.NORMAL))


# =========================================================================
# MAIN
# =========================================================================

if __name__ == "__main__":
    print("=== Virtual BMO ===")
    print(f"Model: {TEXT_MODEL}")
    print(f"Smart routing: {SMART_ROUTING} → {SMART_MODEL}")
    print(f"Personality: {CONFIG.get('personality_file')}")
    print()

    root = tk.Tk()
    app = VirtualBMO(root)
    root.mainloop()
