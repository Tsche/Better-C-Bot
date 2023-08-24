import logging
from pathlib import Path
import click

from .log import setup_logger

from .bot import Bot

@click.command()
@click.option('--debug/--no-debug', default=False)
@click.option("-c", "--config",
              help="Path to project configuration.",
              default=Path.cwd() / "config.toml",
              type=Path)
@click.option("-t", "--token",
              help="Path to Discord bot token file.",
              default=Path.cwd() / "token.txt",
              type=Path)
def main(debug: bool, config: Path, token: Path):
    setup_logger()

    if debug:
        logging.root.setLevel(logging.DEBUG)

    assert token.exists(), "No token found."
    assert config.exists(), "No config found"

    bot = Bot(config)
    bot.run(token=token.read_text().strip(),
            log_handler=None)
