import importlib
import logging
from pkgutil import walk_packages
from types import ModuleType
from typing import Optional
from discord.ext import commands

def _import(name: str) -> Optional[ModuleType]:
    try:
        return importlib.import_module(name)
    except ImportError as exc:
        logging.warning("Could not import `%s`. %s", name, exc)

async def load_cogs(bot: commands.Bot, package: str):
    pkg = _import(package)
    for module_info in walk_packages(path=pkg.__path__, prefix=f"{package}."):
        if module_info.ispkg:
            continue

        if module := _import(module_info.name):
            for key, attr in module.__dict__.items():
                if key.startswith('_'):
                    continue
                if not isinstance(attr, type):
                    continue

                if issubclass(attr, commands.Cog) and attr is not commands.Cog:
                    logging.info("Loading cog %s", module_info.name)
                    try:
                        await bot.add_cog(attr(bot))
                    except Exception as exc:
                        logging.warning(f"{exc}", exc_info=exc)

    logging.info("Synchronizing application command tree.")
    await bot.tree.sync()
