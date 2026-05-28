import asyncio

from aiogram import Bot

from src.config import BOT_TOKEN


async def main() -> None:
    bot = Bot(BOT_TOKEN)
    me = await bot.get_me()
    print(f"Bot OK: @{me.username}")
    await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
