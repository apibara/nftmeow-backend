from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pymongo.database import Database
from strawberry.dataloader import DataLoader
from strawberry.types import Info as StrawberryInfo


@dataclass
class Context:
    db: Database
    collection_loader: DataLoader
    tokens_by_address_token_id_loader: DataLoader


Info = StrawberryInfo[Context, Any]
