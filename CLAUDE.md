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
SERVER_AI_TEAM=   # comma-separated guild IDs to scrape
```

## Commands

```bash
# Start the PostgreSQL database (with pgvector extension)
docker compose up -d

# Install dependencies
pip install -r requirements.txt

# Initialize database tables
python3 -m src.database

# Run the one-shot Discord scraper bot
python3 -m src.services.v1.DiscordEchoSaver_v1.echosaverbot_v1

# Run the FastAPI server (API + persistent bot)
uvicorn src.api.main:app --reload

# Run manual API tests (requires server running)
python3 test/api/v1/fetchDiscordApi.py
```

All modules are run as `-m` commands from the project root (not executed directly).

## Architecture

A **Discord message archiving and analysis system** that scrapes servers into PostgreSQL (with pgvector), then chunks messages, generates LLM summaries, creates vector embeddings, and supports BM25 search and knowledge graph extraction.

### Two bot modes

- **One-shot bot** (`services/v1/DiscordEchoSaver_v1/echosaverbot_v1.py`) — runs scraping tasks on `on_ready`, then calls `self.close()`. Scraping methods are commented/uncommented directly in code.
- **Persistent API bot** (`services/v2/DiscordEchoSaver/echosaverbot_v1.py`) — stays connected; scraping is triggered via HTTP requests to the FastAPI server.

### Service versioning

`services/v1/` holds exploratory/experimental implementations; `services/v2/` holds production-ready versions. When both exist, prefer v2.

### Core modules

- `src/settings.py` — loads all env vars via `python-dotenv`, exposes `APP_CONN_STRING`
- `src/models.py` — SQLAlchemy ORM: `DiscordGuild`, `DiscordUser`, `DiscordChannel`, `DiscordMessage`, `DiscordChannelChronologicalSummary` (pgvector `VECTOR(3072)` embedding column)
- `src/database.py` — `CrudHelper` (context-managed sessions) and `get_db()` generator (FastAPI dependency injection)
- `src/logging_config.py` — rotating file logger shared across all services

### Summarization pipeline

1. **Chunk** (`ChronologicalSummary/chunking_messages.py`) — groups messages by weekly time windows; merges windows until each chunk has ≥50 messages
2. **Summarize** (`ChronologicalSummary/summary.py`) — parallel async LLM calls with semaphore; supports Google Generative AI, Groq (`llama-4-maverick-17b-128e-instruct`), and Ollama
3. **Embed** (`ChronologicalSummary/embeddings.py`) — stores results in `DiscordChannelChronologicalSummary` with pgvector embedding
4. Prompts live in `prompts.py` alongside each service

### API endpoints (`src/api/v1/routers/fetchDiscordApi.py`)

Base path: `/fetchdiscord`. All endpoints spawn background tasks and return `202 Accepted`.

- `POST /channels` — sync all channels/threads from guild list
- `POST /users` — sync all members from guild list
- `POST /messages` — recursively sync messages from a channel list

### Additional services

- **Dulcinea** (`services/v1/Dulcineav1/`) — BM25 search ranking over archived messages
- **KnowledgeGraph** (`services/v1/KnowledgeGraph_v1/`) — extracts entities and binary relationships from summaries (outputs structured JSON); uses `neo4j` for storage

### Scraping methods (bot, called from `on_ready`)

- `save_guild_data` — saves server metadata
- `save_channel_data_from_server` — saves all channels/threads (including archived and private threads)
- `save_user_data` — saves all server members
- `recursively_save_messages_from_a_root(root_id)` — traverses a channel tree from a root ID; uses `last_messages_at` on `DiscordChannel` to resume incrementally

### Data model notes

- `DiscordChannel.parent_channel_id` links threads → parent text/forum channels → categories; the recursive message saver traverses this tree.
- `DiscordMessage.user_id`/`user_name` are intentionally **not** foreign keys to `DiscordUser` — messages can exist from users who left the server and are absent from the members list.
