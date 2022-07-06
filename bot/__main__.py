import discord
import os
from discord.ext import commands
import asyncio
import logging

log = logging.getLogger(__name__)

extensions = (
    'bot.core',
    'bot.social.provider_cog',
    'bot.social.subscriber_cog',
)

def bot_task_callback(future: asyncio.Future):
    if future.exception():
        raise future.exception()


async def run_bot():
    token = os.environ['TOKEN']
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    bot = commands.Bot(
        intents=intents,
        command_prefix='!',
        slash_commands=True,
    )
    try:
        for ext in extensions:
            await bot.load_extension(ext)
            log.debug(f"Extension {ext} loaded")

        await bot.start(token)
    finally:
        await bot.close()

loop = asyncio.new_event_loop()
try:
    future = asyncio.ensure_future(
        run_bot(),
        loop=loop
    )
    future.add_done_callback(bot_task_callback)
    loop.run_forever()
except KeyboardInterrupt:
    pass
finally:
    loop.close()
