import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# Admin Telegram IDs (comma-separated in .env)
ADMIN_IDS_RAW = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_RAW.split(",") if x.strip()]

# 3x-ui Panel
XUI_HOST = os.getenv("XUI_HOST", "http://YOUR_SERVER_IP:2053")
XUI_USERNAME = os.getenv("XUI_USERNAME", "admin")
XUI_PASSWORD = os.getenv("XUI_PASSWORD", "admin")
XUI_INBOUND_ID = int(os.getenv("XUI_INBOUND_ID", "1"))

# Default subscription settings
DEFAULT_TRAFFIC_GB = int(os.getenv("DEFAULT_TRAFFIC_GB", "50"))  # GB
DEFAULT_DAYS = int(os.getenv("DEFAULT_DAYS", "30"))  # days

# Database
DB_PATH = os.getenv("DB_PATH", "bot.db")
