#!/usr/bin/env python3
"""
BMO Face Generator v3 — Expanded Expressions Edition
More frames per state for smoother animation + new expression states.

Screen: 800x480 | Style: Show-accurate (mint green + black features)
"""

from PIL import Image, ImageDraw
import os
import math
import random

# === SHOW-ACCURATE COLORS ===
WIDTH, HEIGHT = 800, 480
BG = (126, 205, 176)           # Mint/seafoam screen
FG = (45, 45, 45)              # Dark charcoal features
MOUTH_FILL = (30, 100, 75)    # Dark green open mouth
BLUSH = (200, 140, 140)       # Subtle blush marks
HEART = (200, 60, 80)         # Heart eyes color

# Face geometry
CX, CY = WIDTH // 2, HEIGHT // 2 - 30
EYE_SP = 100                   # Half-distance between eyes
EYE_Y = CY - 30
MOUTH_Y = CY + 50

OUTPUT = "faces"

# === PRIMITIVES ===

def frame():
    return Image.new("RGB", (WIDTH, HEIGHT), BG)

def dot(d, x, y, r=14, c=FG):
    d.ellipse([x-r, y-r, x+r, y+r], fill=c)

def eyes(d, r=14):
    dot(d, CX-EYE_SP, EYE_Y, r)
    dot(d, CX+EYE_SP, EYE_Y, r)

def eyes_happy(d):
    for ex in [CX-EYE_SP, CX+EYE_SP]:
        d.arc([ex-20, EYE_Y-14, ex+20, EYE_Y+14], 200, 340, fill=FG, width=5)

def eyes_closed(d):
    for ex in [CX-EYE_SP, CX+EYE_SP]:
        d.line([(ex-16, EYE_Y), (ex+16, EYE_Y)], fill=FG, width=4)

def eyes_half(d):
    for ex in [CX-EYE_SP, CX+EYE_SP]:
        d.ellipse([ex-14, EYE_Y-5, ex+14, EYE_Y+5], fill=FG)

def eyes_wide(d, r=20):
    dot(d, CX-EYE_SP, EYE_Y, r)
    dot(d, CX+EYE_SP, EYE_Y, r)

def eyes_look(d, dir="right"):
    off = 10 if dir == "right" else -10
    dot(d, CX-EYE_SP+off, EYE_Y)
    dot(d, CX+EYE_SP+off, EYE_Y)

def eyes_look_up(d):
    dot(d, CX-EYE_SP, EYE_Y-8)
    dot(d, CX+EYE_SP, EYE_Y-8)

def eyes_angry(d):
    for ex in [CX-EYE_SP, CX+EYE_SP]:
        dot(d, ex, EYE_Y, 12)
        d.line([(ex-28, EYE_Y-8), (ex+28, EYE_Y-8)], fill=FG, width=5)
        d.line([(ex-28, EYE_Y+8), (ex+28, EYE_Y+8)], fill=FG, width=5)

def eyes_x(d):
    sz = 14
    for ex in [CX-EYE_SP, CX+EYE_SP]:
        d.line([(ex-sz, EYE_Y-sz), (ex+sz, EYE_Y+sz)], fill=FG, width=5)
        d.line([(ex+sz, EYE_Y-sz), (ex-sz, EYE_Y+sz)], fill=FG, width=5)

def eyes_sad(d):
    # Droopy oval eyes
    for ex in [CX-EYE_SP, CX+EYE_SP]:
        dot(d, ex, EYE_Y+4, 12)
    # Worried brows
    d.line([(CX-EYE_SP-18, EYE_Y-22), (CX-EYE_SP+15, EYE_Y-28)], fill=FG, width=4)
    d.line([(CX+EYE_SP+18, EYE_Y-22), (CX+EYE_SP-15, EYE_Y-28)], fill=FG, width=4)

def eyes_heart(d):
    for ex in [CX-EYE_SP, CX+EYE_SP]:
        # Simple heart shape using two circles + triangle
        r = 8
        dot(d, ex-6, EYE_Y-4, r, HEART)
        dot(d, ex+6, EYE_Y-4, r, HEART)
        d.polygon([(ex-14, EYE_Y), (ex+14, EYE_Y), (ex, EYE_Y+16)], fill=HEART)

def eyes_wink(d):
    # Left eye normal, right eye winking
    dot(d, CX-EYE_SP, EYE_Y)
    d.arc([CX+EYE_SP-16, EYE_Y-4, CX+EYE_SP+16, EYE_Y+12], 200, 340, fill=FG, width=4)

def eyes_sparkle(d):
    # Wide eyes with tiny highlight dots (excited)
    for ex in [CX-EYE_SP, CX+EYE_SP]:
        dot(d, ex, EYE_Y, 18)
        dot(d, ex+5, EYE_Y-5, 4, BG)  # Sparkle highlight

def mouth_smile(d, w=120):
    d.arc([CX-w, MOUTH_Y-40, CX+w, MOUTH_Y+40], 10, 170, fill=FG, width=4)

def mouth_big_smile(d, w=140):
    d.arc([CX-w, MOUTH_Y-50, CX+w, MOUTH_Y+50], 10, 170, fill=FG, width=5)

def mouth_huge_grin(d):
    # Open D-shape smile
    d.pieslice([CX-100, MOUTH_Y-20, CX+100, MOUTH_Y+40], 0, 180, fill=MOUTH_FILL, outline=FG, width=4)

def mouth_flat(d, w=100):
    d.line([(CX-w, MOUTH_Y), (CX+w, MOUTH_Y)], fill=FG, width=5)

def mouth_slant(d):
    d.line([(CX-80, MOUTH_Y+5), (CX+80, MOUTH_Y-10)], fill=FG, width=5)

def mouth_open(d, w=90, h=30):
    d.ellipse([CX-w, MOUTH_Y-h, CX+w, MOUTH_Y+h], fill=MOUTH_FILL, outline=FG, width=4)

def mouth_small_open(d):
    d.ellipse([CX-12, MOUTH_Y-10, CX+12, MOUTH_Y+10], outline=FG, width=4)

def mouth_medium_open(d):
    d.ellipse([CX-40, MOUTH_Y-15, CX+40, MOUTH_Y+15], fill=MOUTH_FILL, outline=FG, width=4)

def mouth_frown(d, w=100):
    d.arc([CX-w, MOUTH_Y-30, CX+w, MOUTH_Y+50], 200, 340, fill=FG, width=4)

def mouth_zigzag(d):
    pts = [(CX-50+i*14, MOUTH_Y+(-10 if i%2==0 else 10)) for i in range(8)]
    for i in range(len(pts)-1):
        d.line([pts[i], pts[i+1]], fill=FG, width=4)

def mouth_dots(d):
    for i in range(3):
        dot(d, CX-20+i*20, MOUTH_Y, 5)

def mouth_wavy(d):
    # Nervous wavy mouth
    pts = [(CX-60+i*20, MOUTH_Y+int(6*math.sin(i*1.2))) for i in range(7)]
    for i in range(len(pts)-1):
        d.line([pts[i], pts[i+1]], fill=FG, width=4)

def mouth_tiny_smile(d):
    d.arc([CX-40, MOUTH_Y-15, CX+40, MOUTH_Y+15], 10, 170, fill=FG, width=3)

def blush_marks(d):
    # Small pink ovals on cheeks
    d.ellipse([CX-EYE_SP-30, EYE_Y+20, CX-EYE_SP+5, EYE_Y+35], fill=BLUSH)
    d.ellipse([CX+EYE_SP-5, EYE_Y+20, CX+EYE_SP+30, EYE_Y+35], fill=BLUSH)

def tear_drop(d, side="left"):
    ex = CX-EYE_SP if side == "left" else CX+EYE_SP
    d.ellipse([ex-4, EYE_Y+20, ex+4, EYE_Y+32], fill=FG)

def zzz(d):
    # Floating Z's
    for i, (dx, dy, sz) in enumerate([(40, -50, 10), (60, -70, 14), (85, -95, 18)]):
        x, y = CX+EYE_SP+dx, EYE_Y+dy
        d.line([(x, y), (x+sz, y)], fill=FG, width=3)
        d.line([(x+sz, y), (x, y+sz)], fill=FG, width=3)
        d.line([(x, y+sz), (x+sz, y+sz)], fill=FG, width=3)

def save(img, state, n):
    d = os.path.join(OUTPUT, state)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"frame_{n:02d}.png")
    img.save(p)


# === STATES ===

def gen_idle():
    """Idle: Relaxed blink cycle with subtle expression shifts."""
    print("idle", end=" ")
    n = 0
    # Frames 0-3: Default smile, eyes open
    for _ in range(4):
        f = frame(); d = ImageDraw.Draw(f)
        eyes(d); mouth_smile(d)
        save(f, "idle", n); n += 1
    # Frame 4: Slight squint (pre-blink)
    f = frame(); d = ImageDraw.Draw(f)
    eyes_half(d); mouth_smile(d)
    save(f, "idle", n); n += 1
    # Frame 5: Closed (blink)
    f = frame(); d = ImageDraw.Draw(f)
    eyes_closed(d); mouth_smile(d)
    save(f, "idle", n); n += 1
    # Frame 6: Half open (recovery)
    f = frame(); d = ImageDraw.Draw(f)
    eyes_half(d); mouth_smile(d)
    save(f, "idle", n); n += 1
    # Frame 7-8: Back to default
    for _ in range(2):
        f = frame(); d = ImageDraw.Draw(f)
        eyes(d); mouth_smile(d)
        save(f, "idle", n); n += 1
    # Frame 9: Happy eyes variant (occasional)
    f = frame(); d = ImageDraw.Draw(f)
    eyes_happy(d); mouth_smile(d)
    save(f, "idle", n); n += 1
    # Frame 10-11: Back to default
    for _ in range(2):
        f = frame(); d = ImageDraw.Draw(f)
        eyes(d); mouth_smile(d)
        save(f, "idle", n); n += 1
    print(f"({n} frames)")

def gen_listening():
    """Listening: Wide attentive eyes, subtle pulsing."""
    print("listening", end=" ")
    n = 0
    for r in [17, 18, 20, 19, 18, 20, 19, 17]:
        f = frame(); d = ImageDraw.Draw(f)
        eyes_wide(d, r); mouth_small_open(d)
        save(f, "listening", n); n += 1
    print(f"({n} frames)")

def gen_thinking():
    """Thinking: Eyes shifting, dots appearing, look up."""
    print("thinking", end=" ")
    n = 0
    # Looking right
    f = frame(); d = ImageDraw.Draw(f); eyes_look(d, "right"); mouth_slant(d); save(f, "thinking", n); n += 1
    f = frame(); d = ImageDraw.Draw(f); eyes_look(d, "right"); dot(d, CX-20, MOUTH_Y, 5); save(f, "thinking", n); n += 1
    f = frame(); d = ImageDraw.Draw(f); eyes_look(d, "right"); dot(d, CX-20, MOUTH_Y, 5); dot(d, CX, MOUTH_Y, 5); save(f, "thinking", n); n += 1
    # Looking left + three dots
    f = frame(); d = ImageDraw.Draw(f); eyes_look(d, "left"); mouth_dots(d); save(f, "thinking", n); n += 1
    f = frame(); d = ImageDraw.Draw(f); eyes_look(d, "left"); mouth_slant(d); save(f, "thinking", n); n += 1
    # Looking up
    f = frame(); d = ImageDraw.Draw(f); eyes_look_up(d); mouth_flat(d, 60); save(f, "thinking", n); n += 1
    f = frame(); d = ImageDraw.Draw(f); eyes_look_up(d); dot(d, CX-20, MOUTH_Y, 5); save(f, "thinking", n); n += 1
    f = frame(); d = ImageDraw.Draw(f); eyes_look_up(d); dot(d, CX-20, MOUTH_Y, 5); dot(d, CX, MOUTH_Y, 5); save(f, "thinking", n); n += 1
    # Back to right
    f = frame(); d = ImageDraw.Draw(f); eyes_look(d, "right"); mouth_dots(d); save(f, "thinking", n); n += 1
    f = frame(); d = ImageDraw.Draw(f); eyes_look(d, "right"); mouth_flat(d, 70); save(f, "thinking", n); n += 1
    print(f"({n} frames)")

def gen_speaking():
    """Speaking: Rapid mouth cycling with eye expression changes."""
    print("speaking", end=" ")
    n = 0
    # Mouth shapes cycle: closed → small → medium → big → medium → small
    sequence = [
        (eyes_happy, mouth_smile, None),
        (eyes, mouth_small_open, None),
        (eyes, mouth_medium_open, None),
        (eyes, mouth_open, None),
        (eyes_happy, mouth_huge_grin, None),
        (eyes, mouth_medium_open, None),
        (eyes, mouth_small_open, None),
        (eyes_happy, mouth_big_smile, None),
        (eyes, mouth_open, None),
        (eyes_happy, mouth_smile, None),
        (eyes, mouth_medium_open, None),
        (eyes, mouth_small_open, None),
    ]
    for eye_fn, mouth_fn, extra in sequence:
        f = frame(); d = ImageDraw.Draw(f)
        eye_fn(d); mouth_fn(d)
        if extra: extra(d)
        save(f, "speaking", n); n += 1
    print(f"({n} frames)")

def gen_error():
    """Error: X eyes, zigzag, angry, distressed cycling."""
    print("error", end=" ")
    n = 0
    f = frame(); d = ImageDraw.Draw(f); eyes_x(d); mouth_zigzag(d); save(f, "error", n); n += 1
    f = frame(); d = ImageDraw.Draw(f); eyes_angry(d); mouth_frown(d); save(f, "error", n); n += 1
    f = frame(); d = ImageDraw.Draw(f); eyes_x(d); mouth_zigzag(d); save(f, "error", n); n += 1
    f = frame(); d = ImageDraw.Draw(f); eyes_sad(d); mouth_wavy(d); save(f, "error", n); n += 1
    f = frame(); d = ImageDraw.Draw(f); eyes_x(d); mouth_frown(d); save(f, "error", n); n += 1
    print(f"({n} frames)")

def gen_capturing():
    """Capturing: Camera viewfinder with crosshairs."""
    print("capturing", end=" ")
    n = 0
    for i in range(4):
        f = frame(); d = ImageDraw.Draw(f)
        # Crosshairs
        d.line([(CX, CY-50), (CX, CY-15)], fill=FG, width=2)
        d.line([(CX, CY+15), (CX, CY+50)], fill=FG, width=2)
        d.line([(CX-50, CY), (CX-15, CY)], fill=FG, width=2)
        d.line([(CX+15, CY), (CX+50, CY)], fill=FG, width=2)
        # Corners
        bk = 35
        for ci, (cx, cy) in enumerate([(CX-130,CY-85),(CX+130,CY-85),(CX-130,CY+85),(CX+130,CY+85)]):
            h = bk if ci in [0,2] else -bk
            v = bk if ci in [0,1] else -bk
            d.line([(cx, cy), (cx+h, cy)], fill=FG, width=3)
            d.line([(cx, cy), (cx, cy+v)], fill=FG, width=3)
        # Blinking REC
        if i % 2 == 0:
            dot(d, 80, 50, 10, (200, 40, 40))
        save(f, "capturing", n); n += 1
    print(f"({n} frames)")

def gen_warmup():
    """Warmup: Boot sequence with loading bars and face appearing."""
    print("warmup", end=" ")
    n = 0
    # Empty screen
    f = frame(); save(f, "warmup", n); n += 1
    # Loading bars appearing
    for bars in range(1, 6):
        f = frame(); d = ImageDraw.Draw(f)
        bw, sp = 50, 15
        total = 5 * (bw + sp) - sp
        sx = CX - total // 2
        by = HEIGHT - 80
        for i in range(5):
            x = sx + i * (bw + sp)
            if i < bars:
                d.rectangle([x, by, x+bw, by+30], fill=FG)
            else:
                d.rectangle([x, by, x+bw, by+30], outline=FG, width=3)
        save(f, "warmup", n); n += 1
    # Face fading in
    for sz in [6, 10, 14]:
        f = frame(); d = ImageDraw.Draw(f)
        eyes(d, sz)
        save(f, "warmup", n); n += 1
    # Full face — excited!
    f = frame(); d = ImageDraw.Draw(f)
    eyes_wide(d, 20); mouth_big_smile(d)
    save(f, "warmup", n); n += 1
    f = frame(); d = ImageDraw.Draw(f)
    eyes_sparkle(d); mouth_huge_grin(d)
    save(f, "warmup", n); n += 1
    print(f"({n} frames)")

# --- NEW EXPRESSION STATES ---

def gen_happy():
    """Happy: Excited BMO with sparkle eyes and blush."""
    print("happy", end=" ")
    n = 0
    f = frame(); d = ImageDraw.Draw(f); eyes_happy(d); mouth_big_smile(d); save(f, "happy", n); n += 1
    f = frame(); d = ImageDraw.Draw(f); eyes_sparkle(d); mouth_huge_grin(d); save(f, "happy", n); n += 1
    f = frame(); d = ImageDraw.Draw(f); eyes_happy(d); mouth_huge_grin(d); blush_marks(d); save(f, "happy", n); n += 1
    f = frame(); d = ImageDraw.Draw(f); eyes_sparkle(d); mouth_big_smile(d); blush_marks(d); save(f, "happy", n); n += 1
    f = frame(); d = ImageDraw.Draw(f); eyes_happy(d); mouth_big_smile(d); save(f, "happy", n); n += 1
    f = frame(); d = ImageDraw.Draw(f); eyes_wide(d, 18); mouth_huge_grin(d); save(f, "happy", n); n += 1
    print(f"({n} frames)")

def gen_sad():
    """Sad: Droopy eyes, frown, tear drop."""
    print("sad", end=" ")
    n = 0
    f = frame(); d = ImageDraw.Draw(f); eyes_sad(d); mouth_frown(d); save(f, "sad", n); n += 1
    f = frame(); d = ImageDraw.Draw(f); eyes_sad(d); mouth_frown(d); tear_drop(d, "left"); save(f, "sad", n); n += 1
    f = frame(); d = ImageDraw.Draw(f); eyes_sad(d); mouth_wavy(d); tear_drop(d, "right"); save(f, "sad", n); n += 1
    f = frame(); d = ImageDraw.Draw(f); eyes_sad(d); mouth_frown(d); save(f, "sad", n); n += 1
    f = frame(); d = ImageDraw.Draw(f); eyes_sad(d); mouth_frown(d, 80); tear_drop(d, "left"); tear_drop(d, "right"); save(f, "sad", n); n += 1
    print(f"({n} frames)")

def gen_love():
    """Love: Heart eyes, big smile, blush."""
    print("love", end=" ")
    n = 0
    f = frame(); d = ImageDraw.Draw(f); eyes_heart(d); mouth_big_smile(d); save(f, "love", n); n += 1
    f = frame(); d = ImageDraw.Draw(f); eyes_heart(d); mouth_huge_grin(d); blush_marks(d); save(f, "love", n); n += 1
    f = frame(); d = ImageDraw.Draw(f); eyes_heart(d); mouth_big_smile(d); blush_marks(d); save(f, "love", n); n += 1
    f = frame(); d = ImageDraw.Draw(f); eyes_heart(d); mouth_huge_grin(d); save(f, "love", n); n += 1
    print(f"({n} frames)")

def gen_surprised():
    """Surprised: Wide eyes, O mouth."""
    print("surprised", end=" ")
    n = 0
    f = frame(); d = ImageDraw.Draw(f); eyes_wide(d, 22); mouth_small_open(d); save(f, "surprised", n); n += 1
    f = frame(); d = ImageDraw.Draw(f); eyes_wide(d, 25); mouth_medium_open(d); save(f, "surprised", n); n += 1
    f = frame(); d = ImageDraw.Draw(f); eyes_wide(d, 22); mouth_open(d, 50, 20); save(f, "surprised", n); n += 1
    f = frame(); d = ImageDraw.Draw(f); eyes_wide(d, 25); mouth_medium_open(d); save(f, "surprised", n); n += 1
    print(f"({n} frames)")

def gen_sleeping():
    """Sleeping: Closed eyes, Z's floating."""
    print("sleeping", end=" ")
    n = 0
    f = frame(); d = ImageDraw.Draw(f); eyes_closed(d); mouth_tiny_smile(d); save(f, "sleeping", n); n += 1
    f = frame(); d = ImageDraw.Draw(f); eyes_closed(d); mouth_tiny_smile(d); zzz(d); save(f, "sleeping", n); n += 1
    f = frame(); d = ImageDraw.Draw(f); eyes_closed(d); save(f, "sleeping", n); n += 1
    f = frame(); d = ImageDraw.Draw(f); eyes_closed(d); mouth_tiny_smile(d); save(f, "sleeping", n); n += 1
    f = frame(); d = ImageDraw.Draw(f); eyes_closed(d); zzz(d); save(f, "sleeping", n); n += 1
    print(f"({n} frames)")

def gen_winking():
    """Winking: Playful wink with smile."""
    print("winking", end=" ")
    n = 0
    f = frame(); d = ImageDraw.Draw(f); eyes(d); mouth_smile(d); save(f, "winking", n); n += 1
    f = frame(); d = ImageDraw.Draw(f); eyes_wink(d); mouth_big_smile(d); save(f, "winking", n); n += 1
    f = frame(); d = ImageDraw.Draw(f); eyes_wink(d); mouth_smile(d); save(f, "winking", n); n += 1
    f = frame(); d = ImageDraw.Draw(f); eyes(d); mouth_smile(d); save(f, "winking", n); n += 1
    print(f"({n} frames)")


# === MAIN ===

if __name__ == "__main__":
    print("=== BMO Face Generator v3 (Expanded) ===")

    # Clear old frames
    import shutil
    for state_dir in os.listdir(OUTPUT):
        path = os.path.join(OUTPUT, state_dir)
        if os.path.isdir(path):
            shutil.rmtree(path)

    print("Generating: ", end="")
    # Core states (used by agent.py)
    gen_idle()
    gen_listening()
    gen_thinking()
    gen_speaking()
    gen_error()
    gen_capturing()
    gen_warmup()
    # New expression states
    gen_happy()
    gen_sad()
    gen_love()
    gen_surprised()
    gen_sleeping()
    gen_winking()

    print()
    total = 0
    for state in sorted(os.listdir(OUTPUT)):
        path = os.path.join(OUTPUT, state)
        if os.path.isdir(path):
            count = len([f for f in os.listdir(path) if f.endswith(".png")])
            total += count
            print(f"  {state}: {count} frames")
    print(f"  TOTAL: {total} frames")
