import asyncio
import random
from aiogram import Bot, Dispatcher
from aiogram.types import Message, MessageEntity

BOT_TOKEN = "8902448579:AAFoho8yLyJKbfSUVlThp2BLIx1NCz5dh8U"
STICKER_SET_NAME = "TgPremiumIcon"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message()
async def handler(message: Message):
    sticker_set = await bot.get_sticker_set(name=STICKER_SET_NAME)
    sticker = random.choice(sticker_set.stickers)
    custom_emoji_id = sticker.custom_emoji_id
    fallback = sticker.emoji

    text = fallback
    length = len(fallback.encode("utf-16-le")) // 2

    await message.answer(
        text,
        entities=[
            MessageEntity(
                type="custom_emoji",
                offset=0,
                length=length,
                custom_emoji_id=custom_emoji_id
            )
        ]
    )

async def main():
    await dp.start_polling(bot)

asyncio.run(main())
