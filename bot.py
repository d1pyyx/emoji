import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import Message, MessageEntity

BOT_TOKEN = "8902448579:AAFoho8yLyJKbfSUVlThp2BLIx1NCz5dh8U"
CUSTOM_EMOJI_ID = "5368324170671202286"
FALLBACK_EMOJI = "👍"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message()
async def handler(message: Message):
    text = f"Привет! {FALLBACK_EMOJI}"
    await message.answer(
        text,
        entities=[
            MessageEntity(
                type="custom_emoji",
                offset=len("Привет! "),
                length=len(FALLBACK_EMOJI),
                custom_emoji_id=CUSTOM_EMOJI_ID
            )
        ]
    )

async def main():
    await dp.start_polling(bot)

asyncio.run(main())
