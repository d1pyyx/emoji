import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import Message, MessageEntity

BOT_TOKEN = "8902448579:AAFoho8yLyJKbfSUVlThp2BLIx1NCz5dh8U"

STICKER_SETS = [
    "HalloweenAdaptiveXkysluv",
    "GTAOnlineIcons",
    "AdaptivePixelEmoji",
    "HalloweenAdaptiveEmoji",
]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message()
async def handler(message: Message):
    for set_name in STICKER_SETS:
        sticker_set = await bot.get_sticker_set(name=set_name)
        for i, sticker in enumerate(sticker_set.stickers):
            fallback = sticker.emoji
            label = f" #{i} ({set_name})"
            text = fallback + label
            length = len(fallback.encode("utf-16-le")) // 2

            await message.answer(
                text,
                entities=[
                    MessageEntity(
                        type="custom_emoji",
                        offset=0,
                        length=length,
                        custom_emoji_id=sticker.custom_emoji_id
                    )
                ]
            )
            await asyncio.sleep(0.3)

async def main():
    await dp.start_polling(bot)

asyncio.run(main())
