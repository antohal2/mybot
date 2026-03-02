"""
Payment provider integrations for mybot.
Supported methods:
- Telegram Stars (built-in)
- YooKassa (ЮKassa)
- CryptoPay (crypto)
"""
import logging
from config import (
    PAYMENT_METHOD, PAYMENT_PROVIDER_TOKEN,
    YOOKASSA_SHOP_ID, YOOKASSA_SECRET,
    CRYPTO_PAY_TOKEN, CRYPTO_PAY_NET
)

log = logging.getLogger(__name__)


# ── Telegram Stars / Native Payments ───────────────────────────────────────────────

def create_stars_invoice(plan_id: str, label: str, stars: int) -> dict:
    """
    Create Telegram Stars invoice.
    Returns: {"title", "description", "payload", "currency", "prices"}
    """
    return {
        "title": label,
        "description": f"VPN подписка: {label}",
        "payload": f"plan_{plan_id}",
        "currency": "XTR",  # Telegram Stars currency code
        "prices": [{"label": label, "amount": stars}],
        "provider_token": PAYMENT_PROVIDER_TOKEN or "",  # empty = Stars
    }


# ── YooKassa ──────────────────────────────────────────────────────────────────

try:
    from yookassa import Configuration, Payment as YKPayment
    Configuration.account_id = YOOKASSA_SHOP_ID
    Configuration.secret_key = YOOKASSA_SECRET
    YOOKASSA_AVAILABLE = bool(YOOKASSA_SHOP_ID and YOOKASSA_SECRET)
except ImportError:
    YOOKASSA_AVAILABLE = False
    log.warning("yookassa library not installed. Run: pip install yookassa")


def create_yookassa_payment(amount_rub: int, description: str, return_url: str) -> dict:
    """
    Create YooKassa payment.
    Returns: {"id", "confirmation_url", "status"}
    """
    if not YOOKASSA_AVAILABLE:
        raise ValueError("YooKassa not configured")
    
    payment = YKPayment.create({
        "amount": {"value": f"{amount_rub}.00", "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": return_url},
        "capture": True,
        "description": description,
    })
    return {
        "id": payment.id,
        "confirmation_url": payment.confirmation.confirmation_url,
        "status": payment.status,
    }


def check_yookassa_payment(payment_id: str) -> str:
    """Check YooKassa payment status. Returns: 'pending' | 'succeeded' | 'canceled'"""
    if not YOOKASSA_AVAILABLE:
        return "error"
    payment = YKPayment.find_one(payment_id)
    return payment.status


# ── CryptoPay ─────────────────────────────────────────────────────────────────────

try:
    from aiocryptopay import AioCryptoPay, Networks
    CRYPTOPAY_AVAILABLE = bool(CRYPTO_PAY_TOKEN)
except ImportError:
    CRYPTOPAY_AVAILABLE = False
    log.warning("aiocryptopay library not installed. Run: pip install aiocryptopay")


async def create_cryptopay_invoice(amount_usdt: float, description: str) -> dict:
    """
    Create CryptoPay invoice.
    Returns: {"invoice_id", "bot_invoice_url", "mini_app_invoice_url"}
    """
    if not CRYPTOPAY_AVAILABLE:
        raise ValueError("CryptoPay not configured")
    
    network = Networks.MAIN_NET if CRYPTO_PAY_NET == "mainnet" else Networks.TEST_NET
    crypto = AioCryptoPay(token=CRYPTO_PAY_TOKEN, network=network)
    
    invoice = await crypto.create_invoice(
        asset="USDT",
        amount=amount_usdt,
        description=description,
    )
    await crypto.close()
    
    return {
        "invoice_id": invoice.invoice_id,
        "bot_invoice_url": invoice.bot_invoice_url,
        "mini_app_invoice_url": invoice.mini_app_invoice_url,
        "status": invoice.status,
    }


async def check_cryptopay_invoice(invoice_id: int) -> str:
    """Check CryptoPay invoice status. Returns: 'active' | 'paid' | 'expired'"""
    if not CRYPTOPAY_AVAILABLE:
        return "error"
    network = Networks.MAIN_NET if CRYPTO_PAY_NET == "mainnet" else Networks.TEST_NET
    crypto = AioCryptoPay(token=CRYPTO_PAY_TOKEN, network=network)
    invoices = await crypto.get_invoices(invoice_ids=invoice_id)
    await crypto.close()
    if invoices:
        return invoices[0].status
    return "not_found"
