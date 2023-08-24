import logging
import tomllib as toml
from pathlib import Path

import aiohttp
import discord
from discord.ext import commands

from .loader import load_cogs


class Bot(commands.Bot):
    def __init__(self, config: Path):
        logging.info("Initializing bot")

        self.config = toml.loads(config.read_text())

        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix=[".", "++"], case_insensitive=True, intents=intents)

    async def on_ready(self):
        logging.info('Logged in as %s (ID: %d)', self.user.name, self.user.id)
        logging.info('OAuth: %s', discord.utils.oauth_url(self.user.id))

        await load_cogs(self, "bcpp.cogs")

        self.http_client = aiohttp.ClientSession()

