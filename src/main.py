import discord
from discord.ext import commands

from datetime import datetime
from dotenv import load_dotenv
import os
import asyncio

from Utils.database import DatabaseManager


if __name__ != '__main__':
    raise RuntimeError('This file is not meant to be imported. Please run it directly.')


bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())


@bot.event
async def on_ready():
    print()
    print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print(f'Logged in as {bot.user}')
    print('------')
    print()

    # Create database tables for all guilds
    for guild in bot.guilds:
        print(f'[DB] Creating tables for guild: {guild.name}, ID: {guild.id}')
        DatabaseManager.create_tables(guild.id)


async def setup_hook():
    for folder in ('cogs', 'cmds'):
        for filename in os.listdir(f'./src/{folder}'):
            if filename.endswith('.py'):
                await bot.load_extension(f'{folder}.{filename[:-3]}')

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
        try:
            await bot.start(get_discord_token())
        except discord.LoginFailure:
            print("🔴 Invalid token. Please check your DISCORD_TOKEN environment variable.")
            return
        except discord.HTTPException as e:
            print(f"🔴 Failed to connect to Discord: {e}")
            return
        except Exception as e:
            print(f"🔴 An unexpected error occurred: {e}")
            return


asyncio.run(main())
