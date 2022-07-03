"""NFTMeow GraphQL server."""

import asyncio
from typing import List
from logging import getLogger
from aiohttp import web

from pymongo import MongoClient
import strawberry
from strawberry.aiohttp.views import GraphQLView
from nftmeow.web.context import Context

from nftmeow.web.pagination import Connection
from nftmeow.web.collection import Collection, collection_loader, get_collections
from nftmeow.web.token import Token, get_tokens
from nftmeow.web.transfer import Transfer, get_transfers


logger = getLogger(__name__)


@strawberry.type
class Query:
    collections: Connection[Collection] = strawberry.field(resolver=get_collections)
    transfers: Connection[Transfer] = strawberry.field(resolver=get_transfers)
    tokens: Connection[Token] = strawberry.field(resolver=get_tokens)


class NFTMeowGraphQLView(GraphQLView):
    def __init__(self, mongo_url: str, db_name: str, **kwargs):
        super().__init__(**kwargs)
        self._mongo = MongoClient(mongo_url)
        self._db = self._mongo[db_name]

    async def get_context(
        self, _request: web.Request, _response: web.StreamResponse
    ) -> Context:
        return Context(db=self._db, collection_loader=collection_loader(self._db))


async def start_web_server(host: str, port: int, mongo_url: str, db_name: str):
    schema = strawberry.Schema(query=Query)
    view = NFTMeowGraphQLView(mongo_url, db_name, schema=schema)

    app = web.Application()
    app.router.add_route("*", "/graphql", view)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info(f"GraphQL server started: {host}:{port}")

    while True:
        await asyncio.sleep(10_000)
