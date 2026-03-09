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

# ── IMPORTS ────────────────────────────────────────────────────────────────────
import os         
import sys        
import wave       
import math       
import subprocess 
import random     
import tempfile   
import numpy as np
import cv2        
from PIL import Image, ImageDraw, ImageFont

# ── CONFIG ─────────────────────────────────────────────────────────────────────
W, H      = 1080, 1920        # video width and height in pixels (standard 9:16 vertical/Reels format)
FPS       = 30                # frames per second — how many images are shown per second in the video
_TMP      = tempfile.gettempdir()                     # gets the OS temp folder path (e.g. /tmp on Linux)
TMP_VIDEO = os.path.join(_TMP, "reel_noaudio.mp4")    # path to the temporary video file without audio
TMP_AUDIO = os.path.join(_TMP, "reel_audio.wav")      # path to the temporary audio-only WAV file
OUTPUT    = "word_reel.mp4"                           # final output file name saved in the current folder

# Image assets — expected in the same folder as this script
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))  # gets the folder where this script lives
IMG_SCREEN1 = os.path.join(SCRIPT_DIR, "Overcome_your_fear_of_speaking_in_just_60_seconds.png")          # full path to the Screen 1 opener image
IMG_SCREEN3 = os.path.join(SCRIPT_DIR, "You_have_60_seconds_to_speak_using_this_word_Don't_stop_talking.png")  # full path to the Screen 3 prompt image

# Font paths — tries Google Fonts, falls back to DejaVu
_GF  = "/usr/share/fonts/truetype/google-fonts"                              # folder where Google Fonts are installed on Linux
_DV  = "/usr/share/fonts/truetype/dejavu"                                    # folder where DejaVu fallback fonts live on Linux
_WIN = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts")         # Windows system fonts folder path

def _fp(gf_name, dv_name="DejaVuSans-Bold.ttf"):
    # tries each font location in order and returns the first path that actually exists on disk
    for folder, name in [(_GF, gf_name), (_WIN, "arialbd.ttf"),
                         (_WIN, "arial.ttf"), (_DV, dv_name)]:
        p = os.path.join(folder, name)   # builds the full path to the candidate font file
        if os.path.exists(p):            # checks if that font file exists on this machine
            return p                     # returns the first found font path immediately
    return None   # returns None if no font file was found; PIL will then use its built-in default

F_BOLD  = _fp("Poppins-Bold.ttf")                        # path to the bold font used for headings and the word
F_MED   = _fp("Poppins-Medium.ttf",   "DejaVuSans.ttf")  # path to the medium-weight font used for labels
F_REG   = _fp("Poppins-Regular.ttf",  "DejaVuSans.ttf")  # path to the regular font (available for use if needed)
F_LIGHT = _fp("Poppins-Light.ttf",    "DejaVuSans.ttf")  # path to the light font used for the definition body text

# ── COLOURS ────────────────────────────────────────────────────────────────────
BG         = (74,  144, 199)   # background blue colour used on all screens (RGB)
WHITE      = (255, 255, 255)   # pure white used for main text like the word and definition
DARK       = (15,   40,  80)   # dark navy blue used for label text like "Today's word:"
CIRCLE_BG  = (100, 170, 225)   # lighter blue fill colour inside the countdown/timer circles
CIRCLE_BDR = (30,   90, 155)   # darker blue colour for the circle border/outline

# ── HELPERS ────────────────────────────────────────────────────────────────────
def fnt(path, size):
    # loads a TrueType font at the given size; falls back to PIL's default if path is missing
    if path and os.path.exists(path):   # only tries to load if a valid path was provided and exists
        try: return ImageFont.truetype(path, size)  # loads the font file at the requested pixel size
        except: pass                                # silently ignores errors and falls through to default
    return ImageFont.load_default()     # returns PIL's built-in bitmap font if no TTF font is available

def blank():
    # creates a fresh 1080x1920 image filled with the background blue colour
    return Image.new("RGB", (W, H), BG)

def pil2cv(img):
    # converts a PIL Image to an OpenCV-compatible numpy array (BGR format) so cv2 can write it as a video frame
    return cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)

def tsz(draw, text, font):
    # measures and returns the pixel width and height of a text string when drawn with the given font
    bb = draw.textbbox((0, 0), text, font=font)   # gets the bounding box (x0, y0, x1, y1) of the text
    return bb[2] - bb[0], bb[3] - bb[1]           # returns width (x1-x0) and height (y1-y0)

def cx(draw, text, font):
    # calculates the x position needed to horizontally centre text on the canvas
    w, _ = tsz(draw, text, font)   # measures the text width
    return (W - w) // 2            # subtracts text width from canvas width and halves it

def draw_wrapped(draw, text, x, y, font, color, max_w, gap=18):
    """Left-aligned wrapped text. Returns y after last line."""
    words = text.split()       # splits the full text string into a list of individual words
    lines, cur = [], []        # lines = completed lines ready to draw; cur = words being collected for current line
    for w in words:            # loops through every word in the text
        test = " ".join(cur + [w])          # builds a trial string by adding the next word to the current line
        tw, _ = tsz(draw, test, font)       # measures how wide that trial string would be
        if tw > max_w and cur:              # if it's too wide AND there are already words in the current line
            lines.append(" ".join(cur))     # finishes the current line and saves it
            cur = [w]                       # starts a new line with the word that didn't fit
        else:
            cur.append(w)                   # the word fits, so add it to the current line
    if cur: lines.append(" ".join(cur))     # adds any remaining words as the final line
    for line in lines:                      # loops through each completed line to draw it
        draw.text((x, y), line, font=font, fill=color)   # draws the line at the current x,y position
        _, lh = tsz(draw, line, font)                    # measures the height of this line
        y += lh + gap                                    # moves y down by line height plus the gap between lines
    return y   # returns the y position after the last line so the caller knows where to continue

def draw_wrapped_center(draw, text, y, font, color, max_w, gap=18):
    """Centered wrapped text. Returns y after last line."""
    words = text.split()       # splits the text into individual words
    lines, cur = [], []        # lines = finished lines; cur = words being built into current line
    for w in words:            # iterates over every word
        test = " ".join(cur + [w])          # trial string with the next word added
        tw, _ = tsz(draw, test, font)       # measures its pixel width
        if tw > max_w and cur:              # if it overflows the max width and the line isn't empty
            lines.append(" ".join(cur))     # saves the current line
            cur = [w]                       # starts a new line
        else:
            cur.append(w)                   # word fits, keep building
    if cur: lines.append(" ".join(cur))     # saves the last line
    for line in lines:                      # draws each line
        tw, lh = tsz(draw, line, font)      # measures width and height of this line
        draw.text(((W - tw) // 2, y), line, font=font, fill=color)  # draws centred by offsetting x to the middle
        y += lh + gap                       # moves y down for the next line
    return y   # returns final y position after all lines

def paste_image_centered(base, img_path, y_center=None, scale_to_width=None):
    # loads an image from disk, optionally rescales it, and pastes it centred onto the base canvas
    if not os.path.exists(img_path):               # checks if the image file actually exists
        print(f"\n⚠️  Image not found: {img_path}")   # warns the user if the file is missing
        return base                                # returns the unchanged base image so the script doesn't crash
    overlay = Image.open(img_path).convert("RGBA")   # opens the image and converts to RGBA so transparency is preserved
    if scale_to_width is not None:               # only rescales if a target width was given
        ratio = scale_to_width / overlay.width   # calculates the scale factor needed to hit the target width
        new_h = int(overlay.height * ratio)      # applies the same scale factor to height to keep the aspect ratio
        overlay = overlay.resize((scale_to_width, new_h), Image.LANCZOS)  # resizes using high-quality LANCZOS filter
    if y_center is None:                         # if no vertical centre was specified
        y_center = H // 2                        # defaults to the exact middle of the canvas
    x = (W - overlay.width) // 2                # calculates x so the overlay is horizontally centred
    y = y_center - overlay.height // 2          # calculates y so the overlay is vertically centred at y_center
    base = base.convert("RGBA")                  # converts base to RGBA so alpha compositing works
    base.paste(overlay, (x, y), overlay)         # pastes the overlay onto the base using its own alpha channel as mask
    return base.convert("RGB")                   # converts back to RGB (no transparency) for video frame use

# ── SCREEN 1  (4 s) ────────────────────────────────────────────────────────────
def make_screen1():
    # builds the opener screen — just a full-screen background with the opener PNG centred on it
    img = blank()   # starts with a fresh blue background canvas
    # pastes the opener image centred horizontally, moved 120px above vertical centre, scaled to fill the width
    img = paste_image_centered(img, IMG_SCREEN1, y_center=H // 2 - 120, scale_to_width=W - 80)
    return img   # returns the finished screen as a PIL Image

# ── SCREEN 2  (8 s) ────────────────────────────────────────────────────────────
def make_screen2(word, pos, defn):
    # builds the word reveal screen showing: "Today's word:", the word, part of speech, and definition
    img  = blank()              # starts with a fresh blue background canvas
    draw = ImageDraw.Draw(img)  # creates a drawing context so text and shapes can be drawn onto the image

    LEFT        = 70         # left margin in pixels for all text on this screen
    MAX_W_DEFN  = W - 340    # maximum line width for definition text — narrower to avoid Instagram's side buttons
    MAX_W_OTHER = W - 180    # maximum line width for all other text (normal margin)

    f1 = fnt(F_BOLD,  102)   # font for "Today's word:" label — bold, slightly smaller than the word
    f2 = fnt(F_BOLD,  145)   # font for the actual word — largest text on the screen
    f3 = fnt(F_MED,    88)   # font for "Part of speech:" label and its value
    f4 = fnt(F_MED,    88)   # font for "Definition:" label
    f5 = fnt(F_LIGHT,  82)   # font for the definition body text — light weight for readability

    def block_height(text, font, max_w, gap=24):
        # measures the total pixel height a wrapped text block will occupy without actually drawing it
        words = text.split()        # splits text into words
        lines, cur = [], []         # lines = completed lines; cur = current line being built
        for w in words:             # iterates over each word
            test = " ".join(cur + [w])         # trial string
            tw, _ = tsz(draw, test, font)      # measures its width
            if tw > max_w and cur:             # if too wide and line isn't empty
                lines.append(" ".join(cur))    # saves the current line
                cur = [w]                      # starts a new line
            else:
                cur.append(w)                  # keeps building the line
        if cur: lines.append(" ".join(cur))    # saves the last line
        total = 0                              # accumulator for total height
        for line in lines:                     # loops through each wrapped line
            _, lh = tsz(draw, line, font)      # measures the height of this line
            total += lh + gap                  # adds line height plus gap to the total
        return total   # returns the total pixel height of the entire wrapped block

    # measures the pixel height of each text element so the whole block can be vertically centred
    _, h1  = tsz(draw, "Today's word:", f1)           # height of the "Today's word:" label
    _, h2  = tsz(draw, word.capitalize(), f2)          # height of the word itself
    _, h3a = tsz(draw, "Part of speech:", f3)          # height of the "Part of speech:" label
    _, h3b = tsz(draw, (pos or "").capitalize(), f3)   # height of the POS value (e.g. "Noun")
    _, h4  = tsz(draw, "Definition:", f4)              # height of the "Definition:" label
    h5     = block_height(defn or "", f5, MAX_W_DEFN)  # total height of the wrapped definition text block

    GAP_AFTER_LABEL  = 36    # vertical space in pixels between "Today's word:" and the word below it
    GAP_AFTER_WORD   = 110   # vertical space between the word and the "Part of speech:" section
    GAP_BETWEEN_POS  = 14    # vertical space between "Part of speech:" label and its value
    GAP_AFTER_POS    = 90    # vertical space between the POS value and the "Definition:" section
    GAP_AFTER_DEFLBL = 28    # vertical space between "Definition:" label and the definition body text

    # sums up the total height of the entire text block including all gaps
    total_h = (h1 + GAP_AFTER_LABEL +
               h2 + GAP_AFTER_WORD +
               h3a + GAP_BETWEEN_POS + h3b + GAP_AFTER_POS +
               h4 + GAP_AFTER_DEFLBL +
               h5)

    # calculates the starting y so the whole block is vertically centred, with a slight upward bias of 60px
    y = max(160, (H - total_h) // 2 - 60)   # max(160,...) ensures we never start too close to the top edge

    # ── Draw each element top-to-bottom ───────────────────────────────────────
    draw.text((LEFT, y), "Today's word:", font=f1, fill=DARK)   # draws the "Today's word:" label in dark navy
    y += h1 + GAP_AFTER_LABEL                                   # advances y past the label and its gap

    draw.text((LEFT, y), word.capitalize(), font=f2, fill=WHITE)  # draws the word itself in large white bold text
    y += h2 + GAP_AFTER_WORD                                      # advances y past the word and its gap

    if pos:                                                           # only draws the POS section if a part of speech was found
        draw.text((LEFT, y), "Part of speech:", font=f3, fill=DARK)  # draws "Part of speech:" label in dark navy
        y += h3a + GAP_BETWEEN_POS                                   # advances y past the label
        draw.text((LEFT, y), pos.capitalize(), font=f3, fill=WHITE)  # draws the POS value (e.g. "Adjective") in white
        y += h3b + GAP_AFTER_POS                                     # advances y past the POS value and its gap

    draw.text((LEFT, y), "Definition:", font=f4, fill=DARK)   # draws the "Definition:" label in dark navy
    y += h4 + GAP_AFTER_DEFLBL                                # advances y past the label

    if defn:   # only draws definition text if a definition string was provided
        draw_wrapped(draw, defn, LEFT, y, f5, WHITE, MAX_W_DEFN, gap=24)  # draws definition as wrapped light white text with extra right margin

    return img   # returns the finished Screen 2 frame as a PIL Image

# ── SCREEN 3  (3 s) ────────────────────────────────────────────────────────────
def make_screen3(n):
    # builds one frame of Screen 3 — the prompt image overlaid with a countdown number (3, 2, or 1)
    img = blank()   # starts with a fresh blue background canvas
    if os.path.exists(IMG_SCREEN3):                          # checks if the Screen 3 prompt image file exists
        png = Image.open(IMG_SCREEN3).convert("RGBA")        # opens the image and ensures it has an alpha channel
        png = png.resize((W, H), Image.LANCZOS)              # scales it to fill the full 1080x1920 canvas
        try:
            arr  = np.array(png)                             # converts the image to a numpy pixel array for direct manipulation
            mask = (arr[:,:,0] < 60) & (arr[:,:,1] < 60) & (arr[:,:,2] < 60)  # creates a boolean mask for near-black pixels
            arr[mask, 3] = 0                                 # sets the alpha of near-black pixels to 0 (fully transparent)
            png = Image.fromarray(arr)                       # converts the modified array back to a PIL Image
        except Exception:
            pass                                             # silently ignores any numpy errors and uses the image as-is
        img = img.convert("RGBA")         # converts base canvas to RGBA so alpha compositing works
        img.alpha_composite(png)          # composites the (now transparent-background) prompt image onto the canvas
        img = img.convert("RGB")          # converts back to RGB for video frame use
    else:
        print(f"\n⚠️  Screen 3 image not found: {IMG_SCREEN3}")   # warns if the image file is missing

    draw = ImageDraw.Draw(img)   # creates a drawing context to draw the countdown circle and number
    cr  = 290                    # radius of the countdown circle in pixels
    ccx = W // 2                 # x coordinate of the circle centre — horizontally centred on the canvas
    ccy = H - 500                # y coordinate of the circle centre — positioned near the bottom, moved up 80px from original
    draw.ellipse([ccx - cr, ccy - cr, ccx + cr, ccy + cr],
                 fill=CIRCLE_BG, outline=CIRCLE_BDR, width=14)  # draws the filled circle with a border

    f_num = fnt(F_BOLD, 360)               # large bold font for the countdown digit
    num   = str(n)                         # converts the countdown number (3, 2, or 1) to a string for drawing
    nw, nh = tsz(draw, num, f_num)         # measures the width and height of the digit
    draw.text((ccx - nw // 2, ccy - nh // 2 - 69), num, font=f_num, fill=DARK)
    # draws the number centred inside the circle; -69 shifts it up slightly so it looks optically centred
    return img   # returns the finished countdown frame as a PIL Image

# ── SCREEN 4  (60 s) ───────────────────────────────────────────────────────────
def make_screen4(word, secs_left):
    # builds one frame of Screen 4 — the 60-second speaking timer with the word shown at the top
    img  = blank()              # starts with a fresh blue background canvas
    draw = ImageDraw.Draw(img)  # creates a drawing context for text and shapes

    f_lbl = fnt(F_MED, 105)               # medium-weight font for the "Word: X" label at the top
    label = f"Word: {word.capitalize()}"  # builds the label string e.g. "Word: Resilient"
    tw, _ = tsz(draw, label, f_lbl)       # measures the width of the label to centre it
    draw.text(((W - tw) // 2, 250), label, font=f_lbl, fill=WHITE)
    # draws the label horizontally centred, at y=250 (moved down from original 140)

    cx_c, cy_c = W // 2, H // 2 + 160   # centre coordinates of the timer circle — horizontally centred, in the lower half
    r = 340                              # radius of the timer circle in pixels

    draw.ellipse([cx_c - r, cy_c - r, cx_c + r, cy_c + r],
                 fill=CIRCLE_BG, outline=CIRCLE_BDR, width=16)  # draws the filled circle with a border

    progress = max(0.0, secs_left / 60.0)   # calculates progress as a 0.0-1.0 fraction of 60 seconds remaining
    sweep    = int(360 * progress)           # converts the fraction to degrees (0-360) for the arc sweep

    if sweep > 0:   # only draws the arc if there's any time remaining
        arc_img = Image.new("RGBA", (W, H), (0, 0, 0, 0))   # creates a transparent overlay image for the arc
        ad = ImageDraw.Draw(arc_img)                          # drawing context for the overlay
        ad.arc([cx_c - r, cy_c - r, cx_c + r, cy_c + r],
               start=-90, end=-90 + sweep,
               fill=(255, 255, 255, 220), width=26)
        # draws a semi-transparent white arc starting from the top (-90 deg) sweeping clockwise as time decreases
        img = img.convert("RGBA")           # converts base canvas to RGBA for compositing
        img.alpha_composite(arc_img)        # composites the arc overlay onto the canvas
        img = img.convert("RGB")            # converts back to RGB for video frame use
        draw = ImageDraw.Draw(img)          # recreates the drawing context on the updated image

    f_num = fnt(F_BOLD, 360)                             # large bold font for the countdown number inside the circle
    num   = str(max(0, int(math.ceil(secs_left))))       # rounds up secs_left and converts to string; clamps at 0
    nw, nh = tsz(draw, num, f_num)                       # measures the width and height of the number
    draw.text((cx_c - nw // 2, cy_c - nh // 2 - 69), num, font=f_num, fill=DARK)
    # draws the number centred inside the circle; -69 shifts it up so it looks optically centred in the circle
    return img   # returns the finished timer frame as a PIL Image

# ── AUDIO ──────────────────────────────────────────────────────────────────────
SAMPLE_RATE = 44100   # audio sample rate in Hz — standard CD quality (44,100 samples per second)

def gen_beep(freq=880, dur=0.22, vol=0.7):
    # generates a short beep tone as a numpy array of 16-bit PCM audio samples
    n = int(SAMPLE_RATE * dur)             # total number of audio samples for the beep duration
    t = np.linspace(0, dur, n, False)      # creates an evenly spaced time array from 0 to dur seconds
    d = np.sin(2 * np.pi * freq * t) * vol # generates a sine wave at the given frequency and scales it by volume
    fade = max(1, int(n * 0.08))           # calculates how many samples to use for fade-in/out (8% of total)
    d[:fade]  *= np.linspace(0, 1, fade)   # applies a linear fade-in at the start to avoid a click/pop
    d[-fade:] *= np.linspace(1, 0, fade)   # applies a linear fade-out at the end to avoid a click/pop
    return (d * 32767).astype(np.int16)    # scales to the 16-bit integer range and converts to int16 PCM format

def build_audio():
    # constructs the full 75-second audio track with three beeps at the countdown moments and writes it to a WAV file
    total = 75                                              # total audio duration in seconds (matches full reel length)
    audio = np.zeros(int(SAMPLE_RATE * total), dtype=np.int16)  # creates a silent audio array for the full duration
    for t, freq in [(12.0, 750), (13.0, 750), (14.0, 1100)]:   # three beeps: two low ones then a higher one at go
        beep = gen_beep(freq=freq)          # generates the beep tone at the specified frequency
        s    = int(SAMPLE_RATE * t)         # converts the beep start time (seconds) to a sample index
        audio[s:s + len(beep)] += beep      # mixes the beep into the audio array at the correct position
    with wave.open(TMP_AUDIO, "w") as wf:   # opens a new WAV file for writing
        wf.setnchannels(1)                  # sets to mono (1 channel)
        wf.setsampwidth(2)                  # sets sample width to 2 bytes (16-bit audio)
        wf.setframerate(SAMPLE_RATE)        # sets the sample rate to 44100 Hz
        wf.writeframes(audio.tobytes())     # writes all the audio samples as raw bytes into the WAV file

# ── WORD FETCH ─────────────────────────────────────────────────────────────────
# hardcoded list of fallback words used if the internet-based word API is unavailable
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
    # tries to fetch a random real English word with its definition from the internet; falls back to the hardcoded list
    try:
        from wonderwords import RandomWord   # wonderwords library generates random English words
        import requests                      # requests library is used to call the dictionary API over HTTP
        rw = RandomWord()                    # creates a RandomWord instance for generating words
        for _ in range(15):                  # tries up to 15 different random words to find one with a valid definition
            w = rw.word()                    # generates one random English word
            try:
                r = requests.get(
                    f"https://api.dictionaryapi.dev/api/v2/entries/en/{w}", timeout=5)
                # calls the free dictionary API with the random word; timeout=5 prevents hanging if the server is slow
                if r.status_code == 200:                          # 200 means the API found the word successfully
                    m    = r.json()[0]["meanings"]                # extracts the list of meanings from the JSON response
                    pos  = m[0]["partOfSpeech"]                   # takes the part of speech from the first meaning
                    defn = m[0]["definitions"][0]["definition"]   # takes the first definition text
                    if defn and len(defn) > 10:   # only accepts definitions longer than 10 chars (avoids empty/stub entries)
                        return w, pos, defn       # returns the word, part of speech, and definition as a tuple
            except: continue   # silently skips this word if any network or parsing error occurs and tries the next
    except: pass   # silently falls through to the fallback list if wonderwords or requests aren't installed
    return random.choice(FALLBACKS)   # picks and returns a random word from the hardcoded fallback list

# ── MAIN ───────────────────────────────────────────────────────────────────────
def main():
    # ── Parse arguments ────────────────────────────────────────────────────────
    skip_upload = "--no-upload" in sys.argv   # checks if the user passed --no-upload flag to skip Instagram posting

    # ── Import Telegram notifier ───────────────────────────────────────────────
    try:
        import telegram_notifier as tg   # tries to import the optional Telegram notification module
        tg_ok = True                     # sets flag to True so Telegram notifications are enabled
    except ImportError:
        tg_ok = False   # sets flag to False if the module isn't found so all tg calls are safely skipped
        print("⚠️  telegram_notifier.py not found — Telegram notifications disabled.")

    print("🎬  Instagram Word Challenge Reel Generator")
    print("─" * 45)   # prints a decorative separator line in the terminal

    # ── Notify start ───────────────────────────────────────────────────────────
    if tg_ok:
        tg.notify_start()   # sends a Telegram message saying the reel generation has started

    # checks whether each required image asset exists on disk and prints the result
    for label, path in [("Screen 1 image", IMG_SCREEN1), ("Screen 3 image", IMG_SCREEN3)]:
        if not os.path.exists(path):
            print(f"⚠️  {label} not found: {path}")          # warns if a required image is missing
        else:
            print(f"✅  {label} found: {os.path.basename(path)}")   # confirms the image was found

    print("\n📖  Fetching word…")
    try:
        word, pos, defn = get_word()   # calls get_word() to retrieve the word, POS, and definition
    except Exception as e:
        if tg_ok:
            tg.notify_error("Word fetch", str(e))   # sends a Telegram error notification if word fetching failed
        raise   # re-raises the exception so the script stops with a visible error

    # prints the fetched word details to the terminal for confirmation
    print(f"    Word      : {word}")
    print(f"    POS       : {pos or 'N/A'}")
    snippet = (defn or "")[:65] + ("…" if defn and len(defn) > 65 else "")   # truncates long definitions to 65 chars for display
    print(f"    Definition: {snippet}")
    print()

    # ── Notify word chosen ─────────────────────────────────────────────────────
    if tg_ok:
        tg.notify_word(word, pos, defn)   # sends a Telegram message with the chosen word details

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")                   # creates the four-character codec code for MP4 video
    writer = cv2.VideoWriter(TMP_VIDEO, fourcc, FPS, (W, H))  # opens a video file writer at the temp path with the configured FPS and resolution

    print("▶  Screen 1/4  Opener      (4s) …", end=" ", flush=True)
    s1 = make_screen1()                               # generates the Screen 1 image (opener)
    for _ in range(4 * FPS): writer.write(pil2cv(s1)) # writes the same frame 120 times (4s x 30fps) to create 4 seconds of video
    print("✓")

    print("▶  Screen 2/4  Word reveal (8s) …", end=" ", flush=True)
    s2 = make_screen2(word, pos, defn)                # generates the Screen 2 image (word reveal) using the fetched word data
    for _ in range(8 * FPS): writer.write(pil2cv(s2)) # writes it 240 times (8s x 30fps) for 8 seconds of video
    print("✓")

    print("▶  Screen 3/4  Countdown   (3s) …", end=" ", flush=True)
    for n in [3, 2, 1]:                               # loops through the countdown numbers 3, 2, 1
        s3 = make_screen3(n)                          # generates the countdown frame for this number
        for _ in range(1 * FPS): writer.write(pil2cv(s3))  # writes it 30 times (1s x 30fps) so each number shows for exactly 1 second
    print("✓")

    print("▶  Screen 4/4  Timer      (60s) …")
    total = 60 * FPS   # total number of frames for the 60-second timer screen (1800 frames)
    for f in range(total):                               # loops through every frame of the timer screen
        secs = 60 - f / FPS                              # calculates how many seconds are left at this frame
        writer.write(pil2cv(make_screen4(word, secs)))   # generates and writes the timer frame for this moment in time
        if f % (3 * FPS) == 0:                           # every 3 seconds, updates the progress bar in the terminal
            pct = int(f / total * 100)                   # calculates the percentage of frames written so far
            bar = "█" * (pct // 5) + "░" * (20 - pct // 5)  # builds a 20-character progress bar string
            print(f"    [{bar}] {pct}%  ", end="\r")    # prints the progress bar, overwriting the same line each time
    print(f"    [{'█'*20}] 100% ✓")   # prints the completed progress bar when all frames are done
    writer.release()   # finalises and closes the video file so it can be read by other programs

    print("\n🔊  Building audio…", end=" ", flush=True)
    build_audio()   # generates the beep audio and writes it to the temp WAV file
    print("✓")

    print("🎞   Merging video + audio…", end=" ", flush=True)
    # builds the ffmpeg command to combine the silent video and the audio WAV into a final compressed MP4
    cmd = ["ffmpeg", "-y",                               # -y overwrites the output file without asking
           "-i", TMP_VIDEO, "-i", TMP_AUDIO,            # specifies the two input files: video and audio
           "-c:v", "libx264", "-preset", "fast", "-crf", "22",   # encodes video with H.264, fast preset, quality level 22
           "-c:a", "aac", "-b:a", "128k", "-shortest", OUTPUT]   # encodes audio as AAC at 128kbps; -shortest stops at the shorter stream
    r = subprocess.run(cmd, capture_output=True)   # runs the ffmpeg command and captures its output
    if r.returncode != 0:   # if ffmpeg failed (non-zero exit code)
        subprocess.run(["cp" if os.name != "nt" else "copy",
                        TMP_VIDEO, OUTPUT], shell=(os.name == "nt"))   # falls back to copying the silent video as the output
        print("(no ffmpeg — saved without audio)")   # notifies the user that audio merging was skipped
    else:
        print("✓")   # confirms successful ffmpeg merge

    mb = os.path.getsize(OUTPUT) / 1024 / 1024   # calculates the output file size in megabytes
    print(f"\n✅  Saved → {OUTPUT}  ({mb:.1f} MB)")   # prints the output file path and size
    print(f"    Word     : {word.upper()}")            # prints the word in uppercase for visibility
    print(f"    Duration : 75s  |  {W}×{H}  |  9:16 Reel")   # prints reel duration and resolution info

    # ── Notify render done + send video preview ────────────────────────────────
    if tg_ok:
        tg.notify_render_done(OUTPUT)   # sends a Telegram message saying the render is complete
        tg.send_video(
            OUTPUT,
            caption=f"🎬 Preview: Today's reel — word is <b>{word.upper()}</b>",
        )   # sends the finished video file directly to Telegram as a preview

    # ── Instagram auto-upload ──────────────────────────────────────────────────
    if skip_upload:
        print("\n⏭   Skipping Instagram upload (--no-upload flag).")   # confirms the upload was intentionally skipped
        if tg_ok:
            tg.notify_skipped("--no-upload flag was passed.")   # notifies Telegram that upload was skipped
    else:
        print("\n" + "─" * 45)
        print("📱  Uploading to Instagram…")
        print("─" * 45)
        if tg_ok:
            tg.notify_upload_start()   # sends a Telegram message saying the Instagram upload is starting
        try:
            from instagram_uploader import upload_reel   # imports the Instagram upload module
            post_id = upload_reel(
                video_path=OUTPUT,   # path to the finished video file
                word=word,           # the word used in this reel (for the caption)
                pos=pos,             # part of speech (for the caption)
                defn=defn,           # definition (for the caption)
            )
            print(f"\n🎉  Reel is LIVE on Instagram!  (Post ID: {post_id})")   # confirms successful upload with the post ID
            print("    Open the Instagram app to see it on your profile.")
            if tg_ok:
                tg.notify_live(post_id, word)   # sends a Telegram message with the live post ID
        except ImportError:
            msg = "instagram_uploader.py not found — skipping upload."
            print(f"⚠️  {msg}")   # warns if the instagram_uploader module isn't in the folder
            if tg_ok:
                tg.notify_skipped(msg)   # notifies Telegram the upload was skipped due to missing module
        except ValueError as e:
            if "not set" in str(e):   # catches the specific error raised when credentials are not configured
                msg = f"Credentials not configured:\n{e}"
                print(f"⚠️  Upload skipped — {msg}")   # tells the user their Instagram credentials are missing
                if tg_ok:
                    tg.notify_skipped(msg)
            else:
                print(f"❌  Upload error:\n    {e}")            # prints any other ValueError that occurred
                print("    Video saved locally as:", OUTPUT)   # reassures the user the video is still saved
                if tg_ok:
                    tg.notify_error("Instagram upload", str(e))   # notifies Telegram of the upload error
        except Exception as e:
            print(f"❌  Upload failed:\n    {e}")                       # catches any unexpected upload error
            print("    The video is still saved locally as:", OUTPUT)  # reassures the user the video is still saved
            if tg_ok:
                tg.notify_error("Instagram upload", str(e))   # notifies Telegram of the unexpected error

    print("\n📱  Done!")   # prints a final completion message to the terminal

if __name__ == "__main__":
    main()   # runs the main() function only when the script is executed directly (not when imported as a module)