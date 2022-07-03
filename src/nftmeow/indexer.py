"""Index NFTs on StarkNet."""

from datetime import datetime
import logging

from typing import Iterator, List, Tuple
from apibara import IndexerManagerClient
from apibara.client import contract_event_filter
from apibara.model import NewEvents, Event
from lru import LRU
from pymongo import MongoClient
import pymongo

from nftmeow.starknet_rpc import StarkNetRpcClient


logger = logging.getLogger(__name__)


class CachedContractStorage:
    """Store and retrieve information about contracts."""

    def __init__(self, db):
        self._cache = LRU(100)
        self._db = db
        self._contracts = self._db["contracts"]

    def get(self, address):
        existing = self._cache.get(address)
        if existing is not None:
            return existing
        # get from mongo
        contract = self._contracts.find_one({"contract_address": address})
        if contract is None:
            return None
        # update cache
        self._cache[address] = contract
        return contract

    def set(self, address, contract):
        data = {**contract, "contract_address": address}
        self._contracts.insert_one(data)


class NftIndexer:
    def __init__(self, server_url, mongo_url, indexer_id):
        self._server_url = server_url
        self._mongo_url = mongo_url
        self._indexer_id = indexer_id
        self._db_name = indexer_id.replace("-", "_")
        self._db = None
        self._contract_storage = None
        self._rpc = StarkNetRpcClient("https://starknet-goerli.apibara.com")

        # Listen to all Transfer events. Notice that we will
        # receive ERC-20 transfers as well.
        self._filters = [contract_event_filter("Transfer")]

    def _mongo_client_db(self):
        mongo = MongoClient(self._mongo_url)
        db = mongo[self._db_name]
        return mongo, db

    async def reset(self):
        async with IndexerManagerClient.insecure_channel(self._server_url) as client:
            existing = await client.get_indexer(self._indexer_id)
            if existing:
                await client.delete_indexer(self._indexer_id)
            await client.create_indexer(self._indexer_id, 21_000, self._filters)

    async def run(self):
        _mongo, db = self._mongo_client_db()
        self._db = db
        self._contract_storage = CachedContractStorage(db)

        db_status = db.command("serverStatus")
        logger.info(f'MongoDB connected: {db_status["host"]}')

        async with IndexerManagerClient.insecure_channel(self._server_url) as client:
            existing = await client.get_indexer(self._indexer_id)
            if existing is None:
                logger.error("indexer does not exist")
                return
            server_stream, client = await client.connect_indexer()
            await client.connect_indexer(self._indexer_id)

            logger.debug("start server stream")
            async for message in server_stream:
                if not isinstance(message, NewEvents):
                    logger.debug(f"non-event message: {message}")
                    continue
                block = await self._rpc.get_block_by_hash(message.block_hash)
                block_timestamp = datetime.fromtimestamp(block["accepted_time"])
                logger.debug(
                    f"got block {message.block_number} accepted at {block_timestamp}"
                )

                for event in message.events:
                    await self._handle_event(
                        message.block_number, block_timestamp, event
                    )

                await client.ack_block(message.block_hash)

    async def _handle_event(
        self, block_number: int, block_timestamp: datetime, event: Event
    ):
        logger.info(f"Process event {block_number} {event}")
        # Decode event data. Notice that some contracts use a felt
        # for the token id and we need to support that too.
        try:
            from_, to, token_id, kind = _parse_event_data(event)
            if kind is None:
                return
        except:
            return

        # The contract could be an ERC-20. Check it is an ERC-721.
        contract = self._contract_storage.get(event.address)
        if contract is None:
            if await self._is_erc721(event.address, kind, token_id):
                # get name and symbol
                name = await self._erc721_name(event.address)
                contract = {"type": "erc721", "name": name}
                self._contract_storage.set(event.address, contract)
            else:
                logger.debug(
                    f"contract {_format_contract_address(event.address)} is not erc721"
                )
                contract = {"type": "other"}
                self._contract_storage.set(event.address, contract)

        if contract["type"] != "erc721":
            return

        # Now we know we have an ERC-721.

        # Invalidate old token information
        token = self._db["tokens"].find_one_and_update(
            {
                "contract_address": event.address,
                "token_id": _int_to_bytes(token_id),
                "_chain.valid_to": None,
            },
            {"$set": {"_chain.valid_to": block_number}},
            return_document=pymongo.ReturnDocument.BEFORE,
        )

        if token is None:
            # TODO: fetch metadata
            token_uri, metadata = await self._fetch_token_metadata(
                event.address, kind, token_id
            )
            if token_uri is not None:
                self._db["token_metadata"].insert_one(
                    {
                        "contract_address": event.address,
                        "token_id": _int_to_bytes(token_id),
                        "token_uri": token_uri,
                        "metadata": metadata,
                        "_chain.valid_to": None,
                    }
                )

            before_owners = []
        else:
            before_owners = token["owners"]
            if len(before_owners) > 1:
                owners_str = [_format_contract_address(o) for o in before_owners]
                logger.warn(
                    f"token has multiple owners. address={_format_contract_address(event.address)}, id={token_id}, block_number={block_number}, owners={owners_str}"
                )

        from_as_bytes = _int_to_bytes(from_)
        to_as_bytes = _int_to_bytes(to)

        after_owners = [
            addr
            for addr in before_owners
            if _bytes_to_int(addr) != from_ and _bytes_to_int(addr) != to
        ] + [to_as_bytes]

        # Store updated token information
        self._db["tokens"].insert_one(
            {
                "contract_address": event.address,
                "token_id": _int_to_bytes(token_id),
                "updated_at": block_timestamp,
                "owners": after_owners,
                "_chain": {"valid_from": block_number, "valid_to": None},
            }
        )

        self._db["transfers"].insert_one(
            {
                "contract_address": event.address,
                "token_id": _int_to_bytes(token_id),
                "from": from_as_bytes,
                "to": to_as_bytes,
                "created_at": block_timestamp,
                "_chain": {"valid_from": block_number, "valid_to": None},
            }
        )

    async def _is_erc721(self, address, kind, token_id):
        # Check 1. Supports interface?
        try:
            response = await self._rpc.call(
                address, "supportsInterface", ["0x80ac58cd"]
            )
            return response == ["0x1"]
        except:
            pass

        # Check 2. Does tokenURI return anything?
        try:
            if kind == "felt":
                args = [hex(token_id)]
            else:
                low, high = _int_to_uint256(token_id)
                args = [hex(low), hex(high)]
            _ = await self._rpc.call(address, "tokenURI", args)
            return True
        except:
            pass
        return False

    async def _erc721_name(self, address: bytes):
        try:
            name_response = await self._rpc.call(address, "name", [])
            return _decode_string_from_response(name_response)
        except:
            return None

    async def _fetch_token_metadata(self, address: bytes, kind: str, token_id: int):
        return "TODO", {}
        try:
            if kind == "felt":
                args = [hex(token_id)]
            else:
                low, high = _int_to_uint256(token_id)
                args = [hex(low), hex(high)]
            token_uri_response = await self._rpc.call(address, "tokenURI", args)
            token_uri = _decode_string_from_response(token_uri_response)
            return token_uri, {}
        except:
            return None, None


def _format_contract_address(address: bytes):
    return "0x" + address.hex()


def _parse_event_data(event):
    if len(event.data) == 3:
        data_iter = iter(event.data)
        from_ = _felt_from_iter(data_iter)
        to = _felt_from_iter(data_iter)
        token_id = _felt_from_iter(data_iter)
        return from_, to, token_id, "felt"
    elif len(event.data) == 4:
        data_iter = iter(event.data)
        from_ = _felt_from_iter(data_iter)
        to = _felt_from_iter(data_iter)
        token_id = _uint256_from_iter(data_iter)
        return from_, to, token_id, "uint256"
    else:
        return None, None, None, None


def _hex_to_bytes(s: str) -> bytes:
    s = s.replace("0x", "")
    # Python doesn't like odd-numbered hex strings
    if len(s) % 2 == 1:
        s = "0" + s
    return bytes.fromhex(s)


def _int_to_bytes(n: int) -> bytes:
    return n.to_bytes(32, "big")


def _bytes_to_int(b: bytes) -> int:
    return int.from_bytes(b, "big")


def _decode_string_from_response(data: List[str]):
    if len(data) == 1:
        return _decode_short_string(iter(data))
    return _decode_long_string(iter(data))


def _decode_short_string(it: Iterator[str]):
    return _hex_to_bytes(next(it)).decode("ascii")


def _decode_long_string(it: Iterator[str]):
    string_len = _bytes_to_int(_hex_to_bytes(next(it)))
    acc = ""
    for _ in range(string_len):
        acc += _decode_short_string(it)
    return acc


def _uint256_from_iter(it: Iterator[bytes]):
    low = _felt_from_iter(it)
    high = _felt_from_iter(it)
    return (high << 128) + low


def _int_to_uint256(n: int) -> Tuple[int, int]:
    high = n >> 128
    low = n - (high << 128)
    return low, high


def _felt_from_iter(it: Iterator[bytes]):
    return _bytes_to_int(next(it))
