from audioop import add
from dataclasses import dataclass
from typing import Optional, List, Tuple
import strawberry
from strawberry import UNSET
from strawberry.dataloader import DataLoader
from pymongo.database import Database

from nftmeow.web.context import Info, Context
from nftmeow.web.pagination import (
    Cursor,
    Connection,
    Filter,
    PageInfo,
    Edge,
    cursor_from_mongo_id,
)
from nftmeow.web.scalar import Address, OrderDirection, TokenId
from nftmeow.web.collection import Collection, get_collection


@strawberry.type
class Token:
    token_id: TokenId
    owners: List[Address]

    _contract_address: strawberry.Private[Address]

    @strawberry.field
    async def collection(self, info: Info) -> Collection:
        return await get_collection(info.context, self._contract_address)

    @classmethod
    def from_mongo(cls, data: dict) -> "Token":
        return cls(
            token_id=data["token_id"],
            owners=data["owners"],
            _contract_address=data["contract_address"],
        )

    @classmethod
    def build_cursor(_cls, data: dict) -> str:
        return cursor_from_mongo_id(data["_id"])


async def get_token_by_address_and_id(
    ctx: Context, address: Address, token_id: TokenId
) -> Token:
    token = await ctx.tokens_by_address_token_id_loader.load((address, token_id))
    if token is not None:
        return Token.from_mongo(token)


def get_tokens(
    info: Info,
    first: int = 10,
    after: Optional[Cursor] = UNSET,
    collection: Optional[Filter[Address]] = UNSET,
    owner: Optional[Filter[Address]] = UNSET,
) -> Connection[Token]:
    if first < 1:
        raise ValueError("first must be greater than equal 1")
    if first > 200:
        raise ValueError("first must be less than equal 200")

    db = info.context.db

    filter = dict()
    if collection is not UNSET:
        filter["contract_address"] = collection.mongo_filter()

    if owner is not UNSET:
        filter["owners"] = {"$elemMatch": owner.mongo_filter()}

    order_direction = OrderDirection.ASC

    if after is not UNSET:
        filter["_id"] = order_direction.mongo_after_cursor(after)

    query = db["tokens"].find(filter)
    query = query.limit(first + 1)

    tokens = list(query)

    edges = [
        Edge(node=Token.from_mongo(t), cursor=Token.build_cursor(t)) for t in tokens
    ]

    page_info = PageInfo(
        has_previous_page=after is not UNSET,
        has_next_page=len(tokens) == first + 1,
        start_cursor=edges[0].cursor if edges else None,
        end_cursor=edges[-2].cursor if len(edges) > 1 else None,
    )

    return Connection(page_info=page_info, edges=edges[:-1])


@dataclass
class TokensByAddressTokenIdLoader:
    db: Database

    async def __call__(self, tokens_addr_id: List[Tuple[Address, TokenId]]):
        # group by contract address since it's not possible to query
        # by address/token_id
        by_addr = dict()
        for addr, token_id in tokens_addr_id:
            if addr not in by_addr:
                by_addr[addr] = []
            by_addr[addr].append(token_id)

        result = dict()
        for addr, token_ids in by_addr.items():
            tokens = self.db["tokens"].find({
                "contract_address": addr,
                "token_id": { "$in": token_ids }
            })
            for token in tokens:
                result[addr, token['token_id']] = token

        return [result[addr, token_id] for addr, token_id in tokens_addr_id]


def tokens_by_address_token_id_loader(db):
    return DataLoader(TokensByAddressTokenIdLoader(db))
