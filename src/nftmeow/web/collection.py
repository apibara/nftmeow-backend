from dataclasses import dataclass
from typing import List, Optional

from pymongo.database import Database
import strawberry
from strawberry import UNSET
from strawberry.dataloader import DataLoader
from nftmeow.web.context import Context
from nftmeow.web.pagination import Connection, Cursor

from nftmeow.web.scalar import Address


@strawberry.type
class Collection:
    address: Address
    name: Optional[str]

    @classmethod
    def from_mongo(cls, data: dict) -> "Collection":
        return Collection(address=data["contract_address"], name=data.get("name"))


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
    first: int = 20, after: Optional[Cursor] = UNSET
) -> Connection[Collection]:
    after = after if after is not UNSET else None
    return Connection()


def collection_loader(db):
    return DataLoader(CollectionLoader(db))
