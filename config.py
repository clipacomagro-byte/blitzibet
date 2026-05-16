"""Central config. All env vars loaded here, imported everywhere else."""
import os
from dotenv import load_dotenv

load_dotenv()


def _required(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing required env var: {name}")
    return val


# Telegram
TELEGRAM_BOT_TOKEN = _required("TELEGRAM_BOT_TOKEN")

# Database (Supabase Postgres pooler URI)
DATABASE_URL = _required("DATABASE_URL")

# Sports data (SportMonks). Keeping the var name for backward-compat with old deploys.
API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "")

# Claude AI for signal narratives. If unset, signals still fire — just without AI commentary.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

# Engine tuning
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))
SIGNAL_COOLDOWN_MINUTES = int(os.getenv("SIGNAL_COOLDOWN_MINUTES", "10"))

# Admin
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0")) or None
