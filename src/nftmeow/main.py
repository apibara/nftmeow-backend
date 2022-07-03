"""NFT Meow indexer entrypoint."""

import asyncio
import logging
import os

import click
from functools import wraps

from nftmeow.indexer import NftIndexer
from nftmeow.web import start_web_server


DEFAULT_APIBARA_URL = "127.0.0.1:7171"
DEFAULT_MONGODB_URL = "mongodb://nftmeow:nftmeow@localhost:27017"
DEFAULT_INDEXER_ID = "nftmeow"


logger = logging.getLogger(__name__)


def async_command(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))

    return wrapper


@click.group()
def cli():
    pass


@cli.command()
@click.option("--reset", default=False, is_flag=True, help="Reset indexer state.")
@click.option("--verbose", default=False, is_flag=True, help="More logging.")
@click.option("--server-url", default=DEFAULT_APIBARA_URL, help="Apibara Server url.")
@click.option("--mongo-url", default=DEFAULT_MONGODB_URL, help="MongoDB url.")
@click.option("--indexer-id", default=DEFAULT_INDEXER_ID, help="Indexer id.")
@async_command
async def indexer(reset, verbose, server_url, mongo_url, indexer_id):
    """Start the NFTMeow indexer."""
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    mongo_url = _override_mongo_url_with_env(mongo_url)

    indexer = NftIndexer(server_url, mongo_url, indexer_id)

    if reset:
        logger.info("reset indexer")
        await indexer.reset()

    await indexer.run()


@cli.command()
@click.option("--verbose", default=False, is_flag=True, help="More logging.")
@click.option("--host", default="0.0.0.0", help="Server host.")
@click.option("--port", default=8080, type=int, help="Server port.")
@click.option("--mongo-url", default=DEFAULT_MONGODB_URL, help="MongoDB url.")
@async_command
async def api_server(verbose, host, port, mongo_url):
    """Start the NFTMeow GraphQL server."""
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    mongo_url = _override_mongo_url_with_env(mongo_url)

    await start_web_server(host, port, mongo_url)


def _override_mongo_url_with_env(mongo_url):
    return os.environ.get('NFTMEOW_MONGO_URL', mongo_url)
