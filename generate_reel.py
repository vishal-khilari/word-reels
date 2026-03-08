"""
Instagram Word Challenge Reel Generator  +  Auto-Upload
  Screen 1 (4s)  : Image "Overcome_your_fear_of_speaking_in_just_60_seconds.png"
  Screen 2 (8s)  : Today's word + part of speech + definition
  Screen 3 (3s)  : Image "You_have_60_seconds_to_speak_using_this_word_Don't_stop_talking.png" + countdown 3→2→1 with beeps
  Screen 4 (60s) : Word reminder + 60-second circle timer

Run: python3 generate_reel.py
     python3 generate_reel.py --no-upload   ← skip Instagram upload

Requires: pip install opencv-python pillow numpy requests wonderwords
"""

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

# Image assets — expected in the same folder as this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IMG_SCREEN1 = os.path.join(SCRIPT_DIR, "Overcome_your_fear_of_speaking_in_just_60_seconds.png")
IMG_SCREEN3 = os.path.join(SCRIPT_DIR, "You_have_60_seconds_to_speak_using_this_word_Don't_stop_talking.png")

# Font paths — tries Google Fonts, falls back to DejaVu
_GF  = "/usr/share/fonts/truetype/google-fonts"
_DV  = "/usr/share/fonts/truetype/dejavu"
_WIN = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts")

def _fp(gf_name, dv_name="DejaVuSans-Bold.ttf"):
    for folder, name in [(_GF, gf_name), (_WIN, "arialbd.ttf"),
                         (_WIN, "arial.ttf"), (_DV, dv_name)]:
        p = os.path.join(folder, name)
        if os.path.exists(p):
            return p
    return None   # PIL will use its built-in default

F_BOLD  = _fp("Poppins-Bold.ttf")
F_MED   = _fp("Poppins-Medium.ttf",   "DejaVuSans.ttf")
F_REG   = _fp("Poppins-Regular.ttf",  "DejaVuSans.ttf")
F_LIGHT = _fp("Poppins-Light.ttf",    "DejaVuSans.ttf")

# ── COLOURS ────────────────────────────────────────────────────────────────────
BG         = (74,  144, 199)
WHITE      = (255, 255, 255)
DARK       = (15,   40,  80)
CIRCLE_BG  = (100, 170, 225)
CIRCLE_BDR = (30,   90, 155)

# ── HELPERS ────────────────────────────────────────────────────────────────────
def fnt(path, size):
    if path and os.path.exists(path):
        try: return ImageFont.truetype(path, size)
        except: pass
    return ImageFont.load_default()

def blank():
    return Image.new("RGB", (W, H), BG)

def pil2cv(img):
    return cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)

def tsz(draw, text, font):
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0], bb[3] - bb[1]

def cx(draw, text, font):
    w, _ = tsz(draw, text, font)
    return (W - w) // 2

def draw_wrapped(draw, text, x, y, font, color, max_w, gap=18):
    """Left-aligned wrapped text. Returns y after last line."""
    words = text.split()
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
        draw.text((x, y), line, font=font, fill=color)
        _, lh = tsz(draw, line, font)
        y += lh + gap
    return y

def draw_wrapped_center(draw, text, y, font, color, max_w, gap=18):
    """Centered wrapped text. Returns y after last line."""
    words = text.split()
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
        tw, lh = tsz(draw, line, font)
        draw.text(((W - tw) // 2, y), line, font=font, fill=color)
        y += lh + gap
    return y

def paste_image_centered(base, img_path, y_center=None, scale_to_width=None):
    if not os.path.exists(img_path):
        print(f"\n⚠️  Image not found: {img_path}")
        return base
    overlay = Image.open(img_path).convert("RGBA")
    if scale_to_width is not None:
        ratio = scale_to_width / overlay.width
        new_h = int(overlay.height * ratio)
        overlay = overlay.resize((scale_to_width, new_h), Image.LANCZOS)
    if y_center is None:
        y_center = H // 2
    x = (W - overlay.width) // 2
    y = y_center - overlay.height // 2
    base = base.convert("RGBA")
    base.paste(overlay, (x, y), overlay)
    return base.convert("RGB")

# ── SCREEN 1  (4 s) ────────────────────────────────────────────────────────────
def make_screen1():
    img = blank()
    img = paste_image_centered(img, IMG_SCREEN1, y_center=H // 2, scale_to_width=W - 80)
    return img

# ── SCREEN 2  (8 s) ────────────────────────────────────────────────────────────
def make_screen2(word, pos, defn):
    img = blank()
    draw = ImageDraw.Draw(img)
    y = 220
    f1 = fnt(F_BOLD, 110)
    draw.text((90, y), "Today's word:", font=f1, fill=DARK)
    _, h = tsz(draw, "Today's word:", f1); y += h + 36
    f2 = fnt(F_BOLD, 185)
    draw.text((90, y), word.capitalize(), font=f2, fill=WHITE)
    _, h = tsz(draw, word.capitalize(), f2); y += h + 90
    if pos:
        f3 = fnt(F_MED, 95)
        draw.text((90, y), "Part of speech:", font=f3, fill=DARK)
        _, h = tsz(draw, "Part of speech:", f3); y += h + 14
        draw.text((90, y), pos.capitalize(), font=f3, fill=WHITE)
        _, h = tsz(draw, pos.capitalize(), f3); y += h + 80
    f4 = fnt(F_MED, 95)
    draw.text((90, y), "Definition:", font=f4, fill=DARK)
    _, h = tsz(draw, "Definition:", f4); y += h + 22
    if defn:
        f5 = fnt(F_REG, 88)
        draw_wrapped(draw, defn, 90, y, f5, WHITE, W - 180, gap=24)
    return img

# ── SCREEN 3  (3 s) ────────────────────────────────────────────────────────────
def make_screen3(n):
    img = blank()
    if os.path.exists(IMG_SCREEN3):
        png = Image.open(IMG_SCREEN3).convert("RGBA")
        png = png.resize((W, H), Image.LANCZOS)
        try:
            arr = np.array(png)
            mask = (arr[:,:,0] < 60) & (arr[:,:,1] < 60) & (arr[:,:,2] < 60)
            arr[mask, 3] = 0
            png = Image.fromarray(arr)
        except Exception:
            pass
        img = img.convert("RGBA")
        img.alpha_composite(png)
        img = img.convert("RGB")
    else:
        print(f"\n⚠️  Screen 3 image not found: {IMG_SCREEN3}")
    draw = ImageDraw.Draw(img)
    cr  = 290
    ccx = W // 2
    ccy = H - 420
    draw.ellipse([ccx - cr, ccy - cr, ccx + cr, ccy + cr],
                 fill=CIRCLE_BG, outline=CIRCLE_BDR, width=14)
    f_num = fnt(F_BOLD, 360)
    num = str(n)
    nw, nh = tsz(draw, num, f_num)
    draw.text((ccx - nw // 2, ccy - nh // 2 - 14), num, font=f_num, fill=DARK)
    return img

# ── SCREEN 4  (60 s) ───────────────────────────────────────────────────────────
def make_screen4(word, secs_left):
    img = blank()
    draw = ImageDraw.Draw(img)
    f_lbl = fnt(F_MED, 105)
    label = f"Word: {word.capitalize()}"
    tw, _ = tsz(draw, label, f_lbl)
    draw.text(((W - tw) // 2, 140), label, font=f_lbl, fill=WHITE)
    cx_c, cy_c = W // 2, H // 2 + 160
    r = 340
    draw.ellipse([cx_c - r, cy_c - r, cx_c + r, cy_c + r],
                 fill=CIRCLE_BG, outline=CIRCLE_BDR, width=16)
    progress = max(0.0, secs_left / 60.0)
    sweep    = int(360 * progress)
    if sweep > 0:
        arc_img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ad = ImageDraw.Draw(arc_img)
        ad.arc([cx_c - r, cy_c - r, cx_c + r, cy_c + r],
               start=-90, end=-90 + sweep,
               fill=(255, 255, 255, 220), width=26)
        img = img.convert("RGBA")
        img.alpha_composite(arc_img)
        img = img.convert("RGB")
        draw = ImageDraw.Draw(img)
    f_num = fnt(F_BOLD, 360)
    num   = str(max(0, int(math.ceil(secs_left))))
    nw, nh = tsz(draw, num, f_num)
    draw.text((cx_c - nw // 2, cy_c - nh // 2 - 14), num, font=f_num, fill=DARK)
    return img

# ── AUDIO ──────────────────────────────────────────────────────────────────────
SAMPLE_RATE = 44100

def gen_beep(freq=880, dur=0.22, vol=0.7):
    n = int(SAMPLE_RATE * dur)
    t = np.linspace(0, dur, n, False)
    d = np.sin(2 * np.pi * freq * t) * vol
    fade = max(1, int(n * 0.08))
    d[:fade]  *= np.linspace(0, 1, fade)
    d[-fade:] *= np.linspace(1, 0, fade)
    return (d * 32767).astype(np.int16)

def build_audio():
    total   = 75
    audio   = np.zeros(int(SAMPLE_RATE * total), dtype=np.int16)
    for t, freq in [(12.0, 750), (13.0, 750), (14.0, 1100)]:
        beep = gen_beep(freq=freq)
        s    = int(SAMPLE_RATE * t)
        audio[s:s + len(beep)] += beep
    with wave.open(TMP_AUDIO, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())

# ── WORD FETCH ─────────────────────────────────────────────────────────────────
FALLBACKS = [
    ("resilient",   "adjective", "Able to recover quickly from difficult conditions."),
    ("eloquent",    "adjective", "Fluent or persuasive in speaking or writing."),
    ("serendipity", "noun",      "The occurrence of events by chance in a happy or beneficial way."),
    ("tenacious",   "adjective", "Tending to keep a firm hold of something; persistent."),
    ("integrity",   "noun",      "The quality of being honest and having strong moral principles."),
    ("audacious",   "adjective", "Showing a willingness to take surprisingly bold risks."),
    ("empathy",     "noun",      "The ability to understand and share the feelings of another."),
    ("deliberate",  "adjective", "Done consciously and intentionally; careful and unhurried."),
]

def get_word():
    try:
        from wonderwords import RandomWord
        import requests
        rw = RandomWord()
        for _ in range(15):
            w = rw.word()
            try:
                r = requests.get(
                    f"https://api.dictionaryapi.dev/api/v2/entries/en/{w}", timeout=5)
                if r.status_code == 200:
                    m    = r.json()[0]["meanings"]
                    pos  = m[0]["partOfSpeech"]
                    defn = m[0]["definitions"][0]["definition"]
                    if defn and len(defn) > 10:
                        return w, pos, defn
            except: continue
    except: pass
    return random.choice(FALLBACKS)

# ── MAIN ───────────────────────────────────────────────────────────────────────
def main():
    # ── Parse arguments ────────────────────────────────────────────────────────
    skip_upload = "--no-upload" in sys.argv

    # ── Import Telegram notifier ───────────────────────────────────────────────
    try:
        import telegram_notifier as tg
        tg_ok = True
    except ImportError:
        tg_ok = False
        print("⚠️  telegram_notifier.py not found — Telegram notifications disabled.")

    print("🎬  Instagram Word Challenge Reel Generator")
    print("─" * 45)

    # ── Notify start ───────────────────────────────────────────────────────────
    if tg_ok:
        tg.notify_start()

    for label, path in [("Screen 1 image", IMG_SCREEN1), ("Screen 3 image", IMG_SCREEN3)]:
        if not os.path.exists(path):
            print(f"⚠️  {label} not found: {path}")
        else:
            print(f"✅  {label} found: {os.path.basename(path)}")

    print("\n📖  Fetching word…")
    try:
        word, pos, defn = get_word()
    except Exception as e:
        if tg_ok:
            tg.notify_error("Word fetch", str(e))
        raise

    print(f"    Word      : {word}")
    print(f"    POS       : {pos or 'N/A'}")
    snippet = (defn or "")[:65] + ("…" if defn and len(defn) > 65 else "")
    print(f"    Definition: {snippet}")
    print()

    # ── Notify word chosen ─────────────────────────────────────────────────────
    if tg_ok:
        tg.notify_word(word, pos, defn)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(TMP_VIDEO, fourcc, FPS, (W, H))

    print("▶  Screen 1/4  Opener      (4s) …", end=" ", flush=True)
    s1 = make_screen1()
    for _ in range(4 * FPS): writer.write(pil2cv(s1))
    print("✓")

    print("▶  Screen 2/4  Word reveal (8s) …", end=" ", flush=True)
    s2 = make_screen2(word, pos, defn)
    for _ in range(8 * FPS): writer.write(pil2cv(s2))
    print("✓")

    print("▶  Screen 3/4  Countdown   (3s) …", end=" ", flush=True)
    for n in [3, 2, 1]:
        s3 = make_screen3(n)
        for _ in range(1 * FPS): writer.write(pil2cv(s3))
    print("✓")

    print("▶  Screen 4/4  Timer      (60s) …")
    total = 60 * FPS
    for f in range(total):
        secs = 60 - f / FPS
        writer.write(pil2cv(make_screen4(word, secs)))
        if f % (3 * FPS) == 0:
            pct = int(f / total * 100)
            bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
            print(f"    [{bar}] {pct}%  ", end="\r")
    print(f"    [{'█'*20}] 100% ✓")
    writer.release()

    print("\n🔊  Building audio…", end=" ", flush=True)
    build_audio()
    print("✓")

    print("🎞   Merging video + audio…", end=" ", flush=True)
    cmd = ["ffmpeg", "-y",
           "-i", TMP_VIDEO, "-i", TMP_AUDIO,
           "-c:v", "libx264", "-preset", "fast", "-crf", "22",
           "-c:a", "aac", "-b:a", "128k", "-shortest", OUTPUT]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        subprocess.run(["cp" if os.name != "nt" else "copy",
                        TMP_VIDEO, OUTPUT], shell=(os.name == "nt"))
        print("(no ffmpeg — saved without audio)")
    else:
        print("✓")

    mb = os.path.getsize(OUTPUT) / 1024 / 1024
    print(f"\n✅  Saved → {OUTPUT}  ({mb:.1f} MB)")
    print(f"    Word     : {word.upper()}")
    print(f"    Duration : 75s  |  {W}×{H}  |  9:16 Reel")

    # ── Notify render done + send video preview ────────────────────────────────
    if tg_ok:
        tg.notify_render_done(OUTPUT)
        tg.send_video(
            OUTPUT,
            caption=f"🎬 Preview: Today's reel — word is <b>{word.upper()}</b>",
        )

    # ── Instagram auto-upload ──────────────────────────────────────────────────
    if skip_upload:
        print("\n⏭   Skipping Instagram upload (--no-upload flag).")
        if tg_ok:
            tg.notify_skipped("--no-upload flag was passed.")
    else:
        print("\n" + "─" * 45)
        print("📱  Uploading to Instagram…")
        print("─" * 45)
        if tg_ok:
            tg.notify_upload_start()
        try:
            from instagram_uploader import upload_reel
            post_id = upload_reel(
                video_path=OUTPUT,
                word=word,
                pos=pos,
                defn=defn,
            )
            print(f"\n🎉  Reel is LIVE on Instagram!  (Post ID: {post_id})")
            print("    Open the Instagram app to see it on your profile.")
            if tg_ok:
                tg.notify_live(post_id, word)
        except ImportError:
            msg = "instagram_uploader.py not found — skipping upload."
            print(f"⚠️  {msg}")
            if tg_ok:
                tg.notify_skipped(msg)
        except ValueError as e:
            if "not set" in str(e):
                msg = f"Credentials not configured:\n{e}"
                print(f"⚠️  Upload skipped — {msg}")
                if tg_ok:
                    tg.notify_skipped(msg)
            else:
                print(f"❌  Upload error:\n    {e}")
                print("    Video saved locally as:", OUTPUT)
                if tg_ok:
                    tg.notify_error("Instagram upload", str(e))
        except Exception as e:
            print(f"❌  Upload failed:\n    {e}")
            print("    The video is still saved locally as:", OUTPUT)
            if tg_ok:
                tg.notify_error("Instagram upload", str(e))

    print("\n📱  Done!")

if __name__ == "__main__":
    main()