#!/usr/bin/env python3
"""
BMO Face Generator v2 — Show-Accurate Edition
Based on actual BMO face references from Adventure Time (byobmo.com)

Key corrections from v1:
- Background is MINT/SEAFOAM GREEN (#7ECDB0), not dark teal
- Features are BLACK/DARK CHARCOAL (#2D2D2D), not phosphor green
- Eyes are small round dots, not vertical ovals
- Mouth is wide smooth curves, not small arcs
- No CRT scanlines or glow effects — clean flat style
- Open mouth is filled dark green, not outlined

Screen: 800x480 (Freenove 5" touchscreen)
"""

from PIL import Image, ImageDraw, ImageFilter, ImageFont
import os
import math

# === SHOW-ACCURATE COLORS ===
WIDTH, HEIGHT = 800, 480
BG_COLOR = (126, 205, 176)      # #7ECDB0 — BMO's mint/seafoam screen
FG_COLOR = (45, 45, 45)         # #2D2D2D — Dark charcoal for features
MOUTH_FILL = (30, 100, 75)      # Dark green for open mouth interior
GAME_BG = (55, 55, 55)          # #373737 — Dark bg for game/text screens
GAME_FG = (120, 210, 185)       # Cyan-green for game/text pixel art

# Face positioning
CENTER_X = WIDTH // 2
CENTER_Y = HEIGHT // 2 - 30     # Face sits in upper portion
EYE_SPACING = 100               # Half-distance between eye centers
EYE_Y = CENTER_Y - 30           # Eye vertical position
MOUTH_Y = CENTER_Y + 50         # Mouth vertical position

OUTPUT_DIR = "faces"

# === DRAWING HELPERS ===

def new_frame():
    return Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)

def new_game_frame():
    """Dark screen for game/text displays."""
    return Image.new("RGB", (WIDTH, HEIGHT), GAME_BG)

def dot(draw, cx, cy, radius=14, color=FG_COLOR):
    """Small filled circle — BMO's default eye."""
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=color)

def eyes_default(draw, radius=14):
    """Two small round dot eyes."""
    dot(draw, CENTER_X - EYE_SPACING, EYE_Y, radius)
    dot(draw, CENTER_X + EYE_SPACING, EYE_Y, radius)

def eyes_happy(draw):
    """Happy closed eyes — downward arcs (like bmo1 reference: content/happy)."""
    for ex in [CENTER_X - EYE_SPACING, CENTER_X + EYE_SPACING]:
        draw.arc([ex - 18, EYE_Y - 12, ex + 18, EYE_Y + 12], 200, 340, fill=FG_COLOR, width=5)

def eyes_closed(draw):
    """Fully closed eyes — horizontal lines."""
    for ex in [CENTER_X - EYE_SPACING, CENTER_X + EYE_SPACING]:
        draw.line([(ex - 16, EYE_Y), (ex + 16, EYE_Y)], fill=FG_COLOR, width=4)

def eyes_half(draw):
    """Half-closed eyes (blinking) — small horizontal ovals."""
    for ex in [CENTER_X - EYE_SPACING, CENTER_X + EYE_SPACING]:
        draw.ellipse([ex - 14, EYE_Y - 5, ex + 14, EYE_Y + 5], fill=FG_COLOR)

def eyes_wide(draw, radius=20):
    """Wide surprised eyes — bigger dots."""
    dot(draw, CENTER_X - EYE_SPACING, EYE_Y, radius)
    dot(draw, CENTER_X + EYE_SPACING, EYE_Y, radius)

def eyes_looking(draw, direction="right"):
    """Eyes looking to one side — offset dots."""
    offset = 10 if direction == "right" else -10
    dot(draw, CENTER_X - EYE_SPACING + offset, EYE_Y)
    dot(draw, CENTER_X + EYE_SPACING + offset, EYE_Y)

def eyes_angry(draw):
    """Angry eyes — dots with eyelid lines (like bmo4 reference)."""
    for ex in [CENTER_X - EYE_SPACING, CENTER_X + EYE_SPACING]:
        dot(draw, ex, EYE_Y, 12)
        # Heavy eyelid lines above and below
        draw.line([(ex - 28, EYE_Y - 8), (ex + 28, EYE_Y - 8)], fill=FG_COLOR, width=5)
        draw.line([(ex - 28, EYE_Y + 8), (ex + 28, EYE_Y + 8)], fill=FG_COLOR, width=5)

def eyes_x(draw):
    """X eyes — error/dizzy."""
    size = 14
    for ex in [CENTER_X - EYE_SPACING, CENTER_X + EYE_SPACING]:
        draw.line([(ex - size, EYE_Y - size), (ex + size, EYE_Y + size)], fill=FG_COLOR, width=5)
        draw.line([(ex + size, EYE_Y - size), (ex - size, EYE_Y + size)], fill=FG_COLOR, width=5)

def eyes_small_o(draw):
    """Small 'o' mouth as eyes — surprised (like bmo7: small circle mouth)."""
    for ex in [CENTER_X - EYE_SPACING, CENTER_X + EYE_SPACING]:
        dot(draw, ex, EYE_Y, 16)

def mouth_smile(draw, width=120):
    """Wide gentle smile curve (like bmo9 reference)."""
    draw.arc(
        [CENTER_X - width, MOUTH_Y - 40, CENTER_X + width, MOUTH_Y + 40],
        10, 170, fill=FG_COLOR, width=4
    )

def mouth_big_smile(draw, width=140):
    """Bigger wider smile."""
    draw.arc(
        [CENTER_X - width, MOUTH_Y - 50, CENTER_X + width, MOUTH_Y + 50],
        10, 170, fill=FG_COLOR, width=5
    )

def mouth_neutral(draw, width=100):
    """Flat neutral line (like bmo3 reference)."""
    draw.line(
        [(CENTER_X - width, MOUTH_Y), (CENTER_X + width, MOUTH_Y)],
        fill=FG_COLOR, width=5
    )

def mouth_slanted(draw):
    """Slightly slanted neutral line (like bmo6 reference)."""
    draw.line(
        [(CENTER_X - 80, MOUTH_Y + 5), (CENTER_X + 80, MOUTH_Y - 10)],
        fill=FG_COLOR, width=5
    )

def mouth_open_talk(draw, width=90, height=30):
    """Open talking mouth — filled dark green bean shape (like bmo2 reference)."""
    draw.ellipse(
        [CENTER_X - width, MOUTH_Y - height, CENTER_X + width, MOUTH_Y + height],
        fill=MOUTH_FILL, outline=FG_COLOR, width=4
    )

def mouth_small_open(draw):
    """Small open mouth — little circle (like bmo7 reference)."""
    draw.ellipse(
        [CENTER_X - 12, MOUTH_Y - 10, CENTER_X + 12, MOUTH_Y + 10],
        fill=None, outline=FG_COLOR, width=4
    )

def mouth_frown(draw, width=100):
    """Frown — downward curve (like bmo4 reference)."""
    draw.arc(
        [CENTER_X - width, MOUTH_Y - 30, CENTER_X + width, MOUTH_Y + 50],
        200, 340, fill=FG_COLOR, width=4
    )

def mouth_zigzag(draw):
    """Zigzag distress mouth."""
    points = []
    for i in range(8):
        x = CENTER_X - 50 + i * 14
        yoff = -10 if i % 2 == 0 else 10
        points.append((x, MOUTH_Y + yoff))
    for i in range(len(points) - 1):
        draw.line([points[i], points[i + 1]], fill=FG_COLOR, width=4)

def mouth_dots(draw):
    """Three dots '...' for thinking."""
    for i in range(3):
        x = CENTER_X - 20 + i * 20
        dot(draw, x, MOUTH_Y, 5)

def loading_bar(draw, progress):
    """Loading/volume bar (like bmo8 reference — signal bars)."""
    bar_count = 5
    bar_width = 50
    bar_spacing = 15
    total_width = bar_count * (bar_width + bar_spacing) - bar_spacing
    start_x = CENTER_X - total_width // 2
    bar_y = HEIGHT - 80

    filled = int(bar_count * progress)
    for i in range(bar_count):
        x = start_x + i * (bar_width + bar_spacing)
        if i < filled:
            draw.rectangle([x, bar_y, x + bar_width, bar_y + 30], fill=FG_COLOR)
        else:
            draw.rectangle([x, bar_y, x + bar_width, bar_y + 30], outline=FG_COLOR, width=3)

def signal_arcs(draw, count=4):
    """Signal/sound arcs (like bmo8 reference)."""
    cx, cy = CENTER_X - 40, CENTER_Y + 20
    for i in range(count):
        r = 30 + i * 50
        draw.arc([cx - r, cy - r, cx + r, cy + r], -50, 50, fill=FG_COLOR, width=8 + i * 2)

def save_frame(img, state, frame_num):
    state_dir = os.path.join(OUTPUT_DIR, state)
    os.makedirs(state_dir, exist_ok=True)
    path = os.path.join(state_dir, f"frame_{frame_num:02d}.png")
    img.save(path)
    print(f"  Saved: {path}")


# === STATE GENERATORS ===

def generate_idle():
    """Idle: Default happy face with blink cycle."""
    print("Generating: idle")

    # Frames 0-2: Default face — dot eyes, gentle smile
    for i in range(3):
        img = new_frame()
        draw = ImageDraw.Draw(img)
        eyes_default(draw)
        mouth_smile(draw)
        save_frame(img, "idle", i)

    # Frame 3: Half-blink
    img = new_frame()
    draw = ImageDraw.Draw(img)
    eyes_half(draw)
    mouth_smile(draw)
    save_frame(img, "idle", 3)

    # Frame 4: Full blink
    img = new_frame()
    draw = ImageDraw.Draw(img)
    eyes_closed(draw)
    mouth_smile(draw)
    save_frame(img, "idle", 4)

    # Frame 5: Half-blink recovery
    img = new_frame()
    draw = ImageDraw.Draw(img)
    eyes_half(draw)
    mouth_smile(draw)
    save_frame(img, "idle", 5)


def generate_listening():
    """Listening: Wide attentive eyes, small open mouth."""
    print("Generating: listening")

    # Frame 0: Wide eyes, small open mouth
    img = new_frame()
    draw = ImageDraw.Draw(img)
    eyes_wide(draw, 18)
    mouth_small_open(draw)
    save_frame(img, "listening", 0)

    # Frame 1: Slightly wider
    img = new_frame()
    draw = ImageDraw.Draw(img)
    eyes_wide(draw, 20)
    mouth_small_open(draw)
    save_frame(img, "listening", 1)

    # Frame 2: Back
    img = new_frame()
    draw = ImageDraw.Draw(img)
    eyes_wide(draw, 18)
    mouth_neutral(draw, 60)
    save_frame(img, "listening", 2)

    # Frame 3: Attentive
    img = new_frame()
    draw = ImageDraw.Draw(img)
    eyes_wide(draw, 19)
    mouth_small_open(draw)
    save_frame(img, "listening", 3)


def generate_thinking():
    """Thinking: Eyes looking around, dots appearing."""
    print("Generating: thinking")

    # Frame 0: Looking right, neutral
    img = new_frame()
    draw = ImageDraw.Draw(img)
    eyes_looking(draw, "right")
    mouth_slanted(draw)
    save_frame(img, "thinking", 0)

    # Frame 1: Looking right, one dot
    img = new_frame()
    draw = ImageDraw.Draw(img)
    eyes_looking(draw, "right")
    dot(draw, CENTER_X - 20, MOUTH_Y, 5)
    save_frame(img, "thinking", 1)

    # Frame 2: Looking right, two dots
    img = new_frame()
    draw = ImageDraw.Draw(img)
    eyes_looking(draw, "right")
    dot(draw, CENTER_X - 20, MOUTH_Y, 5)
    dot(draw, CENTER_X, MOUTH_Y, 5)
    save_frame(img, "thinking", 2)

    # Frame 3: Looking left, three dots
    img = new_frame()
    draw = ImageDraw.Draw(img)
    eyes_looking(draw, "left")
    mouth_dots(draw)
    save_frame(img, "thinking", 3)

    # Frame 4: Looking left, neutral
    img = new_frame()
    draw = ImageDraw.Draw(img)
    eyes_looking(draw, "left")
    mouth_slanted(draw)
    save_frame(img, "thinking", 4)

    # Frame 5: Looking right (loop)
    img = new_frame()
    draw = ImageDraw.Draw(img)
    eyes_looking(draw, "right")
    mouth_neutral(draw, 70)
    save_frame(img, "thinking", 5)


def generate_speaking():
    """Speaking: Mouth cycling open/closed. Mix of expressions."""
    print("Generating: speaking")

    # Frame 0: Happy eyes, smile
    img = new_frame()
    draw = ImageDraw.Draw(img)
    eyes_happy(draw)
    mouth_smile(draw)
    save_frame(img, "speaking", 0)

    # Frame 1: Default eyes, small open
    img = new_frame()
    draw = ImageDraw.Draw(img)
    eyes_default(draw)
    mouth_small_open(draw)
    save_frame(img, "speaking", 1)

    # Frame 2: Default eyes, big open talk (filled green mouth like bmo2)
    img = new_frame()
    draw = ImageDraw.Draw(img)
    eyes_default(draw)
    mouth_open_talk(draw, 80, 25)
    save_frame(img, "speaking", 2)

    # Frame 3: Default eyes, bigger open
    img = new_frame()
    draw = ImageDraw.Draw(img)
    eyes_default(draw)
    mouth_open_talk(draw, 90, 30)
    save_frame(img, "speaking", 3)

    # Frame 4: Happy eyes, small open
    img = new_frame()
    draw = ImageDraw.Draw(img)
    eyes_happy(draw)
    mouth_small_open(draw)
    save_frame(img, "speaking", 4)

    # Frame 5: Default eyes, big smile
    img = new_frame()
    draw = ImageDraw.Draw(img)
    eyes_default(draw)
    mouth_big_smile(draw)
    save_frame(img, "speaking", 5)


def generate_error():
    """Error: X eyes, distressed mouth, angry face."""
    print("Generating: error")

    # Frame 0: X eyes, zigzag mouth
    img = new_frame()
    draw = ImageDraw.Draw(img)
    eyes_x(draw)
    mouth_zigzag(draw)
    save_frame(img, "error", 0)

    # Frame 1: Angry eyelids, frown (like bmo4)
    img = new_frame()
    draw = ImageDraw.Draw(img)
    eyes_angry(draw)
    mouth_frown(draw)
    save_frame(img, "error", 1)

    # Frame 2: X eyes again
    img = new_frame()
    draw = ImageDraw.Draw(img)
    eyes_x(draw)
    mouth_zigzag(draw)
    save_frame(img, "error", 2)


def generate_capturing():
    """Capturing: Camera viewfinder with crosshairs and REC."""
    print("Generating: capturing")

    for i in range(3):
        img = new_frame()
        draw = ImageDraw.Draw(img)

        # Crosshairs
        draw.line([(CENTER_X, CENTER_Y - 50), (CENTER_X, CENTER_Y - 15)], fill=FG_COLOR, width=2)
        draw.line([(CENTER_X, CENTER_Y + 15), (CENTER_X, CENTER_Y + 50)], fill=FG_COLOR, width=2)
        draw.line([(CENTER_X - 50, CENTER_Y), (CENTER_X - 15, CENTER_Y)], fill=FG_COLOR, width=2)
        draw.line([(CENTER_X + 15, CENTER_Y), (CENTER_X + 50, CENTER_Y)], fill=FG_COLOR, width=2)

        # Corner brackets
        bk = 35
        corners = [
            (CENTER_X - 130, CENTER_Y - 85),
            (CENTER_X + 130, CENTER_Y - 85),
            (CENTER_X - 130, CENTER_Y + 85),
            (CENTER_X + 130, CENTER_Y + 85),
        ]
        for ci, (cx, cy) in enumerate(corners):
            if ci == 0:
                draw.line([(cx, cy), (cx + bk, cy)], fill=FG_COLOR, width=3)
                draw.line([(cx, cy), (cx, cy + bk)], fill=FG_COLOR, width=3)
            elif ci == 1:
                draw.line([(cx, cy), (cx - bk, cy)], fill=FG_COLOR, width=3)
                draw.line([(cx, cy), (cx, cy + bk)], fill=FG_COLOR, width=3)
            elif ci == 2:
                draw.line([(cx, cy), (cx + bk, cy)], fill=FG_COLOR, width=3)
                draw.line([(cx, cy), (cx, cy - bk)], fill=FG_COLOR, width=3)
            elif ci == 3:
                draw.line([(cx, cy), (cx - bk, cy)], fill=FG_COLOR, width=3)
                draw.line([(cx, cy), (cx, cy - bk)], fill=FG_COLOR, width=3)

        # Blinking REC dot
        if i % 2 == 0:
            dot(draw, 80, 50, 10, color=(200, 40, 40))

        save_frame(img, "capturing", i)


def generate_warmup():
    """Warmup: Boot sequence — signal arcs + loading bars, then face appears."""
    print("Generating: warmup")

    # Frames 0-3: Signal/sound arcs with loading bars (like bmo8)
    for i in range(4):
        img = new_frame()
        draw = ImageDraw.Draw(img)
        arcs = min(i + 1, 4)
        signal_arcs(draw, arcs)
        loading_bar(draw, (i + 1) / 5)
        save_frame(img, "warmup", i)

    # Frame 4: Full bars, starting to show face
    img = new_frame()
    draw = ImageDraw.Draw(img)
    loading_bar(draw, 1.0)
    eyes_default(draw, 8)  # tiny eyes appearing
    save_frame(img, "warmup", 4)

    # Frame 5: Face growing
    img = new_frame()
    draw = ImageDraw.Draw(img)
    eyes_default(draw, 12)
    mouth_neutral(draw, 50)
    save_frame(img, "warmup", 5)

    # Frame 6: Full face, big smile — BMO is awake!
    img = new_frame()
    draw = ImageDraw.Draw(img)
    eyes_wide(draw, 18)
    mouth_big_smile(draw)
    save_frame(img, "warmup", 6)


# === MAIN ===

if __name__ == "__main__":
    print("=== BMO Face Generator v2 (Show-Accurate) ===")
    print(f"Resolution: {WIDTH}x{HEIGHT}")
    print(f"Background: mint/seafoam #{BG_COLOR[0]:02X}{BG_COLOR[1]:02X}{BG_COLOR[2]:02X}")
    print(f"Features: dark charcoal #{FG_COLOR[0]:02X}{FG_COLOR[1]:02X}{FG_COLOR[2]:02X}")
    print()

    generate_idle()
    generate_listening()
    generate_thinking()
    generate_speaking()
    generate_error()
    generate_capturing()
    generate_warmup()

    print()
    print("Done! All face frames generated.")
    total = 0
    for state in ["idle", "listening", "thinking", "speaking", "error", "capturing", "warmup"]:
        state_dir = os.path.join(OUTPUT_DIR, state)
        if os.path.exists(state_dir):
            count = len([f for f in os.listdir(state_dir) if f.endswith(".png")])
            total += count
            print(f"  {state}: {count} frames")
    print(f"  TOTAL: {total} frames")
