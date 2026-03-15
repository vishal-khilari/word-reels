"""
Instagram Word Challenge Reel Generator  [v5 — GAMIFIED + UPDATED]
═════════════════════════════════════════════════════════════════════
  Screen 1 (3 s)  : Ken Burns slow-zoom on opener image
  Screen 2 (8 s)  : Animated word reveal — elements slide/bounce in
  Screen 3 (3 s)  : Pulsing countdown 3 → 2 → 1 with heartbeat audio
  Screen 4 (60 s) : Gamified Timer with Ranking System (Novice -> Master)

  Audio            : Cinematic Heartbeat and Kick Drums.

  Changes in v5:
  - Word now fetched from Random Word API (no API key needed)
  - WORD_BANK removed
  - Countdown audio (first 3s of Screen 3) increased by 500%
  - Kick + Tick volumes reduced by 30%
  - Rank label position moved down
"""

# ── IMPORTS ────────────────────────────────────────────────────────────────────
import os, sys, wave, math, subprocess, random, tempfile
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

# ── CONFIG ─────────────────────────────────────────────────────────────────────
W, H      = 1080, 1920
FPS       = 30
_TMP      = tempfile.gettempdir()
TMP_VIDEO = os.path.join(_TMP, "reel_noaudio.mp4")
TMP_AUDIO = os.path.join(_TMP, "reel_audio.wav")
OUTPUT    = "word_reel.mp4"

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
IMG_SCREEN1 = os.path.join(SCRIPT_DIR, "Overcome_your_fear_of_speaking_in_just_60_seconds.png")
IMG_SCREEN3 = os.path.join(SCRIPT_DIR, "You_have_60_seconds_to_speak_using_this_word_Don't_stop_talking.png")

# ── FONTS ──────────────────────────────────────────────────────────────────────
_GF  = "/usr/share/fonts/truetype/google-fonts"
_DV  = "/usr/share/fonts/truetype/dejavu"
_WIN = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts")

def _fp(gf_name, dv_name="DejaVuSans-Bold.ttf"):
    for folder, name in [(_GF, gf_name), (_WIN, "arialbd.ttf"),
                         (_WIN, "arial.ttf"), (_DV, dv_name)]:
        p = os.path.join(folder, name)
        if os.path.exists(p): return p
    return None

F_BOLD  = _fp("Poppins-Bold.ttf")
F_MED   = _fp("Poppins-Medium.ttf",  "DejaVuSans.ttf")
F_LIGHT = _fp("Poppins-Light.ttf",   "DejaVuSans.ttf")

# ── COLOURS ────────────────────────────────────────────────────────────────────
WHITE  = (255, 255, 255)
DARK   = ( 15,  40,  80)
YELLOW = (255, 210,  50)
NEON_GREEN = (50, 255, 100)

_G_TOP_BLUE   = (  8,  25,  75);  _G_BOT_BLUE   = ( 40, 120, 210)
_G_TOP_ORANGE = ( 75,  30,  10);  _G_BOT_ORANGE = (210, 110,  30)
_G_TOP_RED    = ( 90,   8,   8);  _G_BOT_RED    = (210,  35,  35)

# ── CORE HELPERS ───────────────────────────────────────────────────────────────
def fnt(path, size):
    if path and os.path.exists(path):
        try: return ImageFont.truetype(path, max(1, size))
        except: pass
    return ImageFont.load_default()

def lerp(a, b, t):      return a + (b - a) * t
def clamp(v, lo=0.0, hi=1.0): return max(lo, min(hi, v))
def ease_out(t):        t = clamp(t); return 1 - (1 - t) ** 3
def ease_in_out(t):     t = clamp(t); return t * t * (3 - 2 * t)

def lerp_color(c1, c2, t):
    t = clamp(t)
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))

def pil2cv(img):
    return cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)

def tsz(draw, text, font):
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0], bb[3] - bb[1]

def composite(base_rgb, overlay_rgba):
    b = base_rgb.convert("RGBA")
    b.alpha_composite(overlay_rgba)
    return b.convert("RGB")

def draw_text_stroked(draw, pos, text, font, fill, stroke_fill=WHITE, stroke_width=3):
    x, y = pos
    for dx in range(-stroke_width, stroke_width + 1):
        for dy in range(-stroke_width, stroke_width + 1):
            if dx == 0 and dy == 0: continue
            if abs(dx) == stroke_width or abs(dy) == stroke_width:
                draw.text((x + dx, y + dy), text, font=font, fill=stroke_fill)
    draw.text((x, y), text, font=font, fill=fill)

def draw_wrapped_on(draw, text, x, y, font, color_rgba, max_w, gap=18):
    words  = text.split()
    lines, cur = [], []
    for w in words:
        test = " ".join(cur + [w])
        tw, _ = tsz(draw, test, font)
        if tw > max_w and cur:
            lines.append(" ".join(cur)); cur = [w]
        else:
            cur.append(w)
    if cur: lines.append(" ".join(cur))
    for line in lines:
        draw.text((x, y), line, font=font, fill=color_rgba)
        _, lh = tsz(draw, line, font)
        y += lh + gap
    return y

# ── GRADIENT BACKGROUND ────────────────────────────────────────────────────────
def gradient_bg(t_color=0.0):
    t_color = clamp(t_color)
    if t_color <= 0.5:
        t2  = t_color * 2.0
        top = lerp_color(_G_TOP_BLUE,   _G_TOP_ORANGE, t2)
        bot = lerp_color(_G_BOT_BLUE,   _G_BOT_ORANGE, t2)
    else:
        t2  = (t_color - 0.5) * 2.0
        top = lerp_color(_G_TOP_ORANGE, _G_TOP_RED,    t2)
        bot = lerp_color(_G_BOT_ORANGE, _G_BOT_RED,    t2)

    ys  = np.linspace(0, 1, H, dtype=np.float32).reshape(H, 1, 1)
    row = (np.array(top, dtype=np.float32) * (1 - ys) +
           np.array(bot, dtype=np.float32) * ys).astype(np.uint8)
    arr = np.broadcast_to(row, (H, W, 3)).copy()
    return Image.fromarray(arr, "RGB")

# ══════════════════════════════════════════════════════════════════════════════
#  SCREEN 1 — KEN BURNS SLOW ZOOM  (3 s)
# ══════════════════════════════════════════════════════════════════════════════
def make_screen1_frame(f, total_frames):
    img = gradient_bg(0.0)
    if not os.path.exists(IMG_SCREEN1):
        return img

    overlay = Image.open(IMG_SCREEN1).convert("RGBA")
    t       = ease_in_out(f / max(total_frames - 1, 1))

    sw = int((W - 50) + 80 * t)
    sh = int(overlay.height * sw / overlay.width)
    overlay = overlay.resize((sw, sh), Image.LANCZOS)

    x = (W - sw) // 2
    y = (H - sh) // 2 - 60

    img = img.convert("RGBA")
    img.paste(overlay, (x, y), overlay)

    if f < 12:
        alpha_black = 255 - int(255 * f / 12)
        black = Image.new("RGBA", (W, H), (0, 0, 0, alpha_black))
        img.alpha_composite(black)

    return img.convert("RGB")

# ══════════════════════════════════════════════════════════════════════════════
#  SCREEN 2 — ANIMATED WORD REVEAL  (8 s)
# ══════════════════════════════════════════════════════════════════════════════
def make_screen2_frame(word, pos, defn, f, total_frames):
    t   = f / FPS
    img = gradient_bg(0.0).convert("RGBA")

    LEFT       = 70
    MAX_W_DEFN = W - 340

    f1 = fnt(F_BOLD,   95)
    f2 = fnt(F_BOLD,  148)
    f3 = fnt(F_MED,    80)
    f4 = fnt(F_MED,    80)
    f5 = fnt(F_LIGHT,  74)

    _d = ImageDraw.Draw(img)
    _, h1  = tsz(_d, "Today's word:", f1)
    _, h2  = tsz(_d, word.capitalize(), f2)
    _, h3a = tsz(_d, "Part of speech:", f3)
    _, h3b = tsz(_d, (pos or "").capitalize(), f3)
    _, h4  = tsz(_d, "Definition:", f4)

    def wrapped_h(text, font, max_w, gap=22):
        words  = text.split()
        lines, cur = [], []
        for w in words:
            test = " ".join(cur + [w])
            if tsz(_d, test, font)[0] > max_w and cur:
                lines.append(" ".join(cur)); cur = [w]
            else:
                cur.append(w)
        if cur: lines.append(" ".join(cur))
        return sum(tsz(_d, l, font)[1] + gap for l in lines)

    h5 = wrapped_h(defn or "", f5, MAX_W_DEFN)

    G1, G2, G3, G4, G5 = 28, 88, 10, 72, 22
    total_h = h1 + G1 + h2 + G2 + h3a + G3 + h3b + G4 + h4 + G5 + h5
    y0      = max(130, (H - total_h) // 2 - 80)

    y_lbl  = y0
    y_word = y0 + h1 + G1
    y_pos1 = y_word + h2 + G2
    y_pos2 = y_pos1 + h3a + G3
    y_def1 = y_pos2 + h3b + G4
    y_def2 = y_def1 + h4  + G5

    SLIDE = 95

    if t >= 0.0:
        pe  = ease_out(clamp(t / 1.1))
        alf = int(255 * clamp(t / 0.5))
        ov  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od  = ImageDraw.Draw(ov)
        draw_text_stroked(
            od, (LEFT, y_lbl + int(SLIDE * (1 - pe))),
            "Today's word:", f1,
            fill=DARK + (alf,), stroke_fill=WHITE + (alf,), stroke_width=2,
        )
        img.alpha_composite(ov)

    if t >= 1.2:
        p = clamp((t - 1.2) / 0.65)
        if p < 0.55:
            scale_anim = ease_out(p / 0.55) * 1.13
        else:
            scale_anim = 1.13 - 0.13 * ease_in_out((p - 0.55) / 0.45)
        if t > 5.8:
            scale_anim = 1.0 + 0.012 * math.sin((t - 5.8) * math.pi * 1.8)

        alf  = int(255 * clamp((t - 1.2) / 0.25))
        sz   = max(20, int(148 * scale_anim))
        f2s  = fnt(F_BOLD, sz)
        wt   = word.capitalize()
        ov   = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od   = ImageDraw.Draw(ov)
        ww2, wh2 = tsz(od, wt, f2s)
        od.text(((W - ww2) // 2, y_word - (wh2 - h2) // 2),
                wt, font=f2s, fill=WHITE + (alf,))
        img.alpha_composite(ov)

    if t >= 2.9 and pos:
        pe  = ease_out(clamp((t - 2.9) / 0.8))
        alf = int(255 * pe)
        sl  = int(SLIDE * 0.5 * (1 - pe))
        ov  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od  = ImageDraw.Draw(ov)
        draw_text_stroked(
            od, (LEFT, y_pos1 + sl),
            "Part of speech:", f3,
            fill=DARK + (alf,), stroke_fill=WHITE + (alf,), stroke_width=2,
        )
        od.text((LEFT, y_pos2 + sl), pos.capitalize(),
                font=f3, fill=WHITE + (alf,))
        img.alpha_composite(ov)

    if t >= 4.4:
        pe  = ease_out(clamp((t - 4.4) / 1.0))
        alf = int(255 * pe)
        sl  = int(SLIDE * 0.4 * (1 - pe))
        ov  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od  = ImageDraw.Draw(ov)
        draw_text_stroked(
            od, (LEFT, y_def1 + sl),
            "Definition:", f4,
            fill=DARK + (alf,), stroke_fill=WHITE + (alf,), stroke_width=2,
        )
        if defn:
            draw_wrapped_on(od, defn, LEFT, y_def2 + sl, f5,
                            WHITE + (alf,), MAX_W_DEFN, gap=22)
        img.alpha_composite(ov)

    return img.convert("RGB")

# ══════════════════════════════════════════════════════════════════════════════
#  SCREEN 3 — PULSING COUNTDOWN  (3 s)
# ══════════════════════════════════════════════════════════════════════════════
def make_screen3_frame(n, f_in_sec, fps):
    img = gradient_bg(0.0)
    if os.path.exists(IMG_SCREEN3):
        png = Image.open(IMG_SCREEN3).convert("RGBA")
        png = png.resize((W, H), Image.LANCZOS)
        try:
            arr  = np.array(png)
            mask = (arr[:, :, 0] < 60) & (arr[:, :, 1] < 60) & (arr[:, :, 2] < 60)
            arr[mask, 3] = 0
            png  = Image.fromarray(arr)
        except Exception:
            pass
        img = img.convert("RGBA")
        img.alpha_composite(png)
        img = img.convert("RGB")

    draw = ImageDraw.Draw(img)
    t    = f_in_sec / fps

    if t < 0.22:
        scale = 0.45 + 0.70 * ease_out(t / 0.22)
    elif t < 0.42:
        scale = 1.15 - 0.15 * ease_in_out((t - 0.22) / 0.20)
    else:
        scale = 1.0 + 0.010 * math.sin(t * math.pi * 3.5)

    cr  = max(10, int(285 * scale))
    ccx = W // 2
    ccy = H - 500

    c_bg  = (88, 155, 218)
    c_bdr = (28,  88, 152)
    draw.ellipse([ccx - cr, ccy - cr, ccx + cr, ccy + cr],
                 fill=c_bg, outline=c_bdr, width=14)

    sz    = max(20, int(360 * scale))
    f_num = fnt(F_BOLD, sz)
    num   = str(n)
    nw, nh = tsz(draw, num, f_num)
    draw.text((ccx - nw // 2, ccy - nh // 2 - int(62 * scale)),
              num, font=f_num, fill=DARK)
    return img

# ══════════════════════════════════════════════════════════════════════════════
#  SCREEN 4 — FULL TIMER + GAMIFICATION (60 s)
# ══════════════════════════════════════════════════════════════════════════════
def make_screen4_frame(word, secs_left):
    secs_left = max(0.0, secs_left)
    elapsed   = 60.0 - secs_left

    if secs_left > 30:
        t_col = 0.0
    elif secs_left > 10:
        t_col = 0.5 * (30 - secs_left) / 20.0
    else:
        t_col = 0.5 + 0.5 * (10 - secs_left) / 10.0

    img  = gradient_bg(t_col)

    # ─── SHAKE EFFECT (Last 10s) ──────────────────────────────────────────────
    shake_x, shake_y = 0, 0
    if secs_left <= 10.0 and secs_left > 0.1:
        intensity = (10.0 - secs_left) / 10.0
        amp = 4 + 8 * intensity
        shake_x = int(random.uniform(-amp, amp))
        shake_y = int(random.uniform(-amp, amp))

    draw = ImageDraw.Draw(img)

    f_lbl  = fnt(F_MED, 100)
    label  = f"Word: {word.capitalize()}"
    blinks = (10, 20, 30, 40, 50)
    is_blink = any(abs(secs_left - bm) < 0.55 for bm in blinks)
    lw, _  = tsz(draw, label, f_lbl)

    # Draw Word Label
    word_y = 195
    draw.text(((W - lw) // 2 + shake_x, word_y + shake_y), label, font=f_lbl,
              fill=YELLOW if is_blink else WHITE)

    # ─── RANK DISPLAY — moved down by 60px ────────────────────────────────────
    rank = "NOVICE"
    rank_col = (200, 200, 200)
    if secs_left < 15:
        rank = "MASTER"
        rank_col = NEON_GREEN
    elif secs_left < 30:
        rank = "PRO"
        rank_col = YELLOW
    elif secs_left < 45:
        rank = "APPRENTICE"
        rank_col = (100, 200, 255)

    f_rank = fnt(F_BOLD, 54)
    rw, rh = tsz(draw, f"RANK: {rank}", f_rank)
    # ↓ Changed from word_y + 110  →  word_y + 170  (moved down 60 px)
    rank_y = word_y + 170
    draw_text_stroked(draw, ((W - rw) // 2 + shake_x, rank_y + shake_y),
                      f"RANK: {rank}", f_rank,
                      fill=rank_col, stroke_fill=DARK, stroke_width=2)

    cx_c = W // 2 + shake_x
    cy_c = H // 2 + 90 + shake_y

    if secs_left <= 10:
        pulse_speed, pulse_amp = 4.2, 0.028
    else:
        pulse_speed, pulse_amp = 1.2, 0.010

    r = int(318 * (1.0 + pulse_amp * math.sin(elapsed * math.pi * pulse_speed)))

    if secs_left > 30:
        c_bg  = ( 80, 148, 210);  c_bdr = ( 28,  88, 152)
        arc_rgba = (255, 255, 255, 215)
    elif secs_left > 10:
        tt    = (30 - secs_left) / 20.0
        c_bg  = lerp_color(( 80, 148, 210), (195, 118,  42), tt)
        c_bdr = lerp_color(( 28,  88, 152), (148,  70,  16), tt)
        arc_rgba = (255, int(lerp(255, 155, tt)), int(lerp(255, 38, tt)), 215)
    else:
        tt    = (10 - secs_left) / 10.0
        c_bg  = lerp_color((195, 118,  42), (195,  38,  38), tt)
        c_bdr = lerp_color((148,  70,  16), (132,  16,  16), tt)
        arc_rgba = (255, int(lerp(155, 52, tt)), int(lerp(38, 38, tt)), 215)

    draw.ellipse([cx_c - r, cy_c - r, cx_c + r, cy_c + r],
                 fill=c_bg, outline=c_bdr, width=18)

    sweep = int(360 * secs_left / 60.0)
    if sweep > 0:
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        od.arc([cx_c - r, cy_c - r, cx_c + r, cy_c + r],
               start=-90, end=-90 + sweep, fill=arc_rgba, width=28)
        img  = composite(img, ov)
        draw = ImageDraw.Draw(img)

    f_num  = fnt(F_BOLD, 360)
    num    = str(max(0, int(math.ceil(secs_left))))
    nw, nh = tsz(draw, num, f_num)
    num_col = WHITE if secs_left <= 10 else DARK
    num_x   = cx_c - nw // 2
    num_y   = cy_c - nh // 2 - 65
    draw.text((num_x, num_y), num, font=f_num, fill=num_col)

    # ─── HALFWAY MARKER ───────────────────────────────────────────────────────
    if 28.8 <= secs_left <= 31.2:
        t_fl  = ease_in_out(1.0 - abs(secs_left - 30.0) / 1.2)
        alf   = int(235 * t_fl)
        f_hf  = fnt(F_BOLD, 116)
        hw, hh = tsz(draw, "HALFWAY!", f_hf)
        pad   = 30
        y_hf  = cy_c - r - 185
        ov    = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od    = ImageDraw.Draw(ov)
        try:
            od.rounded_rectangle(
                [(W // 2 - hw // 2 - pad + shake_x,  y_hf - pad // 2 + shake_y),
                 (W // 2 + hw // 2 + pad + shake_x,  y_hf + hh + pad + shake_y)],
                radius=36, fill=YELLOW + (alf,))
        except AttributeError:
            od.rectangle(
                [(W // 2 - hw // 2 - pad + shake_x,  y_hf - pad // 2 + shake_y),
                 (W // 2 + hw // 2 + pad + shake_x,  y_hf + hh + pad + shake_y)],
                fill=YELLOW + (alf,))
        draw_text_stroked(od, ((W - hw) // 2 + shake_x, y_hf + shake_y), "HALFWAY!", f_hf,
                          fill=DARK + (alf,),
                          stroke_fill=(255, 255, 255, alf),
                          stroke_width=2)
        img  = composite(img, ov)
        draw = ImageDraw.Draw(img)

    bx1, bx2 = 80, W - 80
    by,  bh  = H - 155, 20
    br       = 10

    # Progress Bar Background
    try:
        draw.rounded_rectangle([bx1+shake_x, by+shake_y, bx2+shake_x, by+bh+shake_y], radius=br, fill=(38, 42, 72))
    except AttributeError:
        draw.rectangle([bx1+shake_x, by+shake_y, bx2+shake_x, by+bh+shake_y], fill=(38, 42, 72))

    # Progress Bar Fill
    fill_w = int((bx2 - bx1) * secs_left / 60.0)
    if fill_w > br * 2:
        fc = lerp_color((95, 190, 255), (255, 65, 65), 1.0 - secs_left / 60.0)
        try:
            draw.rounded_rectangle([bx1+shake_x, by+shake_y, bx1 + fill_w+shake_x, by + bh+shake_y], radius=br, fill=fc)
        except AttributeError:
            draw.rectangle([bx1+shake_x, by+shake_y, bx1 + fill_w+shake_x, by + bh+shake_y], fill=fc)

    f_cmt = fnt(F_MED, 62)
    cmt   = "Comment your attempt below! 👇"
    cw, _ = tsz(draw, cmt, f_cmt)
    draw.text(((W - cw) // 2 + shake_x, H - 262 + shake_y), cmt, font=f_cmt, fill=WHITE)

    if secs_left <= 3.0:
        t_end = ease_in_out(1.0 - secs_left / 3.0)
        alf   = int(215 * t_end)
        f_end = fnt(F_BOLD, 90)
        lines = ["Follow for", "tomorrow's word! 🔔"]
        ov    = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od    = ImageDraw.Draw(ov)
        od.rectangle([0, 0, W, H], fill=(0, 0, 0, alf))
        th    = sum(tsz(od, l, f_end)[1] + 24 for l in lines)
        yy    = (H - th) // 2
        for line in lines:
            lw2, lh2 = tsz(od, line, f_end)
            od.text(((W - lw2) // 2, yy), line, font=f_end, fill=WHITE + (alf,))
            yy += lh2 + 24
        img = composite(img, ov)

    return img

# ══════════════════════════════════════════════════════════════════════════════
#  AUDIO - CINEMATIC PROCEDURAL SYNTH
#  Changes:
#    - v_kick reduced by 30%  (0.75 → 0.525)
#    - v_tick reduced by 30%  (0.30 → 0.21)
#    - Countdown beats (Screen 3, 11/12/13s) increased by 500% on top of base
# ══════════════════════════════════════════════════════════════════════════════
SAMPLE_RATE = 44100

def gen_kick(freq_start=150, freq_end=50, dur=0.3, vol=0.8):
    """Synthesized 808-style kick drum (pitch sweep)"""
    n = int(SAMPLE_RATE * dur)
    t = np.linspace(0, dur, n, False)
    freq = freq_start * (freq_end / freq_start)**(t / dur)
    phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
    waveform = np.sin(phase)
    env = np.exp(-15 * t)
    waveform *= env * vol
    return (waveform * 32767).astype(np.int16)

def gen_tick(dur=0.05, vol=0.4):
    """High pitched woodblock/tick"""
    n = int(SAMPLE_RATE * dur)
    t = np.linspace(0, dur, n, False)
    waveform = np.sin(2 * np.pi * 1200 * t)
    env = np.exp(-50 * t)
    waveform *= env * vol
    return (waveform * 32767).astype(np.int16)

def build_audio():
    total = 75
    audio = np.zeros(int(SAMPLE_RATE * total), dtype=np.int32)

    def mix(t_sec, sample_arr):
        s = int(SAMPLE_RATE * t_sec)
        e = s + len(sample_arr)
        if e <= len(audio):
            audio[s:e] += sample_arr.astype(np.int32)

    # ── Base volumes (both reduced by 30%) ────────────────────────────────────
    v_kick = 0.525   # was 0.75 → 0.75 * 0.70 = 0.525
    v_tick = 0.210   # was 0.30 → 0.30 * 0.70 = 0.210

    # ── Screen 3 Countdown (3→2→1) — boosted 500% on top of base ─────────────
    countdown_vol = v_kick * 1.5 * 1.60
    mix(11.0, gen_kick(dur=0.4, vol=countdown_vol))
    mix(12.0, gen_kick(dur=0.4, vol=countdown_vol))
    mix(13.0, gen_kick(dur=0.4, vol=countdown_vol))

    # ── Screen 4 Main Timer — ticks only ──────────────────────────────────────
    start_time = 14.0
    for i in range(50):
        t = start_time + i
        mix(t + 0.5, gen_tick(vol=v_tick))

    # ── Last 10s Panic Phase — double-speed ticks ──────────────────────────────
    for i in range(10):
        t = start_time + 50 + i
        mix(t,       gen_tick(vol=v_tick * 1.2))
        mix(t + 0.5, gen_tick(vol=v_tick * 1.2))

    audio  = np.clip(audio, -32767, 32767).astype(np.int16)
    stereo = np.column_stack([audio, audio])
    with wave.open(TMP_AUDIO, "w") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(stereo.tobytes())

# ══════════════════════════════════════════════════════════════════════════════
#  WORD FETCH — Random Word API (no key needed) + dictionaryapi.dev for defn
# ══════════════════════════════════════════════════════════════════════════════
FALLBACKS = [
    ("resilient",   "adjective", "Able to recover quickly from difficult conditions."),
    ("eloquent",    "adjective", "Fluent or persuasive in speaking or writing."),
    ("tenacious",   "adjective", "Tending to keep a firm hold of something; persistent."),
    ("audacious",   "adjective", "Showing a willingness to take surprisingly bold risks."),
    ("empathy",     "noun",      "The ability to understand and share the feelings of another."),
    ("deliberate",  "adjective", "Done consciously and intentionally; careful and unhurried."),
    ("persevere",   "verb",      "Continue in a course of action in spite of difficulty."),
    ("integrity",   "noun",      "The quality of being honest and having strong moral principles."),
    ("articulate",  "adjective", "Having or showing the ability to speak fluently and coherently."),
    ("meticulous",  "adjective", "Showing great attention to detail; very careful and precise."),
    ("assertive",   "adjective", "Having or showing a confident and forceful personality."),
    ("candid",      "adjective", "Truthful and straightforward; frank in what one says or writes."),
    ("pragmatic",   "adjective", "Dealing with things sensibly and realistically in a practical way."),
]

def _good_defn(defn: str) -> bool:
    d = defn.strip()
    return (
        len(d) >= 55
        and d.count(" ") >= 7
        and not d.endswith((":", ",", "(", "that is,", "i.e."))
        and not any(skip in d.lower() for skip in
                    ["symbol", "abbrev", "abbreviation", "see also",
                     "plural of", "past tense of", "variant of",
                     "short for", "archaic", "dated term"])
    )

def get_word():
    import requests as _req

    preferred_pos = ["adjective", "verb", "adverb", "noun"]
    max_attempts  = 15  # try up to 15 random words

    for _ in range(max_attempts):
        try:
            # Step 1: Fetch a random word from Random Word API
            r = _req.get(
                "https://random-word-api.herokuapp.com/word?number=1",
                timeout=5)
            if r.status_code != 200:
                continue
            word = r.json()[0].lower().strip()

            # Step 2: Fetch its definition from dictionary API
            r2 = _req.get(
                f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}",
                timeout=5)
            if r2.status_code != 200:
                continue

            data     = r2.json()[0]
            meanings = data.get("meanings", [])

            for pref in preferred_pos:
                for m in meanings:
                    if m["partOfSpeech"] == pref:
                        d = m["definitions"][0]["definition"]
                        if _good_defn(d):
                            print(f"    Word: {word.upper()}")
                            return word, pref, d

        except Exception:
            continue

    # Fallback if all API attempts fail
    return random.choice(FALLBACKS)

# ══════════════════════════════════════════════════════════════════════════════
#  BGM PICKER
# ══════════════════════════════════════════════════════════════════════════════
def pick_bgm():
    for folder_name in ("Audios", "audios", "AUDIOS"):
        audios_dir = os.path.join(SCRIPT_DIR, folder_name)
        if os.path.isdir(audios_dir):
            candidates = [
                f for f in os.listdir(audios_dir)
                if f.lower().endswith((".mp3", ".wav", ".aac", ".m4a"))
            ]
            if candidates:
                chosen = random.choice(candidates)
                return os.path.join(audios_dir, chosen), f"{folder_name}/{chosen}"
    return None, None

# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════
def main():
    skip_upload = "--no-upload" in sys.argv
    try:
        import telegram_notifier as tg
        tg_ok = True
    except ImportError:
        tg_ok = False
        print("⚠️  telegram_notifier.py not found — Telegram notifications disabled.")  # ← restored from v3

    print("🎬  Word Challenge Reel Generator  [v5 — GAMIFIED + UPDATED]")
    print("─" * 56)

    if tg_ok: tg.notify_start()

    bgm_path, bgm_display = pick_bgm()
    print(f"  🎵  BGM: {bgm_display if bgm_path else 'None'}")

    print("\n📖  Fetching word from Random Word API…")
    try:                                          # ← restored try/except from v3
        word, pos, defn = get_word()
    except Exception as e:
        if tg_ok: tg.notify_error("Word fetch", str(e))
        raise
    print(f"    Word: {word.upper()}\n")

    if tg_ok: tg.notify_word(word, pos, defn)

    caption = None
    try:
        from instagram_uploader import build_caption
        caption = build_caption(word, pos, defn)
    except: pass

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(TMP_VIDEO, fourcc, FPS, (W, H))

    print("▶  Screen 1/4  Opener …")
    s1_tot = 3 * FPS
    for f in range(s1_tot):
        writer.write(pil2cv(make_screen1_frame(f, s1_tot)))

    print("▶  Screen 2/4  Reveal …")
    s2_tot = 8 * FPS
    for f in range(s2_tot):
        writer.write(pil2cv(make_screen2_frame(word, pos, defn, f, s2_tot)))

    print("▶  Screen 3/4  Countdown …")
    for n in [3, 2, 1]:
        for f in range(FPS):
            writer.write(pil2cv(make_screen3_frame(n, f, FPS)))

    print("▶  Screen 4/4  Timer …")
    s4_tot = 60 * FPS
    for f in range(s4_tot):
        secs = 60.0 - f / FPS
        writer.write(pil2cv(make_screen4_frame(word, secs)))
    writer.release()

    print("\n🔊  Building audio…")
    build_audio()

    print("🎞   Merging…")
    _V = ["-c:v", "libx264", "-preset", "fast", "-crf", "22", "-pix_fmt", "yuv420p"]
    _A = ["-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2"]
    _S = ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]

    if bgm_path:
        cmd = ["ffmpeg", "-y",
               "-i", TMP_VIDEO,
               "-i", TMP_AUDIO,
               "-i", bgm_path,
               *_S,
               "-filter_complex",
               "[2:a]volume=7[bgm_v];"
               "[1:a][bgm_v][3:a]amix=inputs=3:duration=first:weights=1 1 0.15[a]",
               "-map", "0:v", "-map", "[a]", *_V, *_A, "-movflags", "+faststart", OUTPUT]
    else:
        cmd = ["ffmpeg", "-y", "-i", TMP_VIDEO, "-i", TMP_AUDIO, *_S,
               "-filter_complex", "[1:a][2:a]amix=inputs=2:duration=first:weights=1 0.1[a]",
               "-map", "0:v", "-map", "[a]", *_V, *_A, "-movflags", "+faststart", OUTPUT]

    subprocess.run(cmd, capture_output=True)
    print(f"\n✅  Saved → {OUTPUT}")

    if tg_ok: tg.notify_render_done(OUTPUT)                                      # ← restored from v3
    if tg_ok: tg.send_video(OUTPUT, caption=f"🎬 Preview: word is <b>{word.upper()}</b>")  # ← restored from v3

    if skip_upload:
        msg = "--no-upload flag was passed."                                      # ← restored from v3
        print(f"\n⏭   Skipping Instagram upload ({msg})")
        if tg_ok: tg.notify_skipped(msg)
    else:
        print("\n" + "─" * 45)
        print("📱  Uploading to Instagram…")
        print("─" * 45)
        if tg_ok: tg.notify_upload_start()                                       # ← restored from v3
        try:
            from instagram_uploader import upload_reel
            post_id = upload_reel(video_path=OUTPUT, word=word, pos=pos, defn=defn, prebuilt_caption=caption)
            print(f"\n🎉  Reel is LIVE!  (Post ID: {post_id})")
            if tg_ok: tg.notify_live(post_id, word)                              # ← restored from v3
        except ImportError:
            msg = "instagram_uploader.py not found — skipping upload."           # ← restored from v3
            print(f"⚠️  {msg}")
            if tg_ok: tg.notify_skipped(msg)
        except Exception as e:
            print(f"❌  Upload failed:\n    {e}")
            print(f"    Video saved locally as: {OUTPUT}")
            if tg_ok: tg.notify_error("Instagram upload", str(e))               # ← restored from v3

    print("\n📱  Done!")


if __name__ == "__main__":
    main()