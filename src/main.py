import discord
from discord.ext import commands

from dotenv import load_dotenv
import os
import asyncio

from Utils.database import *  # Creates tables if required

bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    print('------')


async def setup_hook():
    for filename in os.listdir('./src/cogs'):
        if filename.endswith('.py'):
            await bot.load_extension(f'cogs.{filename[:-3]}')

    try:
        synced_commands = await bot.tree.sync()
        print(f'Synced {len(synced_commands)} commands')
    except Exception as e:
        print(f'Failed to sync commands: {e}')


bot.setup_hook = setup_hook


def get_discord_token() -> str:
    load_dotenv()
    token = os.getenv('DISCORD_TOKEN')
    if token is None:
        raise ValueError("DISCORD_TOKEN environment variable not set")
    return token


async def main():
    async with bot:
        await bot.start(get_discord_token())


asyncio.run(main())
