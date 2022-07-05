import base64
from typing import Generic, List, Optional, TypeVar

import strawberry
from bson import ObjectId

GenericType = TypeVar("GenericType")

Cursor = str


@strawberry.type
class Connection(Generic[GenericType]):
    """Represents a paginated relationship between two entities

    This pattern is used when the relationship itself has attributes.
    In a Facebook-based domain example, a friendship between two people
    would be a connection that might have a `friendshipStartTime`
    """

    page_info: "PageInfo"
    edges: list["Edge[GenericType]"]


@strawberry.type
class PageInfo:
    """Pagination context to navigate objects with cursor-based pagination

    Instead of classic offset pagination via `page` and `limit` parameters,
    here we have a cursor of the last object and we fetch items starting from that one

    Read more at:
        - https://graphql.org/learn/pagination/#pagination-and-edges
        - https://relay.dev/graphql/connections.htm
    """

    has_next_page: bool
    has_previous_page: bool
    start_cursor: Optional[Cursor]
    end_cursor: Optional[Cursor]


@strawberry.type
class Edge(Generic[GenericType]):
    """An edge may contain additional information of the relationship. This is the trivial case"""

    node: GenericType
    cursor: Cursor


@strawberry.input
class Filter(Generic[GenericType]):
    """A filter over elements of a Collection."""

    eq: Optional[GenericType] = None
    ne: Optional[GenericType] = None
    in_: Optional[List[GenericType]] = None

    def mongo_filter(self):
        if self.eq is not None:
            return {"$eq": self.eq}

        if self.ne is not None:
            return {"$ne": self.ne}

        if self.in_ is not None:
            return {"$in": self.in_}

        raise ValueError("one of eq, ne, or in must be set")


def cursor_from_mongo_id(id: ObjectId) -> str:
    """Generate a Relay-compatible cursor from the mongodb object id."""
    return str(id)
