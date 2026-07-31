from __future__ import annotations

import asyncio
import datetime
import logging
import random
from dataclasses import dataclass

import aiohttp
import aiosqlite
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    MessageEntity,
    ReplyKeyboardMarkup,
)


BOT_TOKEN = "8899946184:AAEXaLiRA_7ttGhhRzVzqUVVNlrpfbuQd8g"
CRYPTOBOT_TOKEN = "616114:AAKEATLqytmkwhfSIITC2isWYS0NU5kVbfl"
LOG_CHANNEL_ID = -1004335316222
CRYPTOBOT_API_URL = "https://pay.crypt.bot/api"
DB_PATH = "db.sqlite3"
PAYMENT_CHECK_INTERVAL = 15


@dataclass(frozen=True)
class Tariff:
    key: str
    title: str
    price_usd: float
    duration_days: int | None
    file_path: str


TARIFFS: dict[str, Tariff] = {
    "hellstar_30d": Tariff(
        key="hellstar_30d",
        title="hellstar 30d",
        price_usd=4.99,
        duration_days=30,
        file_path="files/hellstar_30d.zip",
    ),
    "hellstar_90d": Tariff(
        key="hellstar_90d",
        title="hellstar 90d",
        price_usd=14.99,
        duration_days=90,
        file_path="files/hellstar_90d.zip",
    ),
    "hellstar_lifetime": Tariff(
        key="hellstar_lifetime",
        title="hellstar lifetime",
        price_usd=29.99,
        duration_days=None,
        file_path="files/hellstar_lifetime.zip",
    ),
}


CUSTOM_EMOJI: dict[str, str | None] = {
    "wave": None,
    "cart": None,
    "profile": None,
    "check": None,
    "cross": None,
}

FALLBACK: dict[str, str] = {
    "wave": "👋",
    "cart": "🛒",
    "profile": "👤",
    "check": "✅",
    "cross": "❌",
}


def render(template: str, key: str) -> tuple[str, list[MessageEntity]]:
    symbol = FALLBACK[key]
    text = template.format(emoji=symbol)
    custom_id = CUSTOM_EMOJI.get(key)
    if custom_id is None:
        return text, []
    prefix = template.split("{emoji}")[0]
    offset = len(prefix.encode("utf-16-le")) // 2
    length = len(symbol.encode("utf-16-le")) // 2
    entity = MessageEntity(
        type="custom_emoji",
        offset=offset,
        length=length,
        custom_emoji_id=custom_id,
    )
    return text, [entity]


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_number TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                tariff_key TEXT NOT NULL,
                price_usd REAL NOT NULL,
                status TEXT NOT NULL,
                invoice_id INTEGER,
                pay_url TEXT,
                created_at TEXT NOT NULL,
                paid_at TEXT
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id INTEGER PRIMARY KEY,
                tariff_key TEXT NOT NULL,
                purchased_at TEXT NOT NULL,
                expires_at TEXT
            )
            """
        )
        await db.commit()


async def upsert_user(user_id: int, username: str | None) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO users (user_id, username, created_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET username = excluded.username
            """,
            (user_id, username, datetime.datetime.utcnow().isoformat()),
        )
        await db.commit()


async def create_order(
    order_number: str,
    user_id: int,
    tariff_key: str,
    price_usd: float,
    invoice_id: int,
    pay_url: str,
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO orders (
                order_number, user_id, tariff_key, price_usd,
                status, invoice_id, pay_url, created_at
            )
            VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)
            """,
            (
                order_number,
                user_id,
                tariff_key,
                price_usd,
                invoice_id,
                pay_url,
                datetime.datetime.utcnow().isoformat(),
            ),
        )
        await db.commit()
        return cursor.lastrowid


async def get_order(order_id: int) -> aiosqlite.Row | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM orders WHERE order_id = ?", (order_id,)
        )
        return await cursor.fetchone()


async def get_pending_orders() -> list[aiosqlite.Row]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM orders WHERE status = 'pending'")
        return await cursor.fetchall()


async def mark_order_paid(order_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE orders SET status = 'paid', paid_at = ? WHERE order_id = ?",
            (datetime.datetime.utcnow().isoformat(), order_id),
        )
        await db.commit()


async def mark_order_cancelled(order_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE orders SET status = 'cancelled' WHERE order_id = ?", (order_id,)
        )
        await db.commit()


async def upsert_subscription(
    user_id: int, tariff_key: str, duration_days: int | None
) -> None:
    now = datetime.datetime.utcnow()
    expires_at = (
        (now + datetime.timedelta(days=duration_days)).isoformat()
        if duration_days is not None
        else None
    )
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO subscriptions (user_id, tariff_key, purchased_at, expires_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                tariff_key = excluded.tariff_key,
                purchased_at = excluded.purchased_at,
                expires_at = excluded.expires_at
            """,
            (user_id, tariff_key, now.isoformat(), expires_at),
        )
        await db.commit()


async def get_subscription(user_id: int) -> aiosqlite.Row | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM subscriptions WHERE user_id = ?", (user_id,)
        )
        return await cursor.fetchone()


def cryptobot_headers() -> dict[str, str]:
    return {"Crypto-Pay-API-Token": CRYPTOBOT_TOKEN}


async def create_invoice(amount_usd: float, description: str, payload: str) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{CRYPTOBOT_API_URL}/createInvoice",
            headers=cryptobot_headers(),
            json={
                "currency_type": "fiat",
                "fiat": "USD",
                "amount": f"{amount_usd:.2f}",
                "description": description,
                "payload": payload,
                "allow_comments": False,
                "allow_anonymous": False,
                "expires_in": 3600,
            },
        ) as response:
            data = await response.json()
            return data["result"]


async def get_invoice(invoice_id: int) -> dict | None:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{CRYPTOBOT_API_URL}/getInvoices",
            headers=cryptobot_headers(),
            params={"invoice_ids": str(invoice_id)},
        ) as response:
            data = await response.json()
            items = data.get("result", {}).get("items", [])
            return items[0] if items else None


async def delete_invoice(invoice_id: int) -> None:
    async with aiohttp.ClientSession() as session:
        await session.post(
            f"{CRYPTOBOT_API_URL}/deleteInvoice",
            headers=cryptobot_headers(),
            json={"invoice_id": invoice_id},
        )


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Каталог"), KeyboardButton(text="Профиль")]],
        resize_keyboard=True,
    )


def catalog_kb() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                text=f"{tariff.title} — {tariff.price_usd}$",
                callback_data=f"tariff:{tariff.key}",
            )
        ]
        for tariff in TARIFFS.values()
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def invoice_kb(order_id: int, pay_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Оплатить", url=pay_url)],
            [
                InlineKeyboardButton(
                    text="Отменить заказ", callback_data=f"cancel:{order_id}"
                )
            ],
        ]
    )


def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="back:main")]]
    )


router = Router()


def generate_order_number() -> str:
    return str(random.randint(100000, 999999))


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await upsert_user(message.from_user.id, message.from_user.username)
    text, entities = render("Здравствуйте, вас приветствует hellstar {emoji}", "wave")
    await message.answer(text, reply_markup=main_menu(), entities=entities)


@router.message(F.text == "Каталог")
async def show_catalog(message: Message) -> None:
    text, entities = render("{emoji} Каталог", "cart")
    await message.answer(text, reply_markup=catalog_kb(), entities=entities)


@router.message(F.text == "Профиль")
async def show_profile(message: Message) -> None:
    subscription = await get_subscription(message.from_user.id)
    if subscription:
        tariff = TARIFFS.get(subscription["tariff_key"])
        tariff_title = tariff.title if tariff else subscription["tariff_key"]
        purchased_at = datetime.datetime.fromisoformat(subscription["purchased_at"])
        days_passed = (datetime.datetime.utcnow() - purchased_at).days
        subscription_line = f"{tariff_title}, прошло {days_passed} дн."
    else:
        subscription_line = "отсутствует"

    text, entities = render("{emoji} Профиль", "profile")
    text += (
        f"\n\nusername-@{message.from_user.username}\n"
        f"id-{message.from_user.id}\n"
        f"subscription-{subscription_line}"
    )
    await message.answer(text, reply_markup=back_kb(), entities=entities)


@router.callback_query(F.data.startswith("tariff:"))
async def select_tariff(callback: CallbackQuery) -> None:
    tariff_key = callback.data.split(":", 1)[1]
    tariff = TARIFFS[tariff_key]
    order_number = generate_order_number()

    invoice = await create_invoice(
        amount_usd=tariff.price_usd,
        description=f"{tariff.title} — заказ #{order_number}",
        payload=order_number,
    )

    order_id = await create_order(
        order_number=order_number,
        user_id=callback.from_user.id,
        tariff_key=tariff.key,
        price_usd=tariff.price_usd,
        invoice_id=invoice["invoice_id"],
        pay_url=invoice["pay_url"],
    )

    text, entities = render("{emoji} Счёт на " + f"{tariff.price_usd}$", "cart")
    await callback.message.edit_text(
        text, reply_markup=invoice_kb(order_id, invoice["pay_url"]), entities=entities
    )
    await callback.answer()

    await callback.bot.send_message(
        LOG_CHANNEL_ID,
        f"Новый заказ #{order_number}\n"
        f"user_id: {callback.from_user.id}\n"
        f"username: @{callback.from_user.username}\n"
        f"tariff: {tariff.title}\n"
        f"price: {tariff.price_usd}$\n"
        f"status: pending",
    )


@router.callback_query(F.data.startswith("cancel:"))
async def cancel_order(callback: CallbackQuery) -> None:
    order_id = int(callback.data.split(":", 1)[1])
    order = await get_order(order_id)
    if order and order["status"] == "pending":
        await mark_order_cancelled(order_id)
        await delete_invoice(order["invoice_id"])

        text, entities = render(
            "Заказ отменён {emoji}\n\nДля возвращения в главное нажмите кнопку ниже",
            "cross",
        )
        await callback.message.edit_text(text, reply_markup=back_kb(), entities=entities)

        await callback.bot.send_message(
            LOG_CHANNEL_ID,
            f"Заказ #{order['order_number']} отменён\n"
            f"user_id: {callback.from_user.id}\n"
            f"username: @{callback.from_user.username}",
        )
    await callback.answer()


@router.callback_query(F.data == "back:main")
async def back_to_main(callback: CallbackQuery) -> None:
    await callback.message.delete()
    text, entities = render("Здравствуйте, вас приветствует hellstar {emoji}", "wave")
    await callback.bot.send_message(
        callback.from_user.id, text, reply_markup=main_menu(), entities=entities
    )
    await callback.answer()


async def deliver_paid_order(bot: Bot, order: aiosqlite.Row) -> None:
    tariff = TARIFFS[order["tariff_key"]]
    await mark_order_paid(order["order_id"])
    await upsert_subscription(order["user_id"], tariff.key, tariff.duration_days)

    text, entities = render(
        "Оплата прошла успешно {emoji}\n\n" + f"Заказ:#{order['order_number']}",
        "check",
    )
    await bot.send_message(order["user_id"], text, entities=entities)
    await bot.send_document(order["user_id"], FSInputFile(tariff.file_path))

    chat = await bot.get_chat(order["user_id"])
    await bot.send_message(
        LOG_CHANNEL_ID,
        f"Оплата подтверждена #{order['order_number']}\n"
        f"user_id: {order['user_id']}\n"
        f"username: @{chat.username}\n"
        f"tariff: {tariff.title}\n"
        f"price: {order['price_usd']}$",
    )


async def payment_checker(bot: Bot) -> None:
    while True:
        try:
            for order in await get_pending_orders():
                invoice = await get_invoice(order["invoice_id"])
                if invoice and invoice["status"] == "paid":
                    await deliver_paid_order(bot, order)
        except Exception as error:
            logging.exception("payment_checker error")
            await bot.send_message(LOG_CHANNEL_ID, f"Ошибка payment_checker: {error}")
        await asyncio.sleep(PAYMENT_CHECK_INTERVAL)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    await init_db()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher()
    dispatcher.include_router(router)

    asyncio.create_task(payment_checker(bot))

    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
