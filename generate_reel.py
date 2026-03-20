"""
Instagram Word Challenge Reel Generator  [v8.2 — UI FIXES]
═══════════════════════════════════════════════════════════════════════════════
  v8.2 fixes vs v8.1:
  ─ Screen 2  : Gradient underline moved down (+22 px gap below word)
  ─ Screen 2  : "Your 60-second challenge starts now." auto-sized so it
                never overflows — font shrinks to fit W-120 px margin
  ─ Screen 4  : "HALFWAY! KEEP GOING!" banner auto-sized + wider padding so
                it never clips at edges
  ─ Screen 4  : Full UI overhaul — cleaner zone cards, crisper rank badge,
                labelled progress bar, better digit shadow, tick-mark ring

  PIPELINE:
    [Hook video from hooks/] ──► [Screen 1: Punchy Intro]
    ──► [Screen 2: Word Reveal] ──► [Screen 3: Countdown] ──► [Screen 4: 60s Timer]
"""

import os, sys, wave, math, subprocess, random, tempfile, json
import numpy as np
import cv2
import requests
from PIL import Image, ImageDraw, ImageFont

# ── OUTPUT ─────────────────────────────────────────────────────────────────────
W, H        = 1080, 1920
FPS         = 30
SAMPLE_RATE = 44100
_TMP        = tempfile.gettempdir()
TMP_VIDEO   = os.path.join(_TMP, "reel_noaudio.mp4")
TMP_AUDIO   = os.path.join(_TMP, "reel_audio.wav")
REEL_RAW    = os.path.join(_TMP, "reel_merged.mp4")
OUTPUT      = "word_reel.mp4"
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
HOOKS_DIR   = os.path.join(SCRIPT_DIR, "hooks")

# ── GEMINI ─────────────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL     = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
)

# ── SCREEN TIMING ──────────────────────────────────────────────────────────────
S1_MIN = 5.0;  PAD_S1 = 0.8
S2_MIN = 9.0;  PAD_S2 = 1.0
S3_MIN = 4.0;  PAD_S3 = 0.4
S4_DUR = 60.0

# ── VOICE POOL ─────────────────────────────────────────────────────────────────
VOICE_POOL = [
    ("en-US-JennyNeural",   "+18%", "+0Hz"),
    ("en-US-GuyNeural",     "+18%", "+0Hz"),
    ("en-GB-SoniaNeural",   "+18%", "+0Hz"),
    ("en-US-AriaNeural",    "+18%", "+2Hz"),
    ("en-AU-NatashaNeural", "+18%", "+0Hz"),
    ("en-GB-RyanNeural",    "+18%", "+0Hz"),
]

# ── FONTS ──────────────────────────────────────────────────────────────────────
_GF  = "/usr/share/fonts/truetype/google-fonts"
_DV  = "/usr/share/fonts/truetype/dejavu"
_WIN = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts")

def _fp(gf, dv="DejaVuSans-Bold.ttf"):
    for folder, name in [(_GF, gf), (_WIN, "arialbd.ttf"),
                         (_WIN, "arial.ttf"), (_DV, dv)]:
        p = os.path.join(folder, name)
        if os.path.exists(p): return p
    return None

F_BOLD  = _fp("Poppins-Bold.ttf")
F_MED   = _fp("Poppins-Medium.ttf", "DejaVuSans.ttf")
F_LIGHT = _fp("Poppins-Light.ttf",  "DejaVuSans.ttf")

# ── COLOURS ────────────────────────────────────────────────────────────────────
WHITE      = (255, 255, 255)
NAVY       = (  8,  14,  38)
YELLOW     = (255, 214,  52)
NEON_GREEN = ( 50, 255, 120)
NEON_BLUE  = ( 60, 200, 255)
CORAL      = (255,  88,  55)
PURPLE     = (160,  80, 255)

_BLU_T = (  8,  22,  72);  _BLU_B = ( 30, 100, 200)
_ORG_T = ( 72,  28,   8);  _ORG_B = (200, 105,  28)
_RED_T = ( 88,   6,   6);  _RED_B = (205,  30,  30)

# ── DETERMINISTIC PARTICLES ───────────────────────────────────────────────────
_RNG = random.Random(314159)
PARTICLES = [(_RNG.randint(20, W-20), _RNG.randint(0, H),
              _RNG.uniform(0.6, 2.8), _RNG.randint(3, 9),
              _RNG.choice([YELLOW, NEON_BLUE, WHITE]),
              _RNG.randint(55, 150)) for _ in range(32)]

# ── SCREEN-4 PROMPTS (rotates every 12 s) ─────────────────────────────────────
PROMPTS = [
    "Think of a real example from YOUR life.",
    "Use it in a sentence about your day.",
    "How does it describe someone you know?",
    "Can you use it in a question?",
    "Connect it to something that happened today.",
    "Use it to describe your biggest challenge.",
]

# ── FALLBACK WORDS ─────────────────────────────────────────────────────────────
FALLBACKS = [
    ("resilient",  "adjective", "Able to recover quickly and bounce back from any setback or difficulty."),
    ("eloquent",   "adjective", "Expressing ideas powerfully and smoothly, making every word count."),
    ("tenacious",  "adjective", "Refusing to quit — gripping a goal with fierce, unstoppable determination."),
    ("audacious",  "adjective", "Bold enough to attempt what others consider too risky or outrageous."),
    ("empathy",    "noun",      "The rare ability to genuinely feel and understand another person's emotions."),
    ("deliberate", "adjective", "Fully intentional and carefully thought through before taking any action."),
    ("persevere",  "verb",      "To push forward through difficulty without giving up until you succeed."),
    ("integrity",  "noun",      "Doing the right thing consistently, even when absolutely no one is watching."),
    ("articulate", "adjective", "Expressing thoughts and ideas with impressive clarity and natural fluency."),
    ("assertive",  "adjective", "Stating needs and opinions with calm, respectful confidence and self-belief."),
]


# ══════════════════════════════════════════════════════════════════════════════
#  CORE HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def fnt(path, size):
    if path and os.path.exists(path):
        try: return ImageFont.truetype(path, max(1, int(size)))
        except: pass
    return ImageFont.load_default()

def lerp(a, b, t):            return a + (b - a) * t
def clamp(v, lo=0., hi=1.):   return max(lo, min(hi, v))
def ease_out(t):               t = clamp(t); return 1 - (1-t)**3
def ease_in_out(t):            t = clamp(t); return t*t*(3-2*t)
def ease_elastic(t):
    t = clamp(t)
    if t in (0, 1): return t
    return pow(2, -10*t) * math.sin((t*10 - 0.75)*(2*math.pi/3)) + 1

def lerp_color(c1, c2, t):
    t = clamp(t)
    return tuple(int(c1[i] + (c2[i]-c1[i])*t) for i in range(3))

def pil2cv(img):
    return cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)

def tsz(draw, text, font):
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2]-bb[0], bb[3]-bb[1]

def composite(base, ov):
    b = base.convert("RGBA"); b.alpha_composite(ov); return b.convert("RGB")

def dark_bg():
    arr = np.full((H, W, 3), NAVY, dtype=np.uint8)
    return Image.fromarray(arr, "RGB")

def s4_bg(tc):
    tc = clamp(tc)
    if tc <= 0.5:
        top = lerp_color(_BLU_T, _ORG_T, tc*2); bot = lerp_color(_BLU_B, _ORG_B, tc*2)
    else:
        top = lerp_color(_ORG_T, _RED_T, (tc-.5)*2); bot = lerp_color(_ORG_B, _RED_B, (tc-.5)*2)
    ys  = np.linspace(0, 1, H, dtype=np.float32).reshape(H, 1, 1)
    row = (np.array(top, np.float32)*(1-ys) + np.array(bot, np.float32)*ys).astype(np.uint8)
    return Image.fromarray(np.broadcast_to(row, (H, W, 3)).copy(), "RGB")

def draw_particles(rgba_img, frame):
    ov = Image.new("RGBA", (W, H), (0,0,0,0))
    od = ImageDraw.Draw(ov)
    for px, py, spd, r, col, alf in PARTICLES:
        y = int((py - frame*spd) % H)
        od.ellipse([px-r, y-r, px+r, y+r], fill=col+(alf,))
    rgba_img.alpha_composite(ov)

def auto_fnt(draw, text, fp, max_w, start=180, step=6, min_sz=40):
    for sz in range(start, min_sz-1, -step):
        f = fnt(fp, sz); w, h = tsz(draw, text, f)
        if w <= max_w: return f, w, h
    f = fnt(fp, min_sz); return f, *tsz(draw, text, f)

def wrap_lines(draw, text, font, max_w):
    words, lines, cur = text.split(), [], []
    for w in words:
        test = " ".join(cur+[w])
        if tsz(draw, test, font)[0] > max_w and cur:
            lines.append(" ".join(cur)); cur = [w]
        else: cur.append(w)
    if cur: lines.append(" ".join(cur))
    return [(l, *tsz(draw, l, font)) for l in lines]

def rrect(draw, box, r, fill, outline=None, width=0):
    try:    draw.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)
    except: draw.rectangle(box, fill=fill, outline=outline, width=width)

def fade_frame(img, f, total, fi=14, fo=18):
    ov = None
    if f < fi:          ov = Image.new("RGBA",(W,H),(0,0,0,255-int(255*f/fi)))
    elif f > total-fo:  ov = Image.new("RGBA",(W,H),(0,0,0,int(255*(f-(total-fo))/fo)))
    if ov:
        b = img.convert("RGBA"); b.alpha_composite(ov); return b.convert("RGB")
    return img


# ── VIGNETTE ──────────────────────────────────────────────────────────────────
def _make_vignette():
    xs = np.linspace(-1.0, 1.0, W, dtype=np.float32)
    ys = np.linspace(-1.0, 1.0, H, dtype=np.float32)
    xx, yy = np.meshgrid(xs, ys)
    dist   = np.sqrt(xx**2 + (yy * (H / W))**2)
    alpha  = np.clip((dist - 0.52) * 195, 0, 170).astype(np.uint8)
    ov     = np.zeros((H, W, 4), dtype=np.uint8)
    ov[:, :, 3] = alpha
    return Image.fromarray(ov)

VIGNETTE = _make_vignette()

def add_vignette(img):
    b = img.convert("RGBA")
    b.alpha_composite(VIGNETTE)
    return b.convert("RGB")


# ══════════════════════════════════════════════════════════════════════════════
#  TTS
# ══════════════════════════════════════════════════════════════════════════════
def _silence(path, dur):
    with wave.open(path, "w") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SAMPLE_RATE)
        wf.writeframes(np.zeros(int(SAMPLE_RATE*dur), np.int16).tobytes())

def tts_gen(text, out_path, voice, rate, pitch):
    import asyncio
    mp3 = out_path.replace(".wav", "_raw.mp3")

    async def _speak():
        try:
            import edge_tts
            await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(mp3)
            return True
        except Exception as e:
            print(f"      edge-tts error: {e}"); return False

    try:
        ok = asyncio.run(_speak())
    except RuntimeError:
        loop = asyncio.new_event_loop(); ok = loop.run_until_complete(_speak()); loop.close()

    if ok and os.path.exists(mp3) and os.path.getsize(mp3) > 400:
        r = subprocess.run(["ffmpeg","-y","-i",mp3,"-ar",str(SAMPLE_RATE),
                            "-ac","1","-sample_fmt","s16",out_path],
                           capture_output=True, timeout=30)
        if r.returncode == 0 and os.path.exists(out_path):
            try: os.remove(mp3)
            except: pass
            return True

    dur = max(1.0, len(text.split()) * 0.38)
    print(f"      TTS failed — {dur:.1f}s silence inserted")
    _silence(out_path, dur); return False

def wav_dur(path):
    if not os.path.exists(path): return 1.0
    try:
        with wave.open(path) as wf: return wf.getnframes() / float(wf.getframerate())
    except: return 1.0

def build_audio_track(clips, total_dur):
    n     = int(SAMPLE_RATE * (total_dur + 2.0))
    track = np.zeros(n, np.float32)
    for offset, path in clips:
        if not (path and os.path.exists(path)): continue
        try:
            with wave.open(path) as wf:
                raw = wf.readframes(wf.getnframes())
            data = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
            s = int(offset * SAMPLE_RATE); e = min(s+len(data), n)
            if s < n: track[s:e] += data[:e-s]
        except: pass
    peak = np.max(np.abs(track))
    if peak > 0.90: track *= 0.90/peak
    stereo = (np.clip(np.column_stack([track,track]),-1,1)*32767).astype(np.int16)
    with wave.open(TMP_AUDIO, "w") as wf:
        wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(SAMPLE_RATE)
        wf.writeframes(stereo.tobytes())


# ══════════════════════════════════════════════════════════════════════════════
#  SCREEN 1  —  ANIMATED INTRO
# ══════════════════════════════════════════════════════════════════════════════
def make_screen1_frame(f, total_frames):
    t   = f / FPS
    img = dark_bg().convert("RGBA")
    draw_particles(img, f)

    CX    = W // 2
    SLIDE = 100

    def sa(start, spd=0.50):
        pe  = ease_out(clamp((t-start)/spd))
        alf = int(255*clamp((t-start)/(spd*0.40)))
        return pe, alf

    def text_ov(text, font, x, y, color, alf, shadow_col=None, shadow_off=(5,5)):
        ov = Image.new("RGBA",(W,H),(0,0,0,0))
        od = ImageDraw.Draw(ov)
        if shadow_col:
            od.text((x+shadow_off[0], y+shadow_off[1]), text,
                    font=font, fill=shadow_col+(int(alf*0.35),))
        od.text((x, y), text, font=font, fill=color+(alf,))
        img.alpha_composite(ov)

    if t >= 0.3:
        pe, alf = sa(0.3, 0.45)
        f_n = fnt(F_BOLD, 250)
        d   = ImageDraw.Draw(Image.new("RGB",(1,1)))
        tw, th = tsz(d, "NOW.", f_n)
        x = CX - tw//2;  y = 280 + int(SLIDE*(1-pe))
        for gi in (10, 7, 4):
            text_ov("NOW.", f_n, x, y, WHITE, int(alf*0.05*(12-gi)))
        text_ov("NOW.", f_n, x, y, WHITE, alf, shadow_col=NEON_BLUE)

    if t >= 1.0:
        pe, alf = sa(1.0)
        f_c = fnt(F_MED, 80)
        d   = ImageDraw.Draw(Image.new("RGB",(1,1)))
        tw, _ = tsz(d, "I have your", f_c)
        text_ov("I have your", f_c, CX-tw//2, 570+int(40*(1-pe)), WHITE, alf)

    if t >= 1.6:
        sc  = ease_elastic(clamp((t-1.6)/0.65))
        alf = int(255*clamp((t-1.6)/0.18))
        if t > 5.5: sc = 1.0 + 0.016*math.sin((t-5.5)*math.pi*1.7)
        f_a = fnt(F_BOLD, max(50, int(128*sc)))
        d   = ImageDraw.Draw(Image.new("RGB",(1,1)))
        tw, th = tsz(d, "ATTENTION.", f_a)
        x = CX-tw//2;  y = 710 - int((th-200)*0.5)
        for gi in (12, 8, 4):
            ov2 = Image.new("RGBA",(W,H),(0,0,0,0))
            ImageDraw.Draw(ov2).text((x, y), "ATTENTION.", font=f_a,
                                     fill=YELLOW+(int(alf*0.06*(14-gi)),))
            img.alpha_composite(ov2)
        text_ov("ATTENTION.", f_a, x, y, YELLOW, alf, shadow_col=(180, 130, 0))

    if t >= 2.2:
        pe  = ease_out(clamp((t-2.2)/0.45))
        lw  = int((W-160)*pe)
        ov3 = Image.new("RGBA",(W,H),(0,0,0,0))
        ImageDraw.Draw(ov3).line([(CX-lw//2,1070),(CX+lw//2,1070)],
                                  fill=YELLOW+(int(180*pe),), width=4)
        img.alpha_composite(ov3)

    if t >= 2.3:
        pe, alf = sa(2.3, 0.45)
        f_s = fnt(F_BOLD, 110)
        d   = ImageDraw.Draw(Image.new("RGB",(1,1)))
        tw, _ = tsz(d, "60 seconds.", f_s)
        text_ov("60 seconds.", f_s, CX-tw//2, 1105+int(32*(1-pe)), WHITE, alf)

    if t >= 2.85:
        pe, alf = sa(2.85, 0.45)
        f_ow = fnt(F_MED, 90)
        d    = ImageDraw.Draw(Image.new("RGB",(1,1)))
        tw, _ = tsz(d, "One word.", f_ow)
        text_ov("One word.", f_ow, CX-tw//2, 1248+int(28*(1-pe)), WHITE, alf)

    if t >= 3.5:
        pe   = ease_out(clamp((t-3.5)/0.65))
        alf  = int(255*pe)
        if t > 4.2: alf = int(alf*(0.85+0.15*math.sin((t-4.2)*math.pi*2.4)))
        f_q  = fnt(F_BOLD, 86)
        txt  = "Can you handle it?"
        d    = ImageDraw.Draw(Image.new("RGB",(1,1)))
        tw, _ = tsz(d, txt, f_q)
        text_ov(txt, f_q, CX-tw//2, 1395, CORAL, alf, shadow_col=(180, 40, 20))

    return fade_frame(img.convert("RGB"), f, total_frames, fi=12, fo=18)


# ══════════════════════════════════════════════════════════════════════════════
#  SCREEN 2  —  WORD REVEAL
#
#  FIX 1: Gradient underline y moved down (word_y + wh + 65 instead of +14)
#  FIX 2: "Your 60-second challenge starts now." auto-sized to fit W-120
# ══════════════════════════════════════════════════════════════════════════════
def make_screen2_frame(word, pos, defn, f, total_frames):
    t   = f / FPS
    img = dark_bg().convert("RGBA")
    draw_particles(img, f)

    _d  = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    MW  = W - 140

    f_word, ww, wh = auto_fnt(_d, word.upper(), F_BOLD, W-90, start=190, step=6)
    word_y = 318
    f_defn  = fnt(F_LIGHT, 62)
    def_lines = wrap_lines(_d, defn or "", f_defn, MW)

    SLIDE = 75

    def sa(start, spd=0.50):
        pe  = ease_out(clamp((t-start)/spd))
        alf = int(255*clamp((t-start)/(spd*0.4)))
        return pe, alf

    # ── "TODAY'S WORD" label
    if t >= 0.2:
        pe, alf = sa(0.2, 0.5)
        f_l = fnt(F_MED, 52)
        ov  = Image.new("RGBA",(W,H),(0,0,0,0))
        od  = ImageDraw.Draw(ov)
        lw, _ = tsz(od,"TODAY'S WORD",f_l)
        od.text(((W-lw)//2, 230+int(SLIDE*(1-pe))), "TODAY'S WORD",
                font=f_l, fill=(165,195,240,alf))
        img.alpha_composite(ov)

    # ── Main word — elastic bounce
    if t >= 0.9:
        sc  = ease_elastic(clamp((t-0.9)/0.70))
        alf = int(255*clamp((t-0.9)/0.18))
        if t > 6.0: sc = 1.0 + 0.013*math.sin((t-6.0)*math.pi*1.8)
        fa, aw, ah = auto_fnt(_d, word.upper(), F_BOLD,
                               int((W-90)/max(0.5, sc)), start=190, step=6)
        x = (W-aw)//2;  y = word_y - int((ah-wh)*0.5)
        ov = Image.new("RGBA",(W,H),(0,0,0,0))
        od = ImageDraw.Draw(ov)
        od.text((x+8, y+8), word.upper(), font=fa, fill=NAVY+(int(alf*0.55),))
        od.text((x+3, y+4), word.upper(), font=fa, fill=YELLOW+(int(alf*0.22),))
        od.text((x,   y  ), word.upper(), font=fa, fill=WHITE+(alf,))
        img.alpha_composite(ov)

    # ── FIX 1: Gradient underline — moved DOWN (+36 gap instead of +14)
    if t >= 1.55:
        prog    = ease_out(clamp((t-1.55)/0.55))
        ul_half = int((ww//2 + 25) * prog)
        # ▼ CHANGED: +36 px gap below word (was +14)
        ul_y    = word_y + wh + 65
        ul_cx   = W // 2
        if ul_half > 12:
            ov_ul = Image.new("RGBA",(W,H),(0,0,0,0))
            od_ul = ImageDraw.Draw(ov_ul)
            segs  = 50
            sw    = max(1, ul_half*2 // segs)
            for i in range(segs):
                tc    = i / max(1, segs-1)
                col   = lerp_color(YELLOW, NEON_BLUE, tc)
                x0    = ul_cx - ul_half + i*sw
                od_ul.rectangle([x0, ul_y, x0+sw+1, ul_y+8], fill=col+(215,))
            img.alpha_composite(ov_ul)

    # ── POS badge
    if t >= 2.0 and pos:
        pe, alf = sa(2.0)
        f_p = fnt(F_MED, 52)
        ov  = Image.new("RGBA",(W,H),(0,0,0,0))
        od  = ImageDraw.Draw(ov)
        pw, ph = tsz(od, pos.upper(), f_p)
        px0 = W//2-pw//2-36;  py0 = 590+int(26*(1-pe))
        px1 = W//2+pw//2+36;  py1 = py0+ph+28
        for gi in range(4, 0, -1):
            rrect(od,[px0-gi*2, py0-gi*2, px1+gi*2, py1+gi*2],
                  min(40,(py1-py0+gi*4)//2), NEON_BLUE+(int(alf*0.09*(5-gi)),))
        rrect(od,[px0,py0,px1,py1], min(38,(py1-py0)//2),
              NEON_BLUE+(alf,), outline=(180,235,255,alf), width=3)
        od.text((W//2-pw//2, py0+7), pos.upper(), font=f_p, fill=NAVY+(alf,))
        img.alpha_composite(ov)

    # ── Divider
    if t >= 2.6:
        pe  = ease_out(clamp((t-2.6)/0.45))
        lw  = int((W-190)*pe)
        ov  = Image.new("RGBA",(W,H),(0,0,0,0))
        ImageDraw.Draw(ov).line([(W//2-lw//2,695),(W//2+lw//2,695)],
                                 fill=WHITE+(int(120*pe),), width=2)
        img.alpha_composite(ov)

    # ── Frosted glass card
    if t >= 2.9:
        pe, alf = sa(2.9, 0.5)
        lh_total = len(def_lines) * (68 + 16)
        card_top = 710
        card_bot = card_top + 66 + lh_total + 54
        ov_card  = Image.new("RGBA",(W,H),(0,0,0,0))
        rrect(ImageDraw.Draw(ov_card),
              [55, card_top, W-55, card_bot], 34,
              (255,255,255,int(28*pe)), outline=(255,255,255,int(45*pe)), width=1)
        img.alpha_composite(ov_card)

    # ── "DEFINITION" label
    if t >= 3.0:
        pe, alf = sa(3.0, 0.5)
        f_dl = fnt(F_MED, 50)
        ov   = Image.new("RGBA",(W,H),(0,0,0,0))
        od   = ImageDraw.Draw(ov)
        dlw, _ = tsz(od,"DEFINITION",f_dl)
        od.text(((W-dlw)//2, 728+int(16*(1-pe))), "DEFINITION",
                font=f_dl, fill=(165,195,240,alf))
        img.alpha_composite(ov)

    # ── Definition text
    if t >= 3.5:
        pe, alf = sa(3.5, 0.75)
        ov = Image.new("RGBA",(W,H),(0,0,0,0))
        od = ImageDraw.Draw(ov)
        yy = 798 + int(26*(1-pe))
        for line, lw2, lh in def_lines:
            od.text(((W-lw2)//2, yy), line, font=f_defn, fill=WHITE+(alf,))
            yy += lh + 16
        img.alpha_composite(ov)

    # ── FIX 2: Bottom CTA — auto-sized font so it NEVER overflows
    if t >= 5.5:
        pe    = ease_out(clamp((t-5.5)/0.9))
        pulse = 0.72 + 0.28*math.sin(max(0,t-6.0)*math.pi*2.1)
        alf   = int(240*pe*pulse)
        txt   = "Your 60-second challenge starts now..."
        # ▼ CHANGED: auto_fnt with max_w=W-120 (was hard-coded fnt size 60)
        _tmp_draw = ImageDraw.Draw(Image.new("RGB",(1,1)))
        f_cta, tw, th = auto_fnt(_tmp_draw, txt, F_BOLD, W-120,
                                  start=64, step=4, min_sz=36)
        ov    = Image.new("RGBA",(W,H),(0,0,0,0))
        od    = ImageDraw.Draw(ov)
        od.text(((W-tw)//2, 1330), txt, font=f_cta, fill=YELLOW+(alf,))
        img.alpha_composite(ov)

    return fade_frame(img.convert("RGB"), f, total_frames, fi=10, fo=18)


# ══════════════════════════════════════════════════════════════════════════════
#  SCREEN 3  —  COUNTDOWN  3 → 2 → 1
# ══════════════════════════════════════════════════════════════════════════════
def make_screen3_frame(n, t_beat, total_frames, f_abs):
    img  = dark_bg().convert("RGBA")
    draw_particles(img, f_abs)
    img  = img.convert("RGB")
    draw = ImageDraw.Draw(img)

    f_lbl = fnt(F_MED, 66)
    lbl   = "Timer starts in"
    lw, _ = tsz(draw, lbl, f_lbl)
    draw.text(((W-lw)//2, 215), lbl, font=f_lbl, fill=(165, 195, 240))

    CX = W//2;  CY = H//2 + 50
    bt = clamp(t_beat/0.25)
    if bt < 0.25:   scale = 0.50 + 0.65*ease_out(bt/0.25)
    elif bt < 0.50: scale = 1.15 - 0.15*ease_in_out((bt-0.25)/0.25)
    else:           scale = 1.0  + 0.020*math.sin(t_beat*math.pi*3.5)

    r      = int(310*scale)
    col_t  = 1.0 - (n-1)/2.0
    c_ring = lerp_color((50,130,220),(210,55,55), col_t)
    c_fill = lerp_color((20, 68,165),(145,22,22), col_t)

    img_r = img.convert("RGBA")
    for gi in range(7, 0, -1):
        gr  = r + gi*22
        ov  = Image.new("RGBA",(W,H),(0,0,0,0))
        ImageDraw.Draw(ov).ellipse([CX-gr,CY-gr,CX+gr,CY+gr],
                                   fill=c_ring+(max(0, 50-gi*6),))
        img_r.alpha_composite(ov)

    ov2 = Image.new("RGBA",(W,H),(0,0,0,0))
    od2 = ImageDraw.Draw(ov2)
    od2.ellipse([CX-r,CY-r,CX+r,CY+r], fill=c_fill+(225,),
                outline=c_ring+(255,), width=18)
    ri = int(r*0.82)
    od2.arc([CX-ri,CY-ri,CX+ri,CY+ri], start=-150, end=-30,
            fill=(255,255,255,55), width=10)
    img_r.alpha_composite(ov2)

    f_num = fnt(F_BOLD, max(30, int(370*scale)))
    num   = str(n)
    ov3   = Image.new("RGBA",(W,H),(0,0,0,0))
    od3   = ImageDraw.Draw(ov3)
    nw,nh = tsz(od3, num, f_num)
    od3.text((CX-nw//2+9, CY-nh//2-int(55*scale)+9), num, font=f_num,
             fill=(0,0,0,100))
    od3.text((CX-nw//2,   CY-nh//2-int(55*scale)),   num, font=f_num,
             fill=WHITE+(235,))
    img_r.alpha_composite(ov3)

    if n == 1 and t_beat > 0.5:
        alf2  = int(220*ease_out(clamp((t_beat-0.5)/0.65)))
        f_kt  = fnt(F_BOLD, 72)
        kt    = "Keep talking. Don't stop."
        ov4   = Image.new("RGBA",(W,H),(0,0,0,0))
        od4   = ImageDraw.Draw(ov4)
        kw, _ = tsz(od4, kt, f_kt)
        od4.text(((W-kw)//2, 1618), kt, font=f_kt,
                 fill=YELLOW+(alf2,))
        img_r.alpha_composite(ov4)

    return fade_frame(img_r.convert("RGB"), f_abs, total_frames, fi=10, fo=12)


# ══════════════════════════════════════════════════════════════════════════════
#  SCREEN 4  —  60-SECOND GAMIFIED TIMER
#
#  FIX 3: "HALFWAY! KEEP GOING!" banner auto-sized — never clips edges
#  UI IMPROVEMENTS:
#   • Cleaner zone-A card with subtle top accent stripe
#   • Rank badge uses pill-shaped glow with icon prefix
#   • Timer circle: thicker arc, cleaner tick marks at 15/30/45s
#   • Zone-C: labelled progress bar with "TIME LEFT" tag
#   • Smoother colour transitions throughout
# ══════════════════════════════════════════════════════════════════════════════
def make_screen4_frame(word, secs_left, halfway_flash=0.0, prompt_idx=0):
    secs_left = max(0.0, secs_left)
    elapsed   = 60.0 - secs_left

    tc = 0.0
    if secs_left < 30: tc = clamp(0.5*(30-secs_left)/20)
    if secs_left < 10: tc = clamp(0.5 + 0.5*(10-secs_left)/10)
    img  = s4_bg(tc)

    amp = max(0, int(4 + 8*(10-secs_left)/10)) if secs_left < 10 else 0
    sx  = random.randint(-amp, amp) if amp else 0
    sy  = random.randint(-amp, amp) if amp else 0

    # ═══════════════════════════════════════════════════════════════════════
    # ZONE A  — Word card (y: 48→452)
    # ═══════════════════════════════════════════════════════════════════════
    ov_za = Image.new("RGBA",(W,H),(0,0,0,0))
    od_za = ImageDraw.Draw(ov_za)

    # Card background with subtle border glow
    card_col = (12, 18, 55, 105) if secs_left > 30 else \
               (55, 22, 8, 105)  if secs_left > 10 else \
               (70, 8, 8, 110)
    rrect(od_za, [30+sx, 48+sy, W-30+sx, 452+sy], 36, card_col,
          outline=(255,255,255,22), width=1)

    # Accent stripe at top of card (colour-coded by urgency)
    stripe_col = lerp_color(NEON_BLUE, CORAL, clamp(1.0-secs_left/60.0))
    rrect(od_za, [30+sx, 48+sy, W-30+sx, 60+sy], 36,
          stripe_col + (180,))
    rrect(od_za, [30+sx, 56+sy, W-30+sx, 60+sy], 0,
          stripe_col + (180,))
    img = composite(img, ov_za)
    draw = ImageDraw.Draw(img)

    # "TODAY'S WORD" label
    f_wlbl = fnt(F_MED, 54)
    lbl    = "TODAY'S WORD"
    lw, _  = tsz(draw, lbl, f_wlbl)
    draw.text(((W-lw)//2+sx, 78+sy), lbl, font=f_wlbl, fill=(165,210,255))

    # The word — glow shadow + blink on milestones
    f_w, ww, wh = auto_fnt(draw, word.upper(), F_BOLD, W-80, start=130, step=6)
    is_blink = any(abs(secs_left-b) < 0.50 for b in (10,20,30,40,50))
    word_col = YELLOW if is_blink else WHITE

    ov_wg = Image.new("RGBA",(W,H),(0,0,0,0))
    od_wg = ImageDraw.Draw(ov_wg)
    glow_col = YELLOW if is_blink else NEON_BLUE
    for gi in (8, 5, 3):
        od_wg.text(((W-ww)//2+sx+gi, 158+sy+gi), word.upper(),
                   font=f_w, fill=glow_col+(int(30*(9-gi)),))
    od_wg.text(((W-ww)//2+sx, 158+sy), word.upper(), font=f_w, fill=word_col+(255,))
    img = composite(img, ov_wg)
    draw = ImageDraw.Draw(img)

    # Rank badge — cleaner pill with icon prefix
    if secs_left < 15:   rank, rc, icon = "MASTER",    NEON_GREEN, "★"
    elif secs_left < 30: rank, rc, icon = "PRO",        YELLOW,     "◆"
    elif secs_left < 45: rank, rc, icon = "APPRENTICE", NEON_BLUE,  "▲"
    else:                rank, rc, icon = "NOVICE",     (190,198,215), "●"

    f_rk  = fnt(F_BOLD, 46)
    f_ico = fnt(F_BOLD, 42)
    ov_rk = Image.new("RGBA",(W,H),(0,0,0,0))
    od_rk = ImageDraw.Draw(ov_rk)
    rtxt  = f"{icon}  {rank}"
    rw, rh = tsz(od_rk, rtxt, f_rk)
    rx0 = W//2-rw//2-36+sx;  ry0 = 358+sy
    rx1 = W//2+rw//2+36+sx;  ry1 = ry0+rh+22
    # outer glow halo
    for gi in range(4,0,-1):
        rrect(od_rk, [rx0-gi*3,ry0-gi*3,rx1+gi*3,ry1+gi*3],
              min(40,(ry1-ry0+gi*6)//2), rc+(int(30*(5-gi)),))
    rrect(od_rk, [rx0,ry0,rx1,ry1], min(38,(ry1-ry0)//2),
          rc+(255,), outline=(255,255,255,90), width=2)
    od_rk.text((W//2-rw//2+sx, ry0+11), rtxt, font=f_rk, fill=NAVY+(255,))
    img = composite(img, ov_rk)
    draw = ImageDraw.Draw(img)

    # ═══════════════════════════════════════════════════════════════════════
    # ZONE B  — Timer circle (cx=540, cy=910, r=310)
    # ═══════════════════════════════════════════════════════════════════════
    CX = W//2+sx;  CY = 910+sy;  CR = 310

    pulse_spd = 5.5 if secs_left <= 10 else 1.3
    pulse_amp = 0.034 if secs_left <= 10 else 0.012
    r = int(CR*(1.0 + pulse_amp*math.sin(elapsed*math.pi*pulse_spd)))

    if secs_left > 30:
        c_fill=(24,80,170);   c_ring=(10,48,120);   arc_c=(255,255,255,220)
    elif secs_left > 10:
        tt     = (30-secs_left)/20.0
        c_fill = lerp_color((24,80,170),(165,80,14),tt)
        c_ring = lerp_color((10,48,120),(112,48,6),tt)
        arc_c  = (255,int(lerp(255,130,tt)),int(lerp(255,20,tt)),220)
    else:
        tt     = (10-secs_left)/10.0
        c_fill = lerp_color((165,80,14),(175,18,18),tt)
        c_ring = lerp_color((112,48,6), (115,8,8),tt)
        arc_c  = (255,int(lerp(130,35,tt)),int(lerp(20,20,tt)),220)

    # Outer shadow ring for depth
    ov_sh = Image.new("RGBA",(W,H),(0,0,0,0))
    ImageDraw.Draw(ov_sh).ellipse([CX-r-12,CY-r-12,CX+r+12,CY+r+12],
                                   fill=(0,0,0,60))
    img = composite(img, ov_sh)
    draw = ImageDraw.Draw(img)

    draw.ellipse([CX-r,CY-r,CX+r,CY+r], fill=c_fill, outline=c_ring, width=24)

    # Inner highlight ring
    ri = int(r*0.80)
    ov_ih = Image.new("RGBA",(W,H),(0,0,0,0))
    ImageDraw.Draw(ov_ih).arc([CX-ri,CY-ri,CX+ri,CY+ri],
                               start=-140, end=-40, fill=(255,255,255,55), width=14)
    img = composite(img, ov_ih)

    # Tick marks at 15 / 30 / 45 second positions
    ov_tk = Image.new("RGBA",(W,H),(0,0,0,0))
    od_tk = ImageDraw.Draw(ov_tk)
    for tick_s in (15, 30, 45):
        tick_a = math.radians(-90 + 360*tick_s/60.0)
        for dist, col, width in [(r-2, (0,0,0,80), 6), (r-2, (255,255,255,90), 4)]:
            tx0 = int(CX + (dist-14)*math.cos(tick_a))
            ty0 = int(CY + (dist-14)*math.sin(tick_a))
            tx1 = int(CX + (dist+14)*math.cos(tick_a))
            ty1 = int(CY + (dist+14)*math.sin(tick_a))
            od_tk.line([(tx0,ty0),(tx1,ty1)], fill=col, width=width)
    img = composite(img, ov_tk)
    draw = ImageDraw.Draw(img)

    # Arc sweep
    sweep = int(360*secs_left/60.0)
    if sweep > 0:
        ov_a = Image.new("RGBA",(W,H),(0,0,0,0))
        od_a = ImageDraw.Draw(ov_a)
        od_a.arc([CX-r,CY-r,CX+r,CY+r], start=-90, end=-90+sweep,
                 fill=arc_c, width=36)
        # leading dot
        angle = math.radians(-90 + sweep)
        dot_x = int(CX + r * math.cos(angle))
        dot_y = int(CY + r * math.sin(angle))
        od_a.ellipse([dot_x-20,dot_y-20,dot_x+20,dot_y+20], fill=WHITE+(arc_c[3],))
        img  = composite(img, ov_a)
        draw = ImageDraw.Draw(img)

    # Digits
    f_dig = fnt(F_BOLD, 314 if secs_left >= 10 else 352)
    num   = str(max(0, int(math.ceil(secs_left))))
    nw, nh = tsz(draw, num, f_dig)
    draw.text((CX-nw//2+10, CY-nh//2-58+10), num, font=f_dig, fill=(0,0,0,85))
    draw.text((CX-nw//2,    CY-nh//2-58),    num, font=f_dig,
              fill=WHITE if secs_left <= 10 else (232,244,255))

    # ── FIX 3: Halfway banner — auto_fnt so it NEVER clips edges ─────────
    if halfway_flash > 0.0:
        alf      = int(240*halfway_flash)
        txt_half = "HALFWAY!  KEEP GOING!"
        _tmp_d   = ImageDraw.Draw(Image.new("RGB",(1,1)))
        # ▼ CHANGED: auto_fnt with max_w=W-80 (was hard-coded fnt 94)
        f_hf, hw, hh = auto_fnt(_tmp_d, txt_half, F_BOLD, W-80,
                                 start=94, step=4, min_sz=48)
        pad  = 32
        yh   = CY - r - 155
        ov_h = Image.new("RGBA",(W,H),(0,0,0,0))
        od_h = ImageDraw.Draw(ov_h)
        # badge background
        rrect(od_h, [W//2-hw//2-pad+sx, yh-pad//2+sy,
                     W//2+hw//2+pad+sx, yh+hh+pad+sy],
              36, YELLOW+(alf,), outline=(255,255,255,int(alf*0.6)), width=3)
        od_h.text((W//2-hw//2+sx, yh+sy), txt_half,
                  font=f_hf, fill=NAVY+(alf,))
        img = composite(img, ov_h)
        draw = ImageDraw.Draw(img)

    # ═══════════════════════════════════════════════════════════════════════
    # ZONE C  — Prompt + progress bar card (y: 1255→1600)
    # ═══════════════════════════════════════════════════════════════════════
    ov_zc = Image.new("RGBA",(W,H),(0,0,0,0))
    od_zc = ImageDraw.Draw(ov_zc)
    rrect(od_zc, [35+sx, 1240+sy, W-35+sx, 1630+sy], 36,
          (0,0,0,90), outline=(255,255,255,18), width=1)
    img = composite(img, ov_zc)
    draw = ImageDraw.Draw(img)

    # Rotating prompt
    prompt = PROMPTS[prompt_idx % len(PROMPTS)]
    f_pr   = fnt(F_LIGHT, 50)
    t_win  = elapsed % 12.0
    if t_win < 1.2:    p_alf = int(195*ease_in_out(t_win/1.2))
    elif t_win > 10.8: p_alf = int(195*ease_in_out(1.0-(t_win-10.8)/1.2))
    else:              p_alf = 195

    ov_pr  = Image.new("RGBA",(W,H),(0,0,0,0))
    od_pr  = ImageDraw.Draw(ov_pr)
    plines = wrap_lines(od_pr, prompt, f_pr, W-130)
    yp     = 1258+sy
    for line, plw, plh in plines:
        od_pr.text(((W-plw)//2+sx, yp), line, font=f_pr,
                   fill=(195,225,255,p_alf))
        yp += plh + 10
    img  = composite(img, ov_pr)
    draw = ImageDraw.Draw(img)

    # CTA
    f_cmt = fnt(F_MED, 52)
    cmt   = "Comment your attempt below! \U0001f447"
    cw, _ = tsz(draw, cmt, f_cmt)
    draw.text(((W-cw)//2+sx, 1420+sy), cmt, font=f_cmt, fill=WHITE)

    # "TIME LEFT" label above progress bar
    f_bar_lbl = fnt(F_MED, 40)
    bar_lbl   = "TIME LEFT"
    blw, _    = tsz(draw, bar_lbl, f_bar_lbl)
    draw.text((90+sx, 1545+sy), bar_lbl, font=f_bar_lbl, fill=(165,200,255,160))

    # Percentage label
    pct_txt  = f"{int(secs_left)}s"
    f_pct    = fnt(F_BOLD, 40)
    ptw, _   = tsz(draw, pct_txt, f_pct)
    draw.text((W-90-ptw+sx, 1545+sy), pct_txt, font=f_pct, fill=(165,200,255,160))

    # Gradient progress bar
    bx1 = 80+sx;  bx2 = W-80+sx;  by = 1578+sy;  bh = 26
    rrect(draw, [bx1,by,bx2,by+bh], 13, (20,25,60))
    fw = int((bx2-bx1)*secs_left/60.0)
    if fw > 26:
        tc_bar = 1.0 - secs_left/60.0
        bc = lerp_color((75,175,255),(255,50,50), tc_bar)
        rrect(draw, [bx1,by,bx1+fw,by+bh], 13, bc)
        # pulsing leading edge
        pulse_bar = 0.65 + 0.35*math.sin(elapsed*math.pi*3.0)
        ov_pb = Image.new("RGBA",(W,H),(0,0,0,0))
        ImageDraw.Draw(ov_pb).ellipse(
            [bx1+fw-18, by-9, bx1+fw+18, by+bh+9],
            fill=WHITE+(int(185*pulse_bar),))
        img = composite(img, ov_pb)
        draw = ImageDraw.Draw(img)

    # End-card fade (last 3 s)
    if secs_left <= 3.0:
        t_end = ease_in_out(1.0-secs_left/3.0)
        alf   = int(228*t_end)
        f_end = fnt(F_BOLD, 86)
        line  = "Follow for tomorrow's word! \U0001f514"
        ov_e  = Image.new("RGBA",(W,H),(0,0,0,0))
        od_e  = ImageDraw.Draw(ov_e)
        od_e.rectangle([0,0,W,H], fill=(0,0,0,alf))
        ew, eh = tsz(od_e, line, f_end)
        od_e.text(((W-ew)//2, (H-eh)//2), line, font=f_end, fill=WHITE+(alf,))
        img = composite(img, ov_e)

    return img


# ══════════════════════════════════════════════════════════════════════════════
#  GEMINI WORD DEFINITION
# ══════════════════════════════════════════════════════════════════════════════
class GeminiRateLimitError(Exception):
    pass


def get_word_info_from_gemini(word):
    import re

    prompt = (
        f"Give me information about the English word: '{word}'.\n\n"
        "I need this for a viral Instagram language-learning reel.\n\n"
        "Respond ONLY with this exact JSON on ONE line — "
        "no markdown, no backticks, no explanation, nothing else:\n"
        '{"pos":"PART_OF_SPEECH","definition":"YOUR_DEFINITION"}\n\n'
        "Rules:\n"
        '- "pos": exactly one of: noun / verb / adjective / adverb\n'
        '- "definition": exactly 10-14 words. Factually accurate above all else — vivid and clear.\n'
        "  Must reflect the true, dictionary-accurate meaning. No exaggeration or poetic license.\n"
        "  Do NOT start with the word. No example sentence. No pronunciation.\n"
        "  IMPORTANT: the definition must be a complete sentence ending with a period.\n\n"
        "Good example for 'resilient':\n"
        '{"pos":"adjective","definition":"Bouncing back stronger every time life knocks you down."}\n\n'
        "Good example for 'articulate':\n"
        '{"pos":"adjective","definition":"Expressing ideas with impressive clarity and natural fluency."}'
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.20, "maxOutputTokens": 1024}
    }

    r = requests.post(GEMINI_URL, json=payload, timeout=15)

    if r.status_code == 429:
        raise GeminiRateLimitError(f"Rate limited (429) — switching to Dictionary API.")
    if r.status_code != 200:
        raise Exception(f"Gemini HTTP {r.status_code}: {r.text[:150]}")

    raw = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    print(f"    [Gemini] Raw response: {raw}")

    raw_clean = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
    data = None

    try:
        data = json.loads(raw_clean)
    except json.JSONDecodeError:
        pass

    if data is None:
        m = re.search(r'\{[^{}]+\}', raw_clean, re.DOTALL)
        if m:
            try: data = json.loads(m.group())
            except json.JSONDecodeError: pass

    if data is None:
        pm = re.search(r'"pos"\s*:\s*"([^"]+)"',        raw_clean)
        dm = re.search(r'"definition"\s*:\s*"([^"]*)"', raw_clean)
        if pm and dm and dm.group(1).strip():
            data = {"pos": pm.group(1), "definition": dm.group(1)}

    if data is None:
        raise Exception(f"Could not parse Gemini response: {raw_clean[:120]}")

    pos  = data.get("pos", "").lower().strip()
    defn = data.get("definition", "").strip()

    pos_map = {
        "noun": "noun", "verb": "verb",
        "adjective": "adjective", "adj": "adjective",
        "adverb": "adverb", "adv": "adverb",
    }
    pos = pos_map.get(pos, pos)

    if not pos or pos not in ("noun", "verb", "adjective", "adverb"):
        raise Exception(f"Unrecognised part of speech: '{pos}'")
    if not defn or len(defn.split()) < 6:
        raise Exception(f"Definition too short or empty: '{defn}'")

    return pos, defn


# ══════════════════════════════════════════════════════════════════════════════
#  WORD FETCH
# ══════════════════════════════════════════════════════════════════════════════
_OBSCURE_SUFFIXES = ("idae", "inae", "osis", "itis", "emia",
                     "ectomy", "plasty", "ology")
_OBSCURE_WORDS    = {
    "quoll","quolls","potoroo","bettong","bandicoot","numbat",
    "quokka","bilby","dasyure","dingo","wallaby","wallaroo",
    "dasyurus","dasypus","aalii","abaci","abaft","abeam","abele",
    "absit","acned","acnes",
}

def _is_reel_suitable(word):
    w = word.lower().strip()
    if len(w) < 5 or len(w) > 13:                      return False
    if not w.isalpha():                                 return False
    if w in _OBSCURE_WORDS:                             return False
    if any(w.endswith(s) for s in _OBSCURE_SUFFIXES):  return False
    return True

def _good_defn(d):
    return bool(d and len(d.split()) >= 6)

def _dict_api_lookup(word):
    r = requests.get(
        f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}",
        timeout=6
    )
    if r.status_code != 200:
        raise Exception(f"Dictionary API HTTP {r.status_code} for '{word}'")

    for pref in ("adjective", "verb", "adverb", "noun"):
        for m in r.json()[0].get("meanings", []):
            if m["partOfSpeech"] == pref:
                d = m["definitions"][0]["definition"]
                if _good_defn(d):
                    return pref, d

    raise Exception(f"No usable definition found in Dictionary API for '{word}'")


def get_word():
    if GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        print("\n  ⚠️  GEMINI_API_KEY is not set — using hardcoded fallback.\n")
        return random.choice(FALLBACKS)

    gemini_disabled = False

    for attempt in range(20):
        try:
            print(f"\n  [Word]  Fetching random word... (attempt {attempt+1})")
            r = requests.get(
                "https://random-word-api.herokuapp.com/word?number=1", timeout=5
            )
            if r.status_code != 200:
                print(f"  [Word]  ⚠️  Random Word API HTTP {r.status_code} — retrying...")
                continue

            word = r.json()[0].lower().strip()

            if not _is_reel_suitable(word):
                print(f"  [Word]  '{word}' skipped (too short / long / obscure) — retrying...")
                continue

            print(f"  [Word]  ✓  Got word: '{word.upper()}'")

            if not gemini_disabled:
                print(f"  [Gemini] Trying Gemini for '{word}'...")
                try:
                    pos, defn = get_word_info_from_gemini(word)
                    print(f"  [Gemini] ✓  pos={pos}")
                    print(f"  [Gemini] ✓  definition={defn}")
                    print(f"  [Source] Definition from: Gemini ✓")
                    return word, pos, defn
                except GeminiRateLimitError as e:
                    print(f"  [Gemini] ✗  {e}")
                    print(f"  [Gemini] ⚠️  Rate limit hit — disabling Gemini for this run.")
                    gemini_disabled = True
                except Exception as gemini_err:
                    print(f"  [Gemini] ✗  Failed: {gemini_err}")
                    print(f"  [Gemini]    Trying Dictionary API for same word '{word}'...")
            else:
                print(f"  [Gemini] Skipped (rate-limited) — using Dictionary API directly.")

            print(f"  [DictAPI] Looking up '{word}'...")
            try:
                pos, defn = _dict_api_lookup(word)
                print(f"  [DictAPI] ✓  pos={pos}")
                print(f"  [DictAPI] ✓  definition={defn[:80]}...")
                print(f"  [Source]  Definition from: Dictionary API ✓")
                return word, pos, defn
            except Exception as dict_err:
                print(f"  [DictAPI] ✗  {dict_err} — skipping word, trying new one.")
                continue

        except Exception as e:
            print(f"  [Word]  ✗  Unexpected error on attempt {attempt+1}: {e} — retrying...")
            continue

    fb = random.choice(FALLBACKS)
    print(f"\n  ⚠️  All 20 attempts exhausted.")
    print(f"  ⚠️  Using hardcoded fallback word: '{fb[0].upper()}'")
    return fb


# ══════════════════════════════════════════════════════════════════════════════
#  HOOK VIDEO
# ══════════════════════════════════════════════════════════════════════════════
def get_random_hook():
    if not os.path.isdir(HOOKS_DIR):
        print("  hooks/ folder not found — skipping hook prepend.")
        return None
    videos = [
        f for f in os.listdir(HOOKS_DIR)
        if f.lower().endswith((".mp4", ".mov", ".avi", ".mkv", ".m4v"))
    ]
    if not videos:
        print("  hooks/ folder is empty — skipping hook prepend.")
        return None
    chosen = random.choice(videos)
    print(f"  Hook selected: {chosen}")
    return os.path.join(HOOKS_DIR, chosen)


def prepend_hook(hook_path, reel_path, output_path):
    if not hook_path or not os.path.exists(hook_path):
        subprocess.run(["ffmpeg","-y","-i",reel_path,"-c","copy",output_path],
                       capture_output=True, timeout=120)
        return

    hook_norm = os.path.join(_TMP, "hook_normalised.mp4")

    norm_result = subprocess.run([
        "ffmpeg", "-y", "-i", hook_path,
        "-vf",
            f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,"
            f"setsar=1,fps={FPS}",
        "-af",
            f"aresample={SAMPLE_RATE},"
            f"aformat=sample_fmts=fltp:channel_layouts=stereo",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        hook_norm
    ], capture_output=True, timeout=180)

    if norm_result.returncode != 0 or not os.path.exists(hook_norm):
        print("  Warning: hook normalisation failed — using reel only.")
        subprocess.run(["ffmpeg","-y","-i",reel_path,"-c","copy",output_path],
                       capture_output=True, timeout=120)
        return

    concat_txt = os.path.join(_TMP, "concat_list.txt")
    with open(concat_txt, "w") as fh:
        fh.write(f"file '{hook_norm}'\n")
        fh.write(f"file '{reel_path}'\n")

    merge_result = subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", concat_txt,
        "-c:v", "libx264", "-preset", "fast", "-crf", "22", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ar", str(SAMPLE_RATE), "-ac", "2",
        "-movflags", "+faststart",
        output_path
    ], capture_output=True, timeout=300)

    if merge_result.returncode != 0:
        print("  Warning: hook concat failed — using reel only.")
        print(merge_result.stderr.decode()[:400])
        subprocess.run(["ffmpeg","-y","-i",reel_path,"-c","copy",output_path],
                       capture_output=True, timeout=120)
        return

    print(f"  Hook prepended successfully → {os.path.basename(output_path)}")

    for p in (hook_norm, concat_txt):
        try: os.remove(p)
        except: pass


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════
def main():
    skip_upload = "--no-upload" in sys.argv
    try:
        import telegram_notifier as tg; tg_ok = True
    except ImportError:
        tg_ok = False; print("  telegram_notifier not found — Telegram disabled.")

    print("=== Word Challenge Reel  [v8.2] ===")
    if tg_ok: tg.notify_start()

    voice, rate, pitch = random.choice(VOICE_POOL)
    print(f"  Voice  : {voice}  rate={rate}  pitch={pitch}")

    print("\n  Fetching word...")
    try:
        word, pos, defn = get_word()
    except Exception as e:
        if tg_ok: tg.notify_error("Word fetch", str(e)); raise
    print(f"  Word   : {word.upper()}  ({pos})")
    print(f"  Defn   : {defn[:90]}...")
    if tg_ok: tg.notify_word(word, pos, defn)

    s1_txt = (
        f"Now I have your attention, here's today's challenge — "
        f"sixty seconds, one word, think you can handle it?"
    )
    s2_txt = (
        f"Today's word is {word}, {word}, "
        f"a {pos}, "
        f"meaning — {defn} "
        f"Lock it in, your timer starts right now."
    )
    s3_txt = "Use this word, talk for sixty seconds straight, and don't stop. Three. Two. One!"
    s4_half_txt = "Halfway! Don't stop now!"

    print("\n  Generating TTS...")
    tts_dir = _TMP
    def tp(n): return os.path.join(tts_dir, f"tts_v8_{n}.wav")
    for label, txt, p in [
        ("[1/4] Intro",    s1_txt,      tp("s1")),
        ("[2/4] Reveal",   s2_txt,      tp("s2")),
        ("[3/4] Countdown",s3_txt,      tp("s3")),
        ("[4/4] Halfway",  s4_half_txt, tp("s4h")),
    ]:
        print(f"    {label}...")
        tts_gen(txt, p, voice, rate, pitch)

    s1_dur = max(S1_MIN, wav_dur(tp("s1")) + PAD_S1)
    s2_dur = max(S2_MIN, wav_dur(tp("s2")) + PAD_S2)
    s3_dur = max(S3_MIN, wav_dur(tp("s3")) + PAD_S3)
    s4_dur = S4_DUR
    t_s1 = 0.0
    t_s2 = t_s1 + s1_dur
    t_s3 = t_s2 + s2_dur
    t_s4 = t_s3 + s3_dur
    total = t_s4 + s4_dur
    print(
        f"\n  Timing: S1={s1_dur:.1f}s  S2={s2_dur:.1f}s  "
        f"S3={s3_dur:.1f}s  S4={s4_dur:.0f}s  Total={total:.1f}s"
    )

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(TMP_VIDEO, fourcc, FPS, (W, H))

    print("\n  Rendering Screen 1/4  (intro)...")
    s1f = int(s1_dur*FPS)
    for f in range(s1f):
        writer.write(pil2cv(make_screen1_frame(f, s1f)))

    print("  Rendering Screen 2/4  (word reveal)...")
    s2f = int(s2_dur*FPS)
    for f in range(s2f):
        writer.write(pil2cv(make_screen2_frame(word, pos, defn, f, s2f)))

    print("  Rendering Screen 3/4  (countdown)...")
    s3f = int(s3_dur*FPS);  bf = max(1, s3f//3)
    for f in range(s3f):
        n  = 3 - min(2, f//bf)
        tb = (f % bf) / FPS
        writer.write(pil2cv(make_screen3_frame(n, tb, s3f, f)))

    print("  Rendering Screen 4/4  (timer)...")
    s4f         = int(s4_dur*FPS)
    flash_start = int(30*FPS);  flash_len = int(2.0*FPS)
    for f in range(s4f):
        secs  = 60.0 - f/FPS
        hf    = (max(0.0, 1.0-(f-flash_start)/flash_len)
                 if flash_start <= f < flash_start+flash_len else 0.0)
        pidx  = int((f/FPS)//12)
        writer.write(pil2cv(make_screen4_frame(word, secs, hf, pidx)))

    writer.release()
    print("  Frames done.")

    print("\n  Building audio track...")
    build_audio_track([
        (t_s1,      tp("s1")),
        (t_s2,      tp("s2")),
        (t_s3,      tp("s3")),
        (t_s4+30.0, tp("s4h")),
    ], total)

    print("  Merging video + audio → reel...")
    subprocess.run([
        "ffmpeg", "-y",
        "-i", TMP_VIDEO, "-i", TMP_AUDIO,
        "-map","0:v","-map","1:a",
        "-c:v","libx264","-preset","fast","-crf","22","-pix_fmt","yuv420p",
        "-c:a","aac","-b:a","128k","-ar",str(SAMPLE_RATE),"-ac","2",
        "-shortest","-movflags","+faststart",
        REEL_RAW
    ], capture_output=True)

    print("\n  Selecting hook video...")
    hook_path = get_random_hook()
    print("  Prepending hook to reel...")
    prepend_hook(hook_path, REEL_RAW, OUTPUT)

    print(f"\n  Saved → {OUTPUT}")
    if tg_ok: tg.notify_render_done(OUTPUT)
    if tg_ok: tg.send_video(OUTPUT, caption=f"<b>{word.upper()}</b>  |  {voice}")

    caption = None
    try:
        from instagram_uploader import build_caption
        caption = build_caption(word, pos, defn)
    except Exception:
        pass

    if skip_upload:
        print("  Skipping upload (--no-upload).")
        if tg_ok: tg.notify_skipped("--no-upload flag.")
    else:
        print("\n  Uploading to Instagram...")
        if tg_ok: tg.notify_upload_start()
        try:
            from instagram_uploader import upload_reel
            pid = upload_reel(OUTPUT, word=word, pos=pos, defn=defn,
                              prebuilt_caption=caption)
            print(f"  LIVE!  Post ID: {pid}")
            if tg_ok: tg.notify_live(pid, word)
        except ImportError:
            print("  instagram_uploader.py not found — skipping.")
            if tg_ok: tg.notify_skipped("instagram_uploader not found.")
        except Exception as e:
            print(f"  Upload failed: {e}")
            if tg_ok: tg.notify_error("Upload", str(e))

    print("\n  Done!")


if __name__ == "__main__":
    main()