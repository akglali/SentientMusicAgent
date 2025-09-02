import os
import httpx
import random                          
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv()

LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
BASE = "https://ws.audioscrobbler.com/2.0/"


async def _get_json(params: dict):
    if not LASTFM_API_KEY:
        return None
    params = {**params, "api_key": LASTFM_API_KEY, "format": "json"}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(BASE, params=params)
        r.raise_for_status()
        return r.json()
def _yt_link(artist: str, title: str):
    return f"https://www.youtube.com/results?search_query={quote_plus((artist+' '+title).strip())}"

def _pick_k(items: list[dict], k: int) -> list[dict]:
    if not items:
        return []
    if len(items) <= k:
        random.shuffle(items)
        return items
    return random.sample(items, k)

async def resolve_artist(name: str) -> str | None:
    try:
        data = await _get_json({"method": "artist.search", "artist": name, "limit": "1"})
        matches = (data or {}).get("results", {}).get("artistmatches", {}).get("artist", []) or []
        if matches:
            # Last.fm returns canonical name in 'name'
            return matches[0].get("name")
        return None
    except Exception:
        return None

async def recommend_by_tag(tag: str, k: int, pool: int = 40):     
    try:
        data = await _get_json({"method": "tag.gettoptracks", "tag": tag, "limit": str(pool)})
        tracks = (data or {}).get("tracks", {}).get("track", []) or []
        items = [
            {"artist": t.get("artist", {}).get("name", "Unknown"),
             "title": t.get("name", "Unknown"),
             "youtube": _yt_link(t.get("artist", {}).get("name",""), t.get("name",""))}
            for t in tracks
        ]
        return _pick_k(items, k)
    except Exception:
        return []

async def recommend_by_track_search(query: str, k: int, pool: int = 30):
    try:
        data = await _get_json({"method": "track.search", "track": query, "limit": str(pool)})
        matches = (data or {}).get("results", {}).get("trackmatches", {}).get("track", []) or []
        items = [
            {"artist": t.get("artist", "Unknown"),
             "title": t.get("name", "Unknown"),
             "youtube": _yt_link(t.get("artist",""), t.get("name",""))}
            for t in matches
        ]
        return _pick_k(items, k)
    except Exception:
        return []

async def recommend_similar_to_artist(artist: str, k: int, pool_artists: int = 20):
    artist = await resolve_artist(artist) or artist
    """artist.getSimilar → sample similar artists → take 1 top track from each until k."""
    try:
        data = await _get_json({"method": "artist.getsimilar", "artist": artist, "limit": str(pool_artists)})
        sims = (data or {}).get("similarartists", {}).get("artist", []) or []
        random.shuffle(sims)  # vary which similar artists we use
        results = []
        async with httpx.AsyncClient(timeout=15) as client:
            for a in sims:
                name = a.get("name")
                if not name:
                    continue
                try:
                    r = await client.get(
                        BASE,
                        params={"method":"artist.gettoptracks", "artist": name, "limit":"3",   # small pool
                                "api_key": LASTFM_API_KEY, "format":"json"}
                    )
                    r.raise_for_status()
                    top = (r.json().get("toptracks", {}).get("track", []) or [])
                    if top:
                        # pick one random top track for this similar artist
                        choice = random.choice(top)
                        title = choice.get("name", "Unknown")
                        results.append({"artist": name, "title": title, "youtube": _yt_link(name, title)})
                        if len(results) >= k:
                            break
                except Exception:
                    continue
        return results
    except Exception:
        return []

async def recommend_artist_top(artist: str, k: int, pool: int = 25):
    artist = await resolve_artist(artist) or artist
    try:
        data = await _get_json({"method": "artist.gettoptracks", "artist": artist, "limit": str(pool)})
        tracks = (data or {}).get("toptracks", {}).get("track", []) or []
        items = [
            {"artist": artist,
             "title": t.get("name", "Unknown"),
             "youtube": _yt_link(artist, t.get("name",""))}
            for t in tracks
        ]
        return _pick_k(items, k)
    except Exception:
        return []

async def get_tracks_for_intent(parsed, limit: int = 5):
    """Randomized selection from a larger pool for variety."""
    if not LASTFM_API_KEY:
        return []
    match parsed.intent:
        case "vibe" | "mood":
            return await recommend_by_tag(parsed.vibe, k=limit, pool=40)
        case "track":
            q = f"{parsed.artist} {parsed.title}".strip() if parsed.artist and parsed.title else (parsed.title or "")
            return await recommend_by_track_search(q, k=limit, pool=30)
        case "artist_like":
            return await recommend_similar_to_artist(parsed.artist, k=limit, pool_artists=20)
        case "artist_top":
            return await recommend_artist_top(parsed.artist, k=limit, pool=25)
        case _:
            return await recommend_by_track_search(parsed.title or "", k=limit, pool=30)