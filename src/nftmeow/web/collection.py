from dataclasses import dataclass
from typing import List, Optional

from pymongo.database import Database
import strawberry
from strawberry import UNSET
from strawberry.dataloader import DataLoader

from nftmeow.web.context import Context, Info
from nftmeow.web.pagination import (
    Connection,
    Cursor,
    Filter,
    Edge,
    PageInfo,
    cursor_from_mongo_id,
)
from nftmeow.web.scalar import Address, OrderDirection


@strawberry.type
class Collection:
    address: Address
    name: Optional[str]

    @classmethod
    def from_mongo(cls, data: dict) -> "Collection":
        return Collection(address=data["contract_address"], name=data.get("name"))

    @classmethod
    def build_cursor(_cls, data: dict) -> str:
        return cursor_from_mongo_id(data["_id"])


async def get_collection(ctx: Context, address: Address) -> Optional[Collection]:
    collection = await ctx.collection_loader.load(address)
    if collection is not None:
        return Collection.from_mongo(collection)


@dataclass
class CollectionLoader:
    db: Database

    async def __call__(self, collection_ids: List[Address]):
        collections = self.db["contracts"].find(
            {"type": "erc721", "contract_address": {"$in": collection_ids}}
        )
        collections_by_address = dict(
            (coll["contract_address"], coll) for coll in collections
        )
        return [collections_by_address[addr] for addr in collection_ids]


def get_collections(
    info: Info,
    first: int = 20,
    after: Optional[Cursor] = UNSET,
    address: Optional[Filter[Address]] = UNSET,
) -> Connection[Collection]:
    if first < 1:
        raise ValueError("first must be greater than equal 1")
    if first > 200:
        raise ValueError("first must be less than equal 200")

    db = info.context.db

    filter = {"type": "erc721"}
    if address is not UNSET:
        filter["contract_address"] = address.mongo_filter()

    order_direction = OrderDirection.ASC
    if after is not UNSET:
        filter["_id"] = order_direction.mongo_after_cursor(after)

    query = db["contracts"].find(filter)
    query = query.limit(first + 1)

    collections = list(query)

    edges = [
        Edge(node=Collection.from_mongo(c), cursor=Collection.build_cursor(c))
        for c in collections
    ]

    page_info = PageInfo(
        has_previous_page=after is not UNSET,
        has_next_page=len(collections) == first + 1,
        start_cursor=edges[0].cursor if edges else None,
        end_cursor=edges[-2].cursor if len(edges) > 1 else None,
    )

    return Connection(page_info=page_info, edges=edges[:-1])


def collection_loader(db):
    return DataLoader(CollectionLoader(db))
