import logging
import asyncio
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F, types
from aiogram.types import (
    Message, CallbackQuery, LabeledPrice, PreCheckoutQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.middleware import BaseMiddleware
import time

import config
from database import (
    init_db, upsert_user, get_active_subscription,
    add_subscription, count_users, count_new_users_today,
    count_active_subscriptions, deactivate_subscription,
    get_user_by_id, create_payment, update_payment_status,
    get_expired_subscriptions
)
from xui_client import xui
import payments

# Rate limiting middleware
class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, rate_limit=1):
        self.rate_limit = rate_limit
        self.user_last_time = {}

    async def __call__(self, handler, event, data):
        user_id = getattr(event.from_user, 'id', None)
        if user_id:
            now = time.time()
            last_time = self.user_last_time.get(user_id, 0)
            if now - last_time < self.rate_limit:
                return  # Ignore the event
            self.user_last_time[user_id] = now
        return await handler(event, data)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Rate limiting
dp.message.middleware(RateLimitMiddleware(rate_limit=1))

async def cleanup_expired_subscriptions():
    """Background task to deactivate expired subscriptions."""
    while True:
        try:
            expired_subs = get_expired_subscriptions()
            for sub in expired_subs:
                # Deactivate in DB
                deactivate_subscription(sub['telegram_id'])
                # Delete from 3x-ui
                try:
                    xui.delete_client(sub['client_id'])
                except Exception as e:
                    log.error(f"Failed to delete client {sub['client_id']}: {e}")
            if expired_subs:
                log.info(f"Deactivated {len(expired_subs)} expired subscriptions")
            await asyncio.sleep(3600)  # every hour
        except Exception as e:
            log.error(f"Error in cleanup: {e}")
            await asyncio.sleep(60)

# --- FSM States ---
class Purchase(StatesGroup):
    choosing_tariff = State()
    choosing_method = State()

# --- Keyboards ---
def get_main_kb(user_id):
    buttons = [
        [KeyboardButton(text="🚀 Моя подписка")],
        [KeyboardButton(text="💳 Купить подписку")],
        [KeyboardButton(text="❓ Помощь")]
    ]
    if user_id in config.ADMIN_IDS:
        buttons.append([KeyboardButton(text="📊 Админ-панель")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_tariffs_kb():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Пробный период (3 дня)", callback_data="tariff_trial")],
        [InlineKeyboardButton(text=config.PLANS["1m"]["label"], callback_data="tariff_1m")],
        [InlineKeyboardButton(text=config.PLANS["3m"]["label"], callback_data="tariff_3m")],
        [InlineKeyboardButton(text=config.PLANS["6m"]["label"], callback_data="tariff_6m")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_purchase")]
    ])
    return kb

def get_payment_methods_kb(tariff_id):
    buttons = []
    if config.USE_TELEGRAM_STARS:
        buttons.append([InlineKeyboardButton(text="⭐ Telegram Stars", callback_data=f"pay_stars_{tariff_id}")])
    if config.YOOKASSA_SHOP_ID:
        buttons.append([InlineKeyboardButton(text="💳 ЮKassa (Карты, СБП)", callback_data=f"pay_yookassa_{tariff_id}")])
    if config.CRYPTOPAY_TOKEN:
        buttons.append([InlineKeyboardButton(text="💎 CryptoPay (USDT, TON)", callback_data=f"pay_crypto_{tariff_id}")])
    
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_tariffs")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- Handlers ---
@dp.message(CommandStart())
async def cmd_start(message: Message):
    upsert_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    await message.answer(
        f"Привет, {message.from_user.first_name}! 👋\n"
        "Я помогу тебе получить доступ к быстрому и безопасному VPN.\n\n"
        "Нажми 'Купить подписку', чтобы начать.",
        reply_markup=get_main_kb(message.from_user.id)
    )

@dp.message(F.text == "🚀 Моя подписка")
async def show_subscription(message: Message):
    sub = get_active_subscription(message.from_user.id)
    if sub:
        expiry = datetime.fromisoformat(sub['expire_at']).strftime('%d.%m.%Y %H:%M')
        await message.answer(
            "✅ У вас есть активная подписка!\n\n"
            f"📅 Истекает: {expiry}\n"
            f"🔗 Ваша ссылка:\n<code>{sub['subscription_url']}</code>\n\n"
            "Скопируйте ссылку и добавьте её в v2rayNG или Shadowrocket.",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "❌ У вас пока нет активной подписки.\n"
            "Нажмите 'Купить подписку', чтобы получить доступ."
        )

@dp.message(F.text == "💳 Купить подписку")
async def start_purchase(message: Message, state: FSMContext):
    await state.set_state(Purchase.choosing_tariff)
    await message.answer("Выберите подходящий тариф:", reply_markup=get_tariffs_kb())

@dp.callback_query(F.data.startswith("tariff_"))
async def process_tariff(callback: CallbackQuery, state: FSMContext):
    tariff_id = callback.data.replace("tariff_", "")
    
    if tariff_id == "trial":
        # Проверка, был ли уже пробный период
        # (Упрощенно: просто выдаем)
        await callback.message.edit_text("⏳ Создаем ваш пробный доступ...")
        await create_sub_and_notify(callback.from_user.id, 3, "Trial")
        await state.clear()
        return

    await state.update_data(tariff=tariff_id)
    await state.set_state(Purchase.choosing_method)
    await callback.message.edit_text(
        f"Вы выбрали тариф: {tariff_id.replace('_', ' ')}\n"
        "Выберите способ оплаты:",
        reply_markup=get_payment_methods_kb(tariff_id)
    )

@dp.callback_query(F.data.startswith("pay_"))
async def process_payment(callback: CallbackQuery, state: FSMContext):
    data = callback.data.split("_")
    method = data[1]
    tariff_id = "_".join(data[2:])
    
    plan = config.PLANS.get(tariff_id)
    if not plan:
        await callback.answer("Неверный тариф")
        return
    
    amount = plan["price"] if method == "yookassa" else plan["stars"]
    days = plan["days"]
    
    if method == "stars":
        # Оплата через Telegram Stars
        await callback.message.answer_invoice(
            title=f"Подписка VPN ({tariff_id})",
            description=f"Доступ на {days} дней",
            payload=f"pay_stars_{callback.from_user.id}_{days}",
            currency="XTR",
            prices=[LabeledPrice(label="Оплата", amount=amount)]
        )
    elif method == "yookassa":
        # Оплата через ЮKassa
        payment = payments.create_yookassa_payment(amount, f"Подписка {days} дней", "https://t.me/your_bot")  # replace with actual bot url
        if payment:
            payment_url = payment["confirmation_url"]
            payment_id = payment["id"]
            create_payment(callback.from_user.id, tariff_id, amount, "RUB", "yookassa")
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Перейти к оплате", url=payment_url)],
                [InlineKeyboardButton(text="Проверить оплату", callback_data=f"check_yoo_{payment_id}_{days}")]
            ])
            await callback.message.answer("Оплатите счет по ссылке ниже:", reply_markup=kb)
        else:
            await callback.message.answer("Ошибка при создании счета. Попробуйте другой способ.")
    
    elif method == "crypto":
        # Оплата через CryptoPay
        # (Упрощенно: в рублях по курсу или просто фикс)
        invoice = await payments.create_cryptopay_invoice(amount/100, f"VPN {days} days")
        if invoice:
            create_payment(callback.from_user.id, tariff_id, int(amount), "USDT", "cryptopay")
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Оплатить в CryptoBot", url=invoice["bot_invoice_url"])],
                [InlineKeyboardButton(text="Проверить оплату", callback_data=f"check_crypto_{invoice['invoice_id']}_{days}")]
            ])
            await callback.message.answer("Оплатите счет через CryptoBot:", reply_markup=kb)
    
    await callback.answer()
    await state.clear()

@dp.pre_checkout_query()
async def process_pre_checkout(pre_checkout: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout.id, ok=True)

@dp.message(F.successful_payment)
async def process_successful_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    if payload.startswith("pay_stars_"):
        _, _, user_id, days = payload.split("_")
        await create_sub_and_notify(int(user_id), int(days), "Stars")

@dp.callback_query(F.data.startswith("check_yoo_"))
async def check_yoo_payment(callback: CallbackQuery):
    _, _, payment_id, days = callback.data.split("_")
    status = payments.check_yookassa_payment(payment_id)
    
    if status == "succeeded":
        update_payment_status(payment_id, "completed")
        await callback.message.edit_text("✅ Оплата прошла успешно! Создаем подписку...")
        await create_sub_and_notify(callback.from_user.id, int(days), "YooKassa")
    else:
        await callback.answer("Оплата еще не поступила. Попробуйте позже.", show_alert=True)

@dp.callback_query(F.data.startswith("check_crypto_"))
async def check_crypto_payment(callback: CallbackQuery):
    parts = callback.data.split("_")
    invoice_id = int(parts[2])
    days = int(parts[3]) if len(parts) > 3 else 30
    
    status = await payments.check_cryptopay_invoice(invoice_id)
    
    if status == "paid":
        await callback.message.edit_text("✅ Оплата прошла успешно! Создаем подписку...")
        await create_sub_and_notify(callback.from_user.id, days, "CryptoPay")
    else:
        await callback.answer("Оплата еще не поступила. Попробуйте позже.", show_alert=True)

async def create_sub_and_notify(user_id, days, method):
    expiry_date = (datetime.now() + timedelta(days=days)).isoformat()
    
    # Деактивируем старую подписку если есть
    old_sub = get_active_subscription(user_id)
    if old_sub:
        await xui.delete_client(old_sub['client_id'])
        deactivate_subscription(user_id)

    email = f"user_{user_id}_{int(datetime.now().timestamp())}@bot"
    result = await xui.add_client(email, days, config.DEFAULT_TRAFFIC_GB)
    
    if result:
        client_id = result['client_id']
        sub_url = result['link']
        add_subscription(user_id, client_id, email, expiry_date, config.DEFAULT_TRAFFIC_GB, "custom")
        await bot.send_message(
            user_id,
            f"🎉 Подписка успешно активирована!\n\n"
            f"📅 Срок: {days} дней (через {method})\n"
            f"📅 Истекает: {expiry_date[:16].replace('T', ' ')}\n\n"
            f"🔗 Ваша ссылка:\n<code>{sub_url}</code>",
            parse_mode="HTML"
        )
    else:
        await bot.send_message(user_id, "❌ Произошла ошибка при создании подписки. Обратитесь в поддержку.")

# --- Admin Handlers ---
@dp.message(F.text == "📊 Админ-панель")
async def admin_panel(message: Message):
    if message.from_user.id not in config.ADMIN_IDS: return
    
    stats = (
        "📊 Статистика бота:\n\n"
        f"👥 Всего пользователей: {count_users()}\n"
        f"🆕 Новых сегодня: {count_new_users_today()}\n"
        f"💎 Активных подписок: {count_active_subscriptions()}\n"
    )
    await message.answer(stats)

@dp.message(Command("add_sub"))
async def admin_add_sub(message: Message):
    if message.from_user.id not in config.ADMIN_IDS: return
    # /add_sub user_id days
    try:
        _, user_id, days = message.text.split()
        await create_sub_and_notify(int(user_id), int(days), "Admin")
    except:
        await message.answer("Использование: /add_sub user_id days")

async def main():
    init_db()
    log.info("Starting bot...")
    # Start background cleanup task
    cleanup_task = asyncio.create_task(cleanup_expired_subscriptions())
    try:
        await dp.start_polling(bot)
    finally:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass

if __name__ == "__main__":
    asyncio.run(main())
