# SentientMusicAgent
That agent helps you to use Sentient Agent Framework. It is using last.fm to get the music name and suggestions. It will give you the top youtube search as answer.


# 🎵 MusicAgentBot

A Discord bot + local server that suggests music based on vibe, mood, or artist.  
It connects to [Last.fm](https://www.last.fm/) for music search and streams responses using the [Sentient Agent Framework](https://pypi.org/project/sentient-agent-framework/).

---

## ✨ Features
- Ask for music by **vibe** (`workout`, `chill`, …)
- Ask by **mood** (`I am sad`, `I feel happy`, …)
- Ask by **artist or track** (`like Drake`, `top track by Katy Perry`)
- Randomized suggestions (so you don’t get the same list every time)
- Works 24/7 on Ubuntu via `systemd`
- Built with:
  - Python 3.12+
  - `discord.py`
  - `httpx`
  - `sentient-agent-framework`
  - `python-dotenv`

---

## ⚡ Quick Start (Local Testing)

### 1. Clone and enter the project
```bash
git clone https://github.com/YOUR_USERNAME/musicagent-bot.git
cd musicagent-bot
```

### 2. Create a virtual environment
# For the server:
```bash
python3 -m venv server/.venv
source server/.venv/bin/activate
pip install -U pip
pip install sentient-agent-framework httpx python-dotenv uvicorn
deactivate
```

# For the bot:
```bash
python3 -m venv bot/.venv
source bot/.venv/bin/activate
pip install -U pip
pip install discord.py httpx python-dotenv
deactivate
```
### 3. Create your .env

# .env files
```bash
DISCORD_TOKEN=your_discord_bot_token_here
LASTFM_API_KEY=your_lastfm_api_key_here
AGENT_URL=http://127.0.0.1:8000/assist
```
### 4. Run locally
# In one terminal, run the server:
```bash
cd server
source .venv/bin/activate
python ../music_agent.py
```
# In another terminal, run the bot:
```bash
cd bot
source .venv/bin/activate
python ../bot.py
```

# Try commands in Discord:

```dif 
!ping
```
```dif
hi
```
```dif
workout
```
