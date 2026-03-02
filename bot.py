import logging
import asyncio
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, ADMIN_IDS, DEFAULT_TRAFFIC_GB, DEFAULT_DAYS
from database import (
    init_db, upsert_user, get_active_subscription,
    add_subscription, count_users, count_new_users_today,
    count_active_subscriptions, deactivate_subscription
)
from xui_client import xui

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# ── FSM States ───────────────────────────────────────────────
class CreateSub(StatesGroup):
    waiting_days = State()


# ── Keyboards ────────────────────────────────────────────────
def main_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="🆕 Создать подписку"), KeyboardButton(text="📦 Моя подписка")],
    ]
    if is_admin:
        buttons.append([KeyboardButton(text="👑 Панель администратора")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


# ── Helpers ──────────────────────────────────────────────────
def fmt_bytes(b: int) -> str:
    if b >= 1024 ** 3:
        return f"{b / 1024 ** 3:.2f} ГБ"
    elif b >= 1024 ** 2:
        return f"{b / 1024 ** 2:.2f} МБ"
    return f"{b / 1024:.1f} КБ"


def days_left(expire_at_str: str) -> int:
    try:
        expire = datetime.strptime(expire_at_str, "%Y-%m-%d %H:%M:%S")
        delta = expire - datetime.now()
        return max(delta.days, 0)
    except Exception:
        return 0


# ── Handlers ─────────────────────────────────────────────────
@dp.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    upsert_user(user.id, user.username, user.first_name)
    is_admin = user.id in ADMIN_IDS
    await message.answer(
        f"Привет, {user.first_name}!\n\n"
        "Я бот для управления VPN-подпиской.\n"
        "Выбери действие:",
        reply_markup=main_menu(is_admin)
    )


@dp.message(F.text == "🆕 Создать подписку")
async def create_sub_start(message: Message, state: FSMContext):
    existing = get_active_subscription(message.from_user.id)
    if existing:
        d = days_left(existing["expire_at"])
        await message.answer(
            f"У тебя уже есть активная подписка (осталось {d} дн.).\n"
            "Чтобы создать новую, она будет заменена. Введи количество дней для новой подписки:"
        )
    else:
        await message.answer(
            f"Введи количество дней подписки (например, {DEFAULT_DAYS}):"
        )
    await state.set_state(CreateSub.waiting_days)


@dp.message(CreateSub.waiting_days)
async def create_sub_days(message: Message, state: FSMContext):
    await state.clear()
    text = message.text.strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer("Пожалуйста, введи целое положительное число дней.")
        return

    days = int(text)
    if days > 365:
        await message.answer("Максимум 365 дней за один раз.")
        return

    user = message.from_user
    email = f"tg_{user.id}"

    await message.answer("⏳ Создаю подписку...")
    try:
        result = xui.add_client(email=email, days=days, traffic_gb=DEFAULT_TRAFFIC_GB)
        add_subscription(
            telegram_id=user.id,
            client_id=result["client_id"],
            email=email,
            expire_at=result["expire_at"],
            traffic_limit_gb=DEFAULT_TRAFFIC_GB,
        )
        await message.answer(
            f"✅ Подписка создана!\n\n"
            f"📅 Срок: {days} дней (до {result['expire_at'][:10]})\n"
            f"📊 Трафик: {DEFAULT_TRAFFIC_GB} ГБ\n\n"
            f"🔗 Ссылка для подключения:\n"
            f"<code>{result['link']}</code>",
            parse_mode="HTML"
        )
    except Exception as e:
        log.error(f"Ошибка создания подписки: {e}")
        await message.answer(f"❌ Ошибка при создании подписки: {e}")


@dp.message(F.text == "📦 Моя подписка")
async def my_sub(message: Message):
    sub = get_active_subscription(message.from_user.id)
    if not sub:
        await message.answer(
            "У тебя нет активной подписки.\n"
            "Нажми \"🆕 Создать подписку\" чтобы получить доступ."
        )
        return

    try:
        traffic = xui.get_client_traffic(sub["email"])
        used_up = fmt_bytes(traffic["up"])
        used_down = fmt_bytes(traffic["down"])
        total_allowed = fmt_bytes(sub["traffic_limit_gb"] * 1024 ** 3)
        used_total = fmt_bytes(traffic["up"] + traffic["down"])
        expire_at = sub["expire_at"]
        d_left = days_left(expire_at)
        status = "✅ Активна" if traffic["enable"] else "❌ Заблокирована"

        text = (
            f"📦 <b>Информация о подписке</b>\n\n"
            f"Статус: {status}\n"
            f"📅 Действует до: {expire_at[:10]}\n"
            f"⏳ Осталось дней: {d_left}\n\n"
            f"📊 <b>Трафик</b>\n"
            f"  ⬆️ Отправлено: {used_up}\n"
            f"  ⬇️ Получено: {used_down}\n"
            f"  📈 Итого: {used_total} / {total_allowed}\n"
        )

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Показать ссылку", callback_data="show_link")]
        ])
        await message.answer(text, parse_mode="HTML", reply_markup=kb)

    except Exception as e:
        log.error(f"Ошибка получения трафика: {e}")
        await message.answer(f"❌ Не удалось получить данные: {e}")


@dp.callback_query(F.data == "show_link")
async def show_link_cb(call: CallbackQuery):
    sub = get_active_subscription(call.from_user.id)
    if not sub:
        await call.answer("Подписка не найдена", show_alert=True)
        return
    try:
        inbound = xui.get_inbound()
        protocol = inbound.get("protocol", "vless")
        link = xui._build_link(inbound, sub["client_id"], sub["email"], protocol)
        await call.message.answer(
            f"🔗 Ссылка для подключения:\n<code>{link}</code>",
            parse_mode="HTML"
        )
        await call.answer()
    except Exception as e:
        await call.answer(f"Ошибка: {e}", show_alert=True)


# ── Admin handlers ───────────────────────────────────────────
@dp.message(F.text == "👑 Панель администратора")
async def admin_panel(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("Нет доступа.")
        return
    total = count_users()
    new_today = count_new_users_today()
    active_subs = count_active_subscriptions()
    await message.answer(
        f"👑 <b>Панель администратора</b>\n\n"
        f"👤 Всего пользователей: {total}\n"
        f"🆕 Новых сегодня: {new_today}\n"
        f"📦 Активных подписок: {active_subs}",
        parse_mode="HTML"
    )


@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    await admin_panel(message)


# ── Main ─────────────────────────────────────────────────────
async def main():
    init_db()
    log.info("Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
