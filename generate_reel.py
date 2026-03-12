"""
Instagram Word Challenge Reel Generator  [v3 — FINAL]
═══════════════════════════════════════════════════════
  Screen 1 (3 s)  : Ken Burns slow-zoom on opener image
  Screen 2 (8 s)  : Animated word reveal — elements slide/bounce in
  Screen 3 (3 s)  : Pulsing countdown 3 → 2 → 1 with bounce animation
  Screen 4 (60 s) : Gradient shifts blue→orange→red, pulsing circle,
                    colour-coded arc, HALFWAY! badge, progress bar,
                    yellow word blink every 10 s, urgency mode <10 s,
                    "Comment below 👇" CTA, end card last 3 s

  Audio            : Countdown beeps + 10-second ticks + urgency beeps
  Random Music     : Place mp3/wav/aac/m4a files in an "audios/" sub-folder.
                     One is chosen at random each run, mixed at 30% volume.

Run:  python3 generate_reel.py
      python3 generate_reel.py --no-upload   ← skip Instagram upload

Requires: pip install opencv-python pillow numpy requests
          ffmpeg must be on PATH for audio merging
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

def draw_wrapped_stroked(draw, text, x, y, font, fill, stroke_fill,
                         stroke_width, max_w, gap=18):
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
        draw_text_stroked(draw, (x, y), line, font, fill,
                          stroke_fill=stroke_fill, stroke_width=stroke_width)
        _, lh = tsz(draw, line, font)
        y += lh + gap
    return y

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
#  SCREEN 4 — FULL TIMER  (60 s)
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
    draw = ImageDraw.Draw(img)

    f_lbl  = fnt(F_MED, 100)
    label  = f"Word: {word.capitalize()}"
    blinks = (10, 20, 30, 40, 50)
    is_blink = any(abs(secs_left - bm) < 0.55 for bm in blinks)
    lw, _  = tsz(draw, label, f_lbl)
    draw.text(((W - lw) // 2, 195), label, font=f_lbl,
              fill=YELLOW if is_blink else WHITE)

    cx_c = W // 2
    cy_c = H // 2 + 90

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
                [(W // 2 - hw // 2 - pad,  y_hf - pad // 2),
                 (W // 2 + hw // 2 + pad,  y_hf + hh + pad)],
                radius=36, fill=YELLOW + (alf,))
        except AttributeError:
            od.rectangle(
                [(W // 2 - hw // 2 - pad,  y_hf - pad // 2),
                 (W // 2 + hw // 2 + pad,  y_hf + hh + pad)],
                fill=YELLOW + (alf,))
        draw_text_stroked(od, ((W - hw) // 2, y_hf), "HALFWAY!", f_hf,
                          fill=DARK + (alf,),
                          stroke_fill=(255, 255, 255, alf),
                          stroke_width=2)
        img  = composite(img, ov)
        draw = ImageDraw.Draw(img)

    bx1, bx2 = 80, W - 80
    by,  bh  = H - 155, 20
    br       = 10
    try:
        draw.rounded_rectangle([bx1, by, bx2, by + bh], radius=br, fill=(38, 42, 72))
    except AttributeError:
        draw.rectangle([bx1, by, bx2, by + bh], fill=(38, 42, 72))
    fill_w = int((bx2 - bx1) * secs_left / 60.0)
    if fill_w > br * 2:
        fc = lerp_color((95, 190, 255), (255, 65, 65), 1.0 - secs_left / 60.0)
        try:
            draw.rounded_rectangle([bx1, by, bx1 + fill_w, by + bh], radius=br, fill=fc)
        except AttributeError:
            draw.rectangle([bx1, by, bx1 + fill_w, by + bh], fill=fc)

    f_cmt = fnt(F_MED, 62)
    cmt   = "Comment your attempt below! 👇"
    cw, _ = tsz(draw, cmt, f_cmt)
    draw.text(((W - cw) // 2, H - 262), cmt, font=f_cmt, fill=WHITE)

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
#  AUDIO
# ══════════════════════════════════════════════════════════════════════════════
SAMPLE_RATE = 44100

def gen_beep(freq=880, dur=0.22, vol=0.7):
    n    = int(SAMPLE_RATE * dur)
    t    = np.linspace(0, dur, n, False)
    d    = np.sin(2 * np.pi * freq * t) * vol
    fade = max(1, int(n * 0.08))
    d[:fade]  *= np.linspace(0, 1, fade)
    d[-fade:] *= np.linspace(1, 0, fade)
    return (d * 32767).astype(np.int16)

def build_audio():
    total = 75
    audio = np.zeros(int(SAMPLE_RATE * total), dtype=np.int32)

    def mix(t_sec, beep_arr):
        s = int(SAMPLE_RATE * t_sec)
        e = s + len(beep_arr)
        if e <= len(audio):
            audio[s:e] += beep_arr.astype(np.int32)

    for t_b, freq in [(11.0, 700), (12.0, 700), (13.0, 1250)]:
        mix(t_b, gen_beep(freq=freq, dur=0.28, vol=0.82))

    for elapsed_10 in (10, 20, 30, 40):
        mix(14 + elapsed_10, gen_beep(freq=1050, dur=0.08, vol=0.38))

    for i in range(5):
        mix(69 + i, gen_beep(freq=1450, dur=0.14, vol=0.60))

    audio  = np.clip(audio, -32767, 32767).astype(np.int16)
    # Duplicate mono → stereo so ffmpeg receives a stereo source.
    # Instagram requires stereo AAC; upmixing at the ffmpeg stage
    # sometimes produces a silent or dropped audio track on upload.
    stereo = np.column_stack([audio, audio])
    with wave.open(TMP_AUDIO, "w") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(stereo.tobytes())

# ══════════════════════════════════════════════════════════════════════════════
#  WORD FETCH
# ══════════════════════════════════════════════════════════════════════════════
WORD_BANK = [
    "resilient", "eloquent", "tenacious", "audacious", "empathy",
    "deliberate", "persevere", "integrity", "articulate", "candid",
    "composed", "confident", "courageous", "decisive", "diligent",
    "dynamic", "enthusiastic", "flexible", "genuine", "gracious",
    "humble", "innovative", "intuitive", "meticulous", "motivated",
    "optimistic", "passionate", "patient", "perceptive", "persistent",
    "proactive", "receptive", "resourceful", "sincere", "strategic",
    "thoughtful", "transparent", "versatile", "adaptable", "assertive",
    "authentic", "compassionate", "cultivate", "dedicate", "flourish",
    "foster", "influence", "inspire", "navigate", "nurture",
    "overcome", "prioritize", "pursue", "reflect", "strive",
    "accomplish", "ambitious", "appreciate", "aspire", "clarity",
    "conscientious", "consistent", "creative", "curious", "dependable",
    "determined", "diplomatic", "discerning", "effective", "ethical",
    "expressive", "forthright", "industrious", "insightful", "judicious",
    "magnanimous", "mindful", "objective", "pragmatic", "principled",
    "proficient", "purposeful", "reliable", "remarkable", "resolute",
    "steadfast", "stoic", "tactful", "trustworthy", "unwavering",
    "vigilant", "visionary", "poised", "shrewd", "tenacity",
    "serendipity", "luminous", "invigorate", "embolden", "perseverance",
    "equanimity", "sagacious", "forthcoming", "inquisitive", "empathetic",
]

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

    candidates = WORD_BANK.copy()
    random.shuffle(candidates)

    preferred_pos = ["adjective", "verb", "adverb", "noun"]

    for w in candidates:
        try:
            r = _req.get(
                f"https://api.dictionaryapi.dev/api/v2/entries/en/{w}",
                timeout=5)
            if r.status_code != 200:
                continue
            meanings = r.json()[0]["meanings"]
            for pref in preferred_pos:
                for m in meanings:
                    if m["partOfSpeech"] == pref:
                        d = m["definitions"][0]["definition"]
                        if _good_defn(d):
                            return w, pref, d
        except Exception:
            continue

    return random.choice(FALLBACKS)

# ══════════════════════════════════════════════════════════════════════════════
#  BGM PICKER
# ══════════════════════════════════════════════════════════════════════════════
def pick_bgm():
    # Try both "Audios" (capital) and "audios" (lowercase) for cross-platform compat
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

    for name in ("bgm.mp3", "bgm.wav", "BGM.mp3", "BGM.wav"):
        path = os.path.join(SCRIPT_DIR, name)
        if os.path.exists(path):
            return path, name

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
        print("⚠️  telegram_notifier.py not found — Telegram notifications disabled.")

    print("🎬  Word Challenge Reel Generator  [v3 — FINAL]")
    print("─" * 52)

    if tg_ok:
        tg.notify_start()

    for label, path in [("Screen 1 image", IMG_SCREEN1), ("Screen 3 image", IMG_SCREEN3)]:
        ok = os.path.exists(path)
        print(f"  {'✅' if ok else '⚠️  NOT FOUND'}  {label}: {os.path.basename(path)}")

    bgm_path, bgm_display = pick_bgm()
    if bgm_path:
        print(f"  🎵  Background music: {bgm_display}")
    else:
        print("  🔇  No audio found — add files to 'audios/' for background music")

    print("\n📖  Fetching word…")
    try:
        word, pos, defn = get_word()
    except Exception as e:
        if tg_ok: tg.notify_error("Word fetch", str(e))
        raise

    print(f"    Word      : {word}")
    print(f"    POS       : {pos or 'N/A'}")
    snippet = (defn or "")[:65] + ("…" if defn and len(defn) > 65 else "")
    print(f"    Definition: {snippet}\n")

    if tg_ok:
        tg.notify_word(word, pos, defn)

    print("✨  Generating caption…")
    caption = None
    try:
        from instagram_uploader import build_caption
        caption = build_caption(word, pos, defn)
        W_BOX = 64
        SEP   = "─" * (W_BOX + 4)
        print()
        print(SEP)
        print(f"  📝  CAPTION  ({len(caption.splitlines())} lines, {len(caption)} chars)")
        print(SEP)
        for raw_line in caption.splitlines():
            if not raw_line: print(); continue
            while len(raw_line) > W_BOX:
                print("  " + raw_line[:W_BOX])
                raw_line = raw_line[W_BOX:]
            print("  " + raw_line)
        print(SEP)
        print()
    except ImportError:
        print("⚠️  instagram_uploader.py not found — caption skipped.\n")
    except Exception as e:
        print(f"⚠️  Caption generation failed: {e}\n")

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(TMP_VIDEO, fourcc, FPS, (W, H))

    print("▶  Screen 1/4  Ken Burns opener  (3 s) …", end=" ", flush=True)
    s1_tot = 3 * FPS
    for f in range(s1_tot):
        writer.write(pil2cv(make_screen1_frame(f, s1_tot)))
    print("✓")

    print("▶  Screen 2/4  Animated reveal   (8 s) …", end=" ", flush=True)
    s2_tot = 8 * FPS
    for f in range(s2_tot):
        writer.write(pil2cv(make_screen2_frame(word, pos, defn, f, s2_tot)))
    print("✓")

    print("▶  Screen 3/4  Pulsing countdown (3 s) …", end=" ", flush=True)
    for n in [3, 2, 1]:
        for f in range(FPS):
            writer.write(pil2cv(make_screen3_frame(n, f, FPS)))
    print("✓")

    print("▶  Screen 4/4  Timer            (60 s) …")
    s4_tot = 60 * FPS
    for f in range(s4_tot):
        secs = 60.0 - f / FPS
        writer.write(pil2cv(make_screen4_frame(word, secs)))
        if f % (3 * FPS) == 0:
            pct = int(f / s4_tot * 100)
            bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
            print(f"    [{bar}] {pct}%  ", end="\r")
    print(f"    [{'█' * 20}] 100% ✓")
    writer.release()

    print("\n🔊  Building audio…", end=" ", flush=True)
    build_audio()
    print("✓")

    print("🎞   Merging video + audio…", end=" ", flush=True)

    # Instagram Reels audio requirements:
    #   - AAC-LC codec, stereo, 44100 Hz, CBR 128k minimum
    #   - H.264 / yuv420p video
    #   - movflags +faststart (moov atom at front — required for API upload)
    #
    # IMPORTANT: Instagram silently drops audio tracks with bitrate < 128k.
    # Our beep WAV is mostly silence so AAC VBR compresses it to ~15 kbps
    # and Instagram drops it. Fix: mix a silent pad track so the encoder
    # always has a full-bandwidth signal, then force CBR 128k floor.
    _VIDEO_FLAGS = [
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-pix_fmt", "yuv420p",
    ]
    _AUDIO_FLAGS = [
        "-c:a", "aac", "-profile:a", "aac_low",
        "-b:a", "128k", "-ar", "44100", "-ac", "2",
    ]
    _CONTAINER_FLAGS = [
        "-movflags", "+faststart",
        "-shortest",
    ]

    # Silent pad — ensures AAC encoder always hits 128k CBR floor
    _SILENT = ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]

    if bgm_path:
        cmd = [
            "ffmpeg", "-y",
            "-i", TMP_VIDEO,
            "-i", TMP_AUDIO,
            "-i", bgm_path,
            *_SILENT,
            "-filter_complex",
            "[1:a][2:a][3:a]amix=inputs=3:duration=first:weights=1 0.3 0.05,"
            "aresample=44100,aformat=channel_layouts=stereo[aout]",
            "-map", "0:v", "-map", "[aout]",
            *_VIDEO_FLAGS, *_AUDIO_FLAGS, *_CONTAINER_FLAGS,
            OUTPUT,
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-i", TMP_VIDEO,
            "-i", TMP_AUDIO,
            *_SILENT,
            "-filter_complex",
            "[1:a][2:a]amix=inputs=2:duration=first:weights=1 0.05,"
            "aresample=44100,aformat=channel_layouts=stereo[aout]",
            "-map", "0:v", "-map", "[aout]",
            *_VIDEO_FLAGS, *_AUDIO_FLAGS, *_CONTAINER_FLAGS,
            OUTPUT,
        ]

    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        print("\n❌  ffmpeg failed! stderr output:")
        print(r.stderr.decode(errors="replace")[-1500:])
        fallback = "copy" if os.name == "nt" else "cp"
        subprocess.run([fallback, TMP_VIDEO, OUTPUT], shell=(os.name == "nt"))
        print("(saved without audio — fix ffmpeg errors above)")
    else:
        print("✓")

    mb = os.path.getsize(OUTPUT) / 1024 / 1024
    print(f"\n✅  Saved → {OUTPUT}  ({mb:.1f} MB)")
    print(f"    Word     : {word.upper()}")
    print(f"    Duration : 74 s  |  {W}×{H}  |  9:16 Reel")

    if tg_ok:
        tg.notify_render_done(OUTPUT)
        tg.send_video(OUTPUT, caption=f"🎬 Preview: word is <b>{word.upper()}</b>")

    if skip_upload:
        print("\n⏭   Skipping Instagram upload (--no-upload flag).")
        if tg_ok: tg.notify_skipped("--no-upload flag was passed.")
    else:
        print("\n" + "─" * 45)
        print("📱  Uploading to Instagram…")
        print("─" * 45)
        if tg_ok: tg.notify_upload_start()
        try:
            from instagram_uploader import upload_reel
            post_id = upload_reel(
                video_path=OUTPUT, word=word, pos=pos, defn=defn,
                prebuilt_caption=caption)
            print(f"\n🎉  Reel is LIVE!  (Post ID: {post_id})")
            if tg_ok: tg.notify_live(post_id, word)
        except ImportError:
            msg = "instagram_uploader.py not found — skipping upload."
            print(f"⚠️  {msg}")
            if tg_ok: tg.notify_skipped(msg)
        except Exception as e:
            print(f"❌  Upload failed:\n    {e}")
            print(f"    Video saved locally as: {OUTPUT}")
            if tg_ok: tg.notify_error("Instagram upload", str(e))

    print("\n📱  Done!")


if __name__ == "__main__":
    main()