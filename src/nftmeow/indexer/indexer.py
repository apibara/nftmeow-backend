import logging
from datetime import datetime
from typing import Iterator, List, Tuple

import pymongo
from apibara.model import Event, EventFilter
from pymongo import MongoClient

from apibara import IndexerRunner, Info, NewBlock, NewEvents
from nftmeow.indexer.erc721 import (ERC721Contract, TransferEvent,
                                    bytes_to_int, decode_transfer_event,
                                    hex_to_bytes, int_to_bytes)
from nftmeow.indexer.storage import CachedContractStorage
from nftmeow.starknet_rpc import StarkNetRpcClient

logger = logging.getLogger(__name__)

BRIQ_ADDRESS = hex_to_bytes(
    "0x0266b1276d23ffb53d99da3f01be7e29fa024dd33cd7f7b1eb7a46c67891c9d0"
)


class NftIndexer:
    def __init__(self, server_url, mongo_url, indexer_id):
        self._server_url = server_url
        self._mongo_url = mongo_url
        self._indexer_id = indexer_id
        self._db_name = indexer_id.replace("-", "_")
        self._db = None
        self._contract_storage = None

    def _mongo_client_db(self):
        mongo = MongoClient(self._mongo_url)
        db = mongo[self._db_name]
        return mongo, db

    async def run(self):
        _mongo, db = self._mongo_client_db()
        self._db = db
        self._contract_storage = CachedContractStorage(db)

        db_status = db.command("serverStatus")
        logger.info(f'MongoDB connected: {db_status["host"]}')

        runner = IndexerRunner(
            indexer_id=self._indexer_id, new_events_handler=self.handle_events
        )

        runner.create_if_not_exists(
            filters=[EventFilter.from_event_name(name="Transfer", address=None)],
            index_from_block=21_000,
        )

        await runner.run()

    async def handle_events(self, info: Info, message: NewEvents):
        block = await info.rpc_client.get_block_by_hash(message.block_hash)
        block_timestamp = datetime.fromtimestamp(block["accepted_time"])
        logger.debug(f"got block {message.block_number} accepted at {block_timestamp}")

        for event in message.events:
            await self._handle_transfer_event(
                info, message.block_number, block_timestamp, event
            )

    async def _handle_transfer_event(
        self, info: Info, block_number: int, block_timestamp: datetime, event: Event
    ):
        logger.info(f"Process event {block_number} {event}")
        # Decode event data. Notice that some contracts use a felt
        # for the token id and we need to support that too.
        try:
            transfer = decode_transfer_event(event.data)
            if transfer is None:
                return
        except:
            return

        # Briq is slightly different
        if event.address == BRIQ_ADDRESS:
            return await self._handle_briq(
                block_number, block_timestamp, event, transfer
            )

        # The contract could be an ERC-20. Check it is an ERC-721.
        contract = self._contract_storage.get(event.address)
        if contract is None:
            erc721 = ERC721Contract(info.rpc_client, event.address)
            if await erc721.is_erc721(transfer.token_id):
                # get name and symbol
                name = await erc721.name()
                contract = {"type": "erc721", "name": name}
                self._contract_storage.set(event.address, contract)
            else:
                contract = {"type": "other"}
                self._contract_storage.set(event.address, contract)

        if contract["type"] != "erc721":
            return

        # Now we know we have an ERC-721.
        # Invalidate old token information
        token = self._db["tokens"].find_one_and_update(
            {
                "contract_address": event.address,
                "token_id": transfer.token_id.to_bytes(),
                "_chain.valid_to": None,
            },
            {"$set": {"_chain.valid_to": block_number}},
            return_document=pymongo.ReturnDocument.BEFORE,
        )

        if token is None:
            # insert metadata that will be fetched by the metadata
            # fetchers
            self._db["token_metadata"].insert_one(
                {
                    "contract_address": event.address,
                    "token_id": transfer.token_id.to_bytes(),
                    "status": "missing",
                    "_chain.valid_to": None,
                }
            )

            before_owners = []
        else:
            before_owners = token["owners"]

        from_as_bytes = int_to_bytes(transfer.from_address)
        to_as_bytes = int_to_bytes(transfer.to_address)

        after_owners = [
            addr
            for addr in before_owners
            if bytes_to_int(addr) != transfer.from_address
            and bytes_to_int(addr) != transfer.to_address
        ] + [to_as_bytes]

        # Store updated token information
        self._db["tokens"].insert_one(
            {
                "contract_address": event.address,
                "token_id": transfer.token_id.to_bytes(),
                "updated_at": block_timestamp,
                "owners": after_owners,
                "_chain": {"valid_from": block_number, "valid_to": None},
            }
        )

        self._db["transfers"].insert_one(
            {
                "contract_address": event.address,
                "token_id": transfer.token_id.to_bytes(),
                "from": from_as_bytes,
                "to": to_as_bytes,
                "created_at": block_timestamp,
                "_chain": {"valid_from": block_number, "valid_to": None},
            }
        )

    async def _handle_briq(
        self,
        block_number: int,
        block_timestamp: datetime,
        event: Event,
        transfer: TransferEvent,
    ):
        logger.error(f"Found BRIQ event {block_number} {event}")
