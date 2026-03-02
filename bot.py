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

import config
from database import (
    init_db, upsert_user, get_active_subscription,
    add_subscription, count_users, count_new_users_today,
    count_active_subscriptions, deactivate_subscription,
    get_user_by_id, create_payment, update_payment_status
)
from xui_client import xui
import payments

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

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
        [InlineKeyboardButton(text="1 месяц - 300₽", callback_data="tariff_1_month")],
        [InlineKeyboardButton(text="3 месяца - 800₽", callback_data="tariff_3_months")],
        [InlineKeyboardButton(text="6 месяцев - 1400₽", callback_data="tariff_6_months")],
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
        f"Привет, {message.from_user.first_name}! 👋
"
        "Я помогу тебе получить доступ к быстрому и безопасному VPN.

"
        "Нажми 'Купить подписку', чтобы начать.",
        reply_markup=get_main_kb(message.from_user.id)
    )

@dp.message(F.text == "🚀 Моя подписка")
async def show_subscription(message: Message):
    sub = get_active_subscription(message.from_user.id)
    if sub:
        expiry = datetime.fromisoformat(sub['expiry_date']).strftime('%d.%m.%Y %H:%M')
        await message.answer(
            "✅ У вас есть активная подписка!

"
            f"📅 Истекает: {expiry}
"
            f"🔗 Ваша ссылка:
<code>{sub['subscription_url']}</code>

"
            "Скопируйте ссылку и добавьте её в v2rayNG или Shadowrocket.",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "❌ У вас пока нет активной подписки.
"
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
        f"Вы выбрали тариф: {tariff_id.replace('_', ' ')}
"
        "Выберите способ оплаты:",
        reply_markup=get_payment_methods_kb(tariff_id)
    )

@dp.callback_query(F.data.startswith("pay_"))
async def process_payment(callback: CallbackQuery, state: FSMContext):
    data = callback.data.split("_")
    method = data[1]
    tariff_id = "_".join(data[2:])
    
    prices = {
        "1_month": config.PRICE_1_MONTH,
        "3_months": config.PRICE_3_MONTHS,
        "6_months": config.PRICE_6_MONTHS
    }
    days_map = {
        "1_month": 30,
        "3_months": 90,
        "6_months": 180
    }
    
    amount = prices.get(tariff_id, 0)
    days = days_map.get(tariff_id, 30)
    
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
        payment_url, payment_id = payments.create_yookassa_payment(amount, f"Подписка {days} дней")
        if payment_url:
            create_payment(callback.from_user.id, amount, "rub", "yookassa", payment_id)
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
        invoice = await payments.create_crypto_payment(amount/100, "USDT", f"VPN {days} days")
        if invoice:
             create_payment(callback.from_user.id, amount/100, "USDT", "cryptopay", str(invoice.invoice_id))
             kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Оплатить в CryptoBot", url=invoice.bot_invoice_url)],
                [InlineKeyboardButton(text="Проверить оплату", callback_data=f"check_crypto_{invoice.invoice_id}_{days}")]
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

async def create_sub_and_notify(user_id, days, method):
    expiry_date = (datetime.now() + timedelta(days=days)).isoformat()
    
    # Деактивируем старую подписку если есть
    old_sub = get_active_subscription(user_id)
    if old_sub:
        await xui.delete_client(config.XUI_INBOUND_ID, old_sub['client_email'])
        deactivate_subscription(user_id)

    email = f"user_{user_id}_{int(datetime.now().timestamp())}@bot"
    sub_url = await xui.add_client(config.XUI_INBOUND_ID, email, config.DEFAULT_TRAFFIC_GB)
    
    if sub_url:
        add_subscription(user_id, email, sub_url, expiry_date)
        await bot.send_message(
            user_id,
            f"🎉 Подписка успешно активирована!

"
            f"📅 Срок: {days} дней (через {method})
"
            f"📅 Истекает: {expiry_date[:16].replace('T', ' ')}

"
            f"🔗 Ваша ссылка:
<code>{sub_url}</code>",
            parse_mode="HTML"
        )
    else:
        await bot.send_message(user_id, "❌ Произошла ошибка при создании подписки. Обратитесь в поддержку.")

# --- Admin Handlers ---
@dp.message(F.text == "📊 Админ-панель")
async def admin_panel(message: Message):
    if message.from_user.id not in config.ADMIN_IDS: return
    
    stats = (
        "📊 Статистика бота:

"
        f"👥 Всего пользователей: {count_users()}
"
        f"🆕 Новых сегодня: {count_new_users_today()}
"
        f"💎 Активных подписок: {count_active_subscriptions()}
"
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
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
