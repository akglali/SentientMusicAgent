import re
from dataclasses import dataclass

@dataclass
class ParsedPrompt:
    intent: str          # "greeting" | "mood" | "vibe" | "track" | "artist_like" | "artist_top"
    vibe: str | None = None
    artist: str | None = None
    title: str | None = None
    mood: str | None = None
    raw: str = ""

ARTIST_SEP = re.compile(r"\s*[-–—:]\s*")  # match -, –, —, :

# for later we can add more moods
MOOD_MAP = {
    "sad": ["sad", "down", "depressed", "blue", "heartbroken"],
    "happy": ["happy", "joy", "good mood", "excited", "cheerful"],
    "calm": ["calm", "relax", "chill", "peaceful", "lofi"],
    "angry": ["angry", "rage", "mad"],
    "focus": ["focus", "study", "concentrate", "deep work"],
    "energetic": ["energetic", "hype", "workout", "pump"],
}

def _detect_greeting(t: str) -> bool:
    return t.lower() in {"hi", "hello", "hey", "yo", "sup"} or t.lower().startswith(("hi ", "hello ", "hey "))

def _detect_mood(t: str) -> str | None:
    low = t.lower()
    for mood, keywords in MOOD_MAP.items():
        if any(k in low for k in keywords) or low.startswith(f"i am {mood}") or low.startswith(f"i'm {mood}"):
            return mood
    return None

def parse_prompt(text: str) -> ParsedPrompt:
    t = (text or "").strip()

    if not t:
        return ParsedPrompt(intent="greeting", raw=t)
    

    if _detect_greeting(t):
        return ParsedPrompt(intent="greeting", raw=t)
    
    mood = _detect_mood(t)
    if mood:
        return ParsedPrompt(intent="mood", mood=mood, vibe=mood, raw=t)

    # Pattern 1: "Artist - Song" or "Artist: Song"
    if ARTIST_SEP.search(t):
        parts = ARTIST_SEP.split(t, maxsplit=1)
        if len(parts) == 2 and parts[0] and parts[1]:
            return ParsedPrompt(intent="track", artist=parts[0].strip(), title=parts[1].strip(), raw=t)

    # Pattern 2: "like <artist>" / "similar to <artist>"
    m = re.search(r"(?:like|similar to)\s+(.+)$", t, re.IGNORECASE)
    if m:
        return ParsedPrompt(intent="artist_like", artist=m.group(1).strip(), raw=t)

    # Pattern 3: "<artist> top tracks" / "top songs by <artist>"
    m2 = re.search(r"^(?:top\s+(?:songs|tracks)\s+by|by)\s+(.+)$", t, re.IGNORECASE)
    if not m2:
        # also catch "top track by katty pery" exactly if user write it by mistake
        m2 = re.search(r"^top\s+(?:song|songs|track|tracks)\s+by\s+(.+)$", t, re.IGNORECASE)
    if m2:
        return ParsedPrompt(intent="artist_top", artist=m2.group(1).strip(), raw=t)

    # short = vibe/tag, else generic track search
    if len(t.split()) <= 3:
        return ParsedPrompt(intent="vibe", vibe=t, raw=t)
    return ParsedPrompt(intent="track", title=t, raw=t)
