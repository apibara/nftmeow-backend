from typing import NewType
from enum import Enum
from bson import ObjectId

import strawberry

from nftmeow.web.pagination import Cursor


@strawberry.enum
class OrderDirection(Enum):
    """Direction in which to order results in a `Connection`."""

    ASC = "asc"
    DESC = "desc"

    def mongo_direction(self) -> int:
        if self == OrderDirection.ASC:
            return 1
        return -1

    def mongo_after_cursor(self, after: Cursor) -> dict:
        if self == OrderDirection.ASC:
            return {"$gt": ObjectId(after)}
        return {"$lt": ObjectId(after)}


def _parse_token_id(value: str) -> "TokenId":
    if not value.startswith("0x"):
        raise ValueError("invalid tokenId")
    return bytes.fromhex(value.replace("0x", ""))


def _serialize_token_id(token_id: "TokenId") -> str:
    return "0x" + token_id.hex()


TokenId = strawberry.scalar(
    NewType("TokenId", bytes),
    parse_value=_parse_token_id,
    serialize=_serialize_token_id,
)


def _parse_address(value: str) -> "Address":
    if not value.startswith("0x"):
        raise ValueError("invalid address")
    return bytes.fromhex(value.replace("0x", "").zfill(64))


def _serialize_address(addr: "Address") -> str:
    return "0x" + addr.zfill(32).hex()


Address = strawberry.scalar(
    NewType("Address", bytes),
    parse_value=_parse_address,
    serialize=_serialize_address,
)
