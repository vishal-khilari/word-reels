"""
instagram_uploader.py
─────────────────────
Uploads reels directly to Instagram — no third-party hosting needed.

SETUP: Fill in ACCESS_TOKEN and IG_USER_ID below.
"""

import os, sys, time, json, requests

# ── CONFIG ─────────────────────────────────────────────────────────────────────
ACCESS_TOKEN  = "YOUR_LONG_LIVED_ACCESS_TOKEN"
IG_USER_ID    = "YOUR_INSTAGRAM_USER_ID"
CUSTOM_CAPTION = ""
# ──────────────────────────────────────────────────────────────────────────────

GRAPH_BASE = "https://graph.facebook.com/v21.0"


# ── PHASE 1 : create container ───────────────────────────────────────────────

def init_upload_session(local_path: str, caption: str):
    file_size = os.path.getsize(local_path)
    print(f"  📋  Initialising upload session ({file_size/1024/1024:.1f} MB)…")

    resp = requests.post(
        f"{GRAPH_BASE}/{IG_USER_ID}/media",
        data={
            "media_type":    "REELS",
            "upload_type":   "resumable",
            "caption":       caption,
            "share_to_feed": "true",
            "access_token":  ACCESS_TOKEN,
        },
        timeout=30,
    )
    body = resp.json()

    if "error" in body:
        raise RuntimeError(
            f"Session init failed (code {body['error'].get('code')}):\n"
            f"  {body['error'].get('message')}"
        )

    container_id = body.get("id")
    upload_url   = body.get("uri")

    if not container_id or not upload_url:
        raise RuntimeError(f"Missing id/uri in response:\n{json.dumps(body, indent=2)}")

    print(f"  ✅  Container ID : {container_id}")
    print(f"  ✅  Upload URL   : {upload_url}")
    return container_id, upload_url


# ── PHASE 2 : upload video (tries all method + auth combos) ──────────────────

def upload_video_bytes(local_path: str, upload_url: str) -> None:
    file_size = os.path.getsize(local_path)
    print(f"  ⬆️   Uploading {file_size/1024/1024:.1f} MB…")

    with open(local_path, "rb") as f:
        video_bytes = f.read()

    base_headers = {
        "offset":       "0",
        "file_size":    str(file_size),
        "Content-Type": "application/octet-stream",
    }

    # Try every combination until one works
    combos = [
        ("PUT",  f"OAuth {ACCESS_TOKEN}"),
        ("POST", f"OAuth {ACCESS_TOKEN}"),
        ("PUT",  f"Bearer {ACCESS_TOKEN}"),
        ("POST", f"Bearer {ACCESS_TOKEN}"),
    ]

    for method, auth in combos:
        headers = {**base_headers, "Authorization": auth}
        print(f"      Trying {method} with {auth[:10]}…", end=" ")

        if method == "PUT":
            resp = requests.put(upload_url,  headers=headers, data=video_bytes, timeout=300)
        else:
            resp = requests.post(upload_url, headers=headers, data=video_bytes, timeout=300)

        print(f"→ HTTP {resp.status_code}  {resp.text[:80].strip()}")

        if resp.status_code in (200, 201):
            print("  ✅  Upload succeeded!")
            return

    raise RuntimeError(
        "All upload attempts failed. Check your access token has "
        "'instagram_content_publish' permission and hasn't expired."
    )


# ── PHASE 3 : poll until FINISHED ────────────────────────────────────────────

def wait_for_container(container_id: str, timeout: int = 300) -> None:
    print("  ⏳  Waiting for Instagram to process the video…")
    endpoint = f"{GRAPH_BASE}/{container_id}"
    params   = {"fields": "status_code,status", "access_token": ACCESS_TOKEN}
    deadline = time.time() + timeout
    dots     = 0

    while time.time() < deadline:
        body   = requests.get(endpoint, params=params, timeout=30).json()
        status = body.get("status_code", "")
        dots  += 1
        print(f"      Status: {status or 'checking'} {'.' * (dots % 4)}   ", end="\r")

        if status == "FINISHED":
            print("\n  ✅  Processing complete.")
            return
        elif status == "ERROR":
            raise RuntimeError(f"Instagram rejected the video:\n{json.dumps(body, indent=2)}")

        time.sleep(8)

    raise TimeoutError(f"Processing timed out after {timeout}s.")


# ── PHASE 4 : publish ────────────────────────────────────────────────────────

def publish_container(container_id: str) -> str:
    print("  🚀  Publishing reel…")
    body = requests.post(
        f"{GRAPH_BASE}/{IG_USER_ID}/media_publish",
        data={"creation_id": container_id, "access_token": ACCESS_TOKEN},
        timeout=60,
    ).json()

    if "error" in body:
        raise RuntimeError(
            f"Publish failed (code {body['error'].get('code')}):\n"
            f"  {body['error'].get('message')}"
        )

    post_id = body["id"]
    print(f"  ✅  Post ID: {post_id}")
    return post_id


# ── CAPTION ───────────────────────────────────────────────────────────────────

def build_caption(word: str, pos: str, defn: str) -> str:
    if CUSTOM_CAPTION:
        return CUSTOM_CAPTION
    return (
        f"✨ Today's Word Challenge: {word.upper()} ✨\n\n"
        f"📖 ({pos.capitalize()})\n"
        f"{defn}\n\n"
        f"💬 You have 60 seconds to use this word out loud!\n"
        f"Drop your sentence in the comments 👇\n\n"
        f"#WordOfTheDay #EnglishChallenge #SpeakingChallenge "
        f"#LearnEnglish #VocabularyChallenge #EnglishVocabulary "
        f"#60SecondChallenge #PublicSpeaking #WordChallenge "
        f"#EnglishLearning #DailyChallenge #SpokenEnglish"
    )


# ── MAIN ─────────────────────────────────────────────────────────────────────

def upload_reel(video_path: str, word: str, pos: str = "", defn: str = "") -> str:
    if ACCESS_TOKEN == "YOUR_LONG_LIVED_ACCESS_TOKEN":
        raise ValueError("ACCESS_TOKEN not set in instagram_uploader.py")
    if IG_USER_ID == "YOUR_INSTAGRAM_USER_ID":
        raise ValueError("IG_USER_ID not set in instagram_uploader.py")
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    caption                  = build_caption(word, pos, defn)
    print(f"\n📝  Caption preview:\n    {caption[:120]}…\n")

    container_id, upload_url = init_upload_session(video_path, caption)
    upload_video_bytes(video_path, upload_url)
    wait_for_container(container_id)
    return publish_container(container_id)


# ── STANDALONE ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python instagram_uploader.py <video.mp4> [word] [pos] [definition]")
        sys.exit(1)
    try:
        pid = upload_reel(
            sys.argv[1],
            sys.argv[2] if len(sys.argv) > 2 else "challenge",
            sys.argv[3] if len(sys.argv) > 3 else "noun",
            sys.argv[4] if len(sys.argv) > 4 else "A test upload.",
        )
        print(f"\n🎉  Reel is LIVE!  Post ID: {pid}")
    except Exception as e:
        print(f"\n❌  {e}")
        sys.exit(1)