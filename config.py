import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Bot configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # Default to 0 if not set

# Database configuration
DB_URI = os.environ.get("DATABASE_URL")
DB_PATH = "bot_database.db"  # SQLite fallback if PostgreSQL not configured

# Automation settings
RETRY_LIMIT = 3
PROXY_TIMEOUT = 30  # seconds
MAX_ACCOUNTS_IN_QUEUE = 100
CARD_CHECK_INTERVAL = 5  # seconds

# BIN list file
BIN_LIST_PATH = "bins_all.csv"

# Session settings
SESSION_PATH = "sessions"