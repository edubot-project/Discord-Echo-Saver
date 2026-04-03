# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

Requires a `.env` file with:
```
DB_USER=
DB_PASS=
DB_HOST=
DB_PORT=
DB_NAME=
DISCORD_BOT_TOKEN=
DULCINEA_DISCORD_BOT_TOKEN=
GOOGLE_API_KEY=
GROQ_API_KEY=
```

## Commands

```bash
# Start the PostgreSQL database (with pgvector extension)
docker compose up -d

# Install dependencies
pip install -r requirements.txt

# Initialize database tables
python3 -m src.database

# Run the Discord bot
python3 -m src.services.DiscordEchoSaver_v1.echosaverbot_v1
```

All modules are run as `-m` commands from the project root (not executed directly).

## Architecture

This is a **Discord message archiving bot** that scrapes and stores Discord server data into PostgreSQL with pgvector support (for future embedding/RAG use).

**Data flow:**
1. `DiscordEchoSaverBot` (a `discord.Client` subclass) connects to Discord on `on_ready`
2. It runs one-shot scraping tasks then calls `self.close()` — it is not a persistent listener
3. Scraped data is written to PostgreSQL via SQLAlchemy ORM

**Module responsibilities:**
- `src/settings.py` — loads all env vars via `python-dotenv`, exposes `APP_CONN_STRING`
- `src/models.py` — SQLAlchemy ORM models: `DiscordGuild`, `DiscordUser`, `DiscordChannel`, `DiscordMessage`, `DiscordChannelChronologicalSummary` (with `pgvector` embedding column)
- `src/database.py` — provides `CrudHelper` (context-managed sessions) and `get_db()` generator (FastAPI-style dependency injection, for future use)
- `src/services/DiscordEchoSaver_v1/echosaverbot_v1.py` — the bot itself

**Bot scraping methods (called from `on_ready`, comment/uncomment as needed):**
- `save_guild_data` — saves server metadata
- `save_channel_data_from_server` — saves all channels/threads (including archived and private threads)
- `save_user_data` — saves all server members
- `recursively_save_messages_from_a_root(root_id)` — traverses a channel tree from a root ID and saves all messages; uses `last_messages_at` on `DiscordChannel` to resume incrementally

**Channel hierarchy in DB:** `DiscordChannel.parent_channel_id` links threads to their parent text/forum channels and channels to their parent category. The recursive message saver traverses this tree.

**`DiscordMessage` note:** `user_id`/`user_name` are not foreign keys to `DiscordUser` — the comment in models.py explains this is intentional (messages can exist from users not in the members list).
