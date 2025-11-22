from pyrogram import Client
import asyncio

async def main():
    async with Client("TELERAG-MessageScrapper") as app:
        chat = await app.get_chat(-1002706500293)
        print(chat.id, chat.title)

asyncio.run(main())
