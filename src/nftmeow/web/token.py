from typing import Optional
import strawberry
from nftmeow.web.context import Context

from nftmeow.web.context import Info
from nftmeow.web.scalar import Address, TokenId
from nftmeow.web.collection import Collection, get_collection


@strawberry.type
class Token:
    token_id: TokenId

    _contract_address: strawberry.Private[Address]

    @strawberry.field
    async def collection(self, info: Info) -> Collection:
        return await get_collection(info.context, self._contract_address)

    @classmethod
    def from_mongo(cls, data: dict) -> "Token":
        return cls(
            token_id=data["token_id"], _contract_address=data["contract_address"]
        )


def get_token_by_address_and_id(
    ctx: Context, address: Address, token_id: TokenId
) -> Token:
    token = ctx.db["tokens"].find_one(
        {"contract_address": address, "token_id": token_id}
    )

    if token is not None:
        return Token.from_mongo(token)
