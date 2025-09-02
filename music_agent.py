from sentient_agent_framework import AbstractAgent, DefaultServer, Session, Query, ResponseHandler
from dotenv import load_dotenv
import os, traceback

from parser import parse_prompt                
from lastfm import get_tracks_for_intent    

load_dotenv()

FALLBACK = [
    {"artist": "The Weeknd", "title": "Blinding Lights",
     "youtube": "https://www.youtube.com/results?search_query=The+Weeknd+Blinding+Lights"},
    {"artist": "ODESZA", "title": "A Moment Apart",
     "youtube": "https://www.youtube.com/results?search_query=ODESZA+A+Moment+Apart"},
    {"artist": "Daft Punk", "title": "Instant Crush",
     "youtube": "https://www.youtube.com/results?search_query=Daft+Punk+Instant+Crush"},
]
_last_seen: dict[str, set[tuple[str, str]]] = {}

class MusicAgent(AbstractAgent):
    def __init__(self):
        super().__init__("MusicAgent")

    async def assist(self, session: Session, query: Query, response_handler: ResponseHandler):
        async def safe_complete():
            try:
                await response_handler.complete()
            except Exception:
                pass

        try:
            raw = (query.prompt or "").strip() or "workout"
            parsed = parse_prompt(raw)

            # Greeting → friendly reply and stop (no API calls)
            if parsed.intent == "greeting":
                await response_handler.emit_text_block("PLAN", "Greeting detected.")
                await response_handler.emit_json("SOURCES", {"links": []})
                stream = response_handler.create_text_stream("FINAL_RESPONSE")
                await stream.emit_chunk(
                    "hi! what kind of music you want to listen today?\n"
                    "you can tell me a vibe (e.g., workout, chill), a mood (e.g., i am sad), "
                    "an artist (e.g., like drake), or a track (e.g., tarkan - şımarık).\n"
                )
                await stream.complete()
                await response_handler.complete()
                return

            # Build a PLAN message that is always defined
            plan_str = ""
            if parsed.intent == "mood":
                plan_str = f"Mood detected: {parsed.mood}. Using vibe '{parsed.vibe}'."
            elif parsed.intent == "vibe":
                plan_str = f"Interpreting '{raw}' as a vibe/tag. Fetching tracks for '{parsed.vibe}'."
            elif parsed.intent == "track":
                if parsed.artist and parsed.title:
                    plan_str = f"Interpreting as track query: {parsed.artist} — {parsed.title}. Searching related tracks."
                else:
                    plan_str = f"Interpreting as generic track search: '{parsed.title}'."
            elif parsed.intent == "artist_like":
                plan_str = f"Interpreting as 'similar to {parsed.artist}'. Fetching similar artists and top tracks."
            elif parsed.intent == "artist_top":
                plan_str = f"Interpreting as 'top tracks by {parsed.artist}'. Resolving artist name if misspelled."
            else:
                plan_str = f"Searching for recommendations for '{raw}'."

            await response_handler.emit_text_block("PLAN", plan_str)

            # Warn if key missing (won’t crash thanks to fallbacks)
            import os
            if not os.getenv("LASTFM_API_KEY"):
                await response_handler.emit_text_block("WARNING", "LASTFM_API_KEY not found; using fallback.")

            # Fetch suggestions (handles mood→vibe, fuzzy artists)
            suggestions = await get_tracks_for_intent(parsed, limit=5)
            if not suggestions:
                suggestions = FALLBACK

            # Emit sources + streamed list
            await response_handler.emit_json("SOURCES", {"links": suggestions})

            stream = response_handler.create_text_stream("FINAL_RESPONSE")
            await stream.emit_chunk("Here are some picks:\n")
            for s in suggestions:
                await stream.emit_chunk(f"- {s['artist']} — {s['title']}\n")
            await stream.complete()
            await safe_complete()

        except Exception as e:
            # Never leak a traceback into SSE
            await response_handler.emit_text_block("ERROR", "Unexpected error. Showing safe defaults.")
            print("MusicAgent error:", e)
            import traceback; traceback.print_exc()

            await response_handler.emit_json("SOURCES", {"links": FALLBACK})
            stream = response_handler.create_text_stream("FINAL_RESPONSE")
            await stream.emit_chunk("Here are some picks:\n")
            for s in FALLBACK:
                await stream.emit_chunk(f"- {s['artist']} — {s['title']}\n")
            await stream.complete()
            await safe_complete()

if __name__ == "__main__":
    server = DefaultServer(MusicAgent())
    server.run()
