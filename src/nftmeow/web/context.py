from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from pymongo.database import Database
from strawberry.dataloader import DataLoader
from strawberry.types import Info as StrawberryInfo


@dataclass
class Context:
    db: Database
    collection_loader: DataLoader


Info = StrawberryInfo[Context, Any]
