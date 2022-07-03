from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional

from pymongo.database import Database
import strawberry
from strawberry import UNSET

from nftmeow.web.context import Info
from nftmeow.web.scalar import Address, OrderDirection, TokenId
from nftmeow.web.token import Token, get_token_by_address_and_id
from nftmeow.web.pagination import (
    Cursor,
    Connection,
    Filter,
    PageInfo,
    Edge,
    cursor_from_mongo_id,
)


@strawberry.enum
class TransferOrderBy(Enum):
    TIME = "time"


@strawberry.type
class Transfer:
    from_address: Address
    to_address: Address
    time: datetime

    _contract_address: strawberry.Private[Address]
    _token_id: strawberry.Private[TokenId]

    @strawberry.field
    def token(self, info: Info) -> Token:
        return get_token_by_address_and_id(
            info.context, self._contract_address, self._token_id
        )

    @classmethod
    def from_mongo(cls, data: dict) -> "Transfer":
        return Transfer(
            from_address=data["from"],
            to_address=data["to"],
            time=data["created_at"],
            _contract_address=data["contract_address"],
            _token_id=data["token_id"],
        )

    @classmethod
    def build_cursor(_cls, data: dict) -> str:
        return cursor_from_mongo_id(data["_id"])


@dataclass
class TransferLoader:
    db: Database

    def __call__(self, *args, **kwargs):
        pass


def get_transfers(
    info: Info,
    first: int = 10,
    after: Optional[Cursor] = UNSET,
    order_by: TransferOrderBy = TransferOrderBy.TIME,
    order_direction: OrderDirection = OrderDirection.DESC,
    collection: Optional[Filter[Address]] = UNSET,
    from_address: Optional[Filter[Address]] = UNSET,
    to_address: Optional[Filter[Address]] = UNSET,
) -> Connection[Transfer]:
    if first < 1:
        raise ValueError("first must be greater than equal 1")
    if first > 200:
        raise ValueError("first must be less than equal 200")

    db = info.context.db

    filter = dict()
    if from_address is not UNSET:
        filter["from"] = from_address.mongo_filter()

    if to_address is not UNSET:
        filter["to"] = from_address.mongo_filter()

    if collection is not UNSET:
        filter["contract_address"] = from_address.mongo_filter()

    if after is not UNSET:
        filter["_id"] = order_direction.mongo_after_cursor(after)

    query = db["transfers"].find(filter)

    if order_by == TransferOrderBy.TIME:
        query.sort("created_at", order_direction.mongo_direction())

    query = query.limit(first + 1)

    transfers = list(query)

    edges = [
        Edge(node=Transfer.from_mongo(t), cursor=Transfer.build_cursor(t))
        for t in transfers
    ]

    page_info = PageInfo(
        has_previous_page=after is not UNSET,
        has_next_page=len(transfers) == first + 1,
        start_cursor=edges[0].cursor if edges else None,
        end_cursor=edges[-2].cursor if len(edges) > 1 else None,
    )

    return Connection(page_info=page_info, edges=edges[:-1])
