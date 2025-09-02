import os,time
import json
import asyncio
import discord
import httpx
from pathlib import Path
from dotenv import load_dotenv
from simple_sse_client import async_stream

# Load .env from the same folder as this file 
ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(dotenv_path=ENV_PATH)

TOKEN = (os.getenv("DISCORD_TOKEN") or "").strip()
AGENT_URL = (os.getenv("AGENT_URL") or "").strip()

# Fallback if AGENT_URL missing/invalid
if not AGENT_URL.lower().startswith(("http://", "https://")):
    AGENT_URL = "http://127.0.0.1:8000/assist"

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)


def new_ulid() -> str:
    # ULID generator 
    t = int(time.time() * 1000).to_bytes(6, "big")
    r = os.urandom(10)
    data = int.from_bytes(t + r, "big")
    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    out = []
    for _ in range(26):
        out.append(alphabet[data & 31])
        data >>= 5
    return "".join(reversed(out))


# --- Agent streaming helper --------------------------------------------------

async def ask_agent(prompt: str, user_id: str | None = None, conversation_id: str | None = None):
    """
    Stream events from /assist using httpx directly.
    Parse minimal SSE: lines starting with 'event:' and 'data:'.
    Always returns {plan_text, links, final_text} with safe fallbacks.
    """
    plan_chunks, links, final_chunks = [], [], []

    buf_session = {
    "processor_id": new_ulid(),
    "activity_id": new_ulid(),
    "request_id": new_ulid(),
    "conversation_id": conversation_id or new_ulid(),
    "client": "discord-bot",
    "interactions": [],
}
    if user_id:
        buf_session["user_id"] = user_id

    buffer = {
        "query": {
            "id": new_ulid(),
            "prompt": prompt
        },
        "session": buf_session
    }
    payload = json.dumps(buffer)

    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }


    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", AGENT_URL, headers=headers, content=payload) as resp:
                ctype = resp.headers.get("content-type", "")

                if "text/event-stream" not in ctype:
                    # read body BEFORE leaving the context; stream is still open here
                    text = await resp.aread()
                    try:
                        snippet = text.decode("utf-8", errors="replace")
                    except Exception:
                        snippet = repr(text)
                    plan_chunks.append(f"**ERROR:** agent returned {resp.status_code} {ctype}:\n{snippet}")
                else:
                    current_event = None
                    current_data_parts = []

                    async for line in resp.aiter_lines():
                        if line is None:
                            continue
                        line = line.rstrip("\r\n")

                        if line.startswith(":"):
                            continue

                        if line.startswith("event:"):
                            # flush any previous block first
                            if current_data_parts:
                                #used for debugging
                                #print("[SSE data]", ("\n".join(current_data_parts))[:300])
                                _process_event(
                                    current_event or "message",
                                    "\n".join(current_data_parts),
                                    plan_chunks, final_chunks, links
                                )
                                current_data_parts = []
                            current_event = line[len("event:"):].strip()
                            continue

                        if line.startswith("data:"):
                            current_data_parts.append(line[len("data:"):].strip())
                            continue

                        if line == "":
                            # blank line => dispatch even if no 'event:' header was seen
                            if current_data_parts:
                                #used for debugging
                                #print("[SSE data]", ("\n".join(current_data_parts))[:300])
                                _process_event(
                                    current_event or "message",
                                    "\n".join(current_data_parts),
                                    plan_chunks, final_chunks, links
                                )
                            current_event, current_data_parts = None, []
                            continue

                    # flush tail
                    if current_data_parts:
                        #used for debugging
                        #print("[SSE data]", ("\n".join(current_data_parts))[:300])
                        _process_event(
                            current_event or "message",
                            "\n".join(current_data_parts),
                            plan_chunks, final_chunks, links
                        )

    except Exception as e:
        plan_chunks.append(f"**ERROR:** agent unavailable ({e}).")

    plan_text = "\n".join(plan_chunks).strip()
    final_text = "".join(final_chunks).strip()

    if not links:
        # safe fallback if we hit with any errors so we still have something to show
        links = [
            {"artist": "The Weeknd", "title": "Blinding Lights",
             "youtube": "https://www.youtube.com/results?search_query=The+Weeknd+Blinding+Lights"},
            {"artist": "ODESZA", "title": "A Moment Apart",
             "youtube": "https://www.youtube.com/results?search_query=ODESZA+A+Moment+Apart"},
            {"artist": "Daft Punk", "title": "Instant Crush",
             "youtube": "https://www.youtube.com/results?search_query=Daft+Punk+Instant+Crush"},
        ]

    return {"plan_text": plan_text, "links": links, "final_text": final_text}


def _process_event(ev_type: str, data_str: str, plan_chunks: list, final_chunks: list, links_ref: list):
    """
    Handles Sentient 'atomic'/'chunked' schema:
      - atomic.textblock  + event_name: PLAN/WARNING/ERROR  -> content: str
      - atomic.json       + event_name: SOURCES             -> content: {"links":[...]}
      - chunked.text      + event_name: FINAL_RESPONSE      -> content: "..." (streamed), is_complete flag
    Also tolerates older shapes (eventType/payload) if present.
    """
    import json as _json

    try:
        obj = _json.loads(data_str)
    except _json.JSONDecodeError:
        return

    # Primary fields for  server
    ct = (obj.get("content_type") or "").lower()
    en = (obj.get("event_name") or ev_type or "").upper()
    content = obj.get("content")

    # Fallbacks for older/other shapes
    if not en and obj.get("eventType"):
        en = str(obj.get("eventType")).upper()
    if content is None and obj.get("payload") is not None:
        payload = obj.get("payload") or {}
        # try typical payload keys
        if isinstance(payload, dict):
            if "text" in payload or "content" in payload:
                content = payload.get("text") or payload.get("content")
            elif "json" in payload:
                content = payload.get("json")
            elif "data" in payload:
                content = payload.get("data")

    # --- PLAN / WARNING / ERROR (text block) ---
    if en in {"PLAN", "WARNING", "ERROR"}:
        if isinstance(content, str) and content.strip():
            plan_chunks.append(f"**{en}:** {content.strip()}")
        return

    # --- SOURCES (json block) ---
    if en == "SOURCES":
        # expected shape for your server: content = {"links":[...]}
        links = None
        if isinstance(content, dict) and isinstance(content.get("links"), list):
            links = content.get("links")
        # tolerate alt locations (older shapes)
        if links is None and isinstance(content, list):
            links = content
        if links is not None:
            links_ref.clear()
            links_ref.extend(links)
        return

    # --- FINAL_RESPONSE (streamed text) ---
    if en == "FINAL_RESPONSE":
        if isinstance(content, str) and content:
            final_chunks.append(content)
        return

    # ignore 'done' and other atomic.* or chunked.* you don't use
    return


def format_links(links: list[dict], limit: int = 5) -> str:
    out = []
    for s in links[:limit]:
        artist = s.get("artist", "Unknown")
        title = s.get("title", "Unknown")
        url = (
            s.get("youtube")
            or s.get("url")
            or "https://www.youtube.com"
        )
        out.append(f"- **{artist} — {title}**\n{url}")
    return "\n".join(out)

# --- Discord events ----------------------------------------------------------

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (id: {bot.user.id})")
    print("AGENT_URL =", repr(AGENT_URL))

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    content = (message.content or "").strip()

    # Quick commands that don't hit the agent
    lower = content.lower()
    if lower in {"hi", "hello", "hey"}:
        await message.channel.send(
            "hi! what kind of music you want to listen today?\n"
            "you can tell me a vibe (e.g., workout, chill), a mood (e.g., i am sad), "
            "an artist (e.g., like drake), or a track (e.g., tarkan - şımarık)."
        )
        return

    if lower.startswith("!ping"):
        await message.channel.send("pong 🏓")
        return

    # Everything else → forward to agent
    async with message.channel.typing():
        result = await ask_agent(
        content,
        user_id=str(message.author.id),
        conversation_id=str(message.channel.id),
            )
        plan_text = result["plan_text"] or "*working on it…*"
        suggestions = format_links(result["links"], limit=5)

        # Keep each message under Discord’s 2000-char limit
        chunks = []
        body = f"**Plan**\n{plan_text}\n\n**Suggestions**\n{suggestions}"
        if len(body) <= 1900:
            chunks = [body]
        else:
            # crude split if needed
            mid = body.find("\n\n**Suggestions**")
            chunks = [body[:mid], body[mid:]]

        for c in chunks:
            await message.channel.send(c)

bot.run(TOKEN)
