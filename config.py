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

# Database
DB_PATH = os.getenv("DB_PATH", "bot.db")

# Default traffic per subscription (GB)
DEFAULT_TRAFFIC_GB = int(os.getenv("DEFAULT_TRAFFIC_GB", "50"))

# ── Payment providers ──────────────────────────────────────────────────────────
# Telegram Payments (Stars or provider token)
# Get from @BotFather -> Payments
PAYMENT_PROVIDER_TOKEN = os.getenv("PAYMENT_PROVIDER_TOKEN", "")  # empty = Telegram Stars

# YooKassa (ЮKassa)
YOOKASSA_SHOP_ID  = os.getenv("YOOKASSA_SHOP_ID", "")
YOOKASSA_SECRET   = os.getenv("YOOKASSA_SECRET", "")

# CryptoPay (https://t.me/CryptoBot)
CRYPTO_PAY_TOKEN  = os.getenv("CRYPTO_PAY_TOKEN", "")
CRYPTO_PAY_NET    = os.getenv("CRYPTO_PAY_NET", "mainnet")  # or "testnet"

# Active payment method: "stars" | "yookassa" | "cryptopay" | "manual"
PAYMENT_METHOD = os.getenv("PAYMENT_METHOD", "stars")

# Use Telegram Stars
USE_TELEGRAM_STARS = os.getenv("USE_TELEGRAM_STARS", "true").lower() == "true"

# ── Subscription plans ────────────────────────────────────────────────────────
# Format: id -> {days, price, label, traffic_gb}
PLANS = {
    "trial": {
        "days": 3,
        "price": 0,          # free
        "stars": 0,
        "label": "🆓 Пробный — 3 дня (бесплатно)",
        "short": "3 дня",
        "traffic_gb": 5,
    },
    "1m": {
        "days": 30,
        "price": 199,        # RUB (for YooKassa)
        "stars": 100,        # Telegram Stars
        "label": "1 месяц — 199 ₽",
        "short": "1 месяц",
        "traffic_gb": 50,
    },
    "3m": {
        "days": 90,
        "price": 499,
        "stars": 250,
        "label": "3 месяца — 499 ₽  (скидка 16%)",
        "short": "3 месяца",
        "traffic_gb": 150,
    },
    "6m": {
        "days": 180,
        "price": 899,
        "stars": 450,
        "label": "6 месяцев — 899 ₽  (скидка 25%)",
        "short": "6 месяцев",
        "traffic_gb": 300,
    },
}

# Legacy price vars (for backward compatibility)
PRICE_1_MONTH = PLANS["1m"]["price"]
PRICE_3_MONTHS = PLANS["3m"]["price"]
PRICE_6_MONTHS = PLANS["6m"]["price"]
