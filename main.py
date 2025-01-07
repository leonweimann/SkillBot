from dotenv import load_dotenv
import os
import discord


load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
if TOKEN is None:
    raise ValueError("DISCORD_TOKEN environment variable not set")


class Client(discord.Client):
    async def on_ready(self):
        print(f'Logged in as {self.user}')


intents = discord.Intents.default()
intents.message_content = True

client = Client(intents=intents)
client.run(TOKEN)
