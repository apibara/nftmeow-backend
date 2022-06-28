"""NFT Meow indexer entrypoint."""

import asyncio
import aiohttp
from datetime import datetime
from typing import Iterator

from apibara import IndexerManagerClient, DEFAULT_APIBARA_SERVER_URL
from apibara.model import NewEvents
from apibara.client import contract_event_filter
from apibara.starknet import get_selector_from_name


INDEXER_ID = 'nftmeow'
FILTERS = [
    contract_event_filter('Transfer')
]


NODE_URL = 'http://192.168.8.100:9545'


async def node_request(method, params):
    async with aiohttp.ClientSession(NODE_URL) as session:
        data = {
            'id': 1,
            'jsonrpc': '2.0',
            'method': method,
            'params': params
        }
        async with session.post('/', json=data) as response:
            response = await response.json()
            if 'result' in response:
                return response['result']
            raise RuntimeError(response['error']['message'])


async def get_block_by_hash(hash):
    return await node_request('starknet_getBlockByHash', ['0x' + hash.hex() ,"TXN_HASH"])


async def contract_call(contract, entrypoint, params):
    params = [{
        'contract_address': '0x' + contract.hex(),
        'entry_point_selector': hex(entrypoint),
        'calldata': params
    }, "latest"]
    return await node_request('starknet_call', params)


_supports_interface_selector = get_selector_from_name('supportsInterface')
_erc721_id = '0x80ac58cd'


async def supports_erc721(contract):
    try:
        response = await contract_call(contract, _supports_interface_selector, [_erc721_id])
        return response == ['0x1']
    except:
        return False


_token_uri_selector = get_selector_from_name('tokenURI')


async def get_token_uri(contract, token_id):
    try:
        response = await contract_call(contract, _token_uri_selector, [hex(token_id)])
        print(response)
        return response == ['0x1']
    except:
        return None


def felt_from_iter(it: Iterator[bytes]):
    return int.from_bytes(next(it), "big")


def uint256_from_iter(it: Iterator[bytes]):
    low = felt_from_iter(it)
    high = felt_from_iter(it)
    return (high << 128) + low


def parse_event_data(event):
    if len(event.data) == 3:
        data_iter = iter(event.data)
        from_ = felt_from_iter(data_iter)
        to = felt_from_iter(data_iter)
        token_id = felt_from_iter(data_iter)
        return from_, to, token_id
    elif len(event.data) == 4:
        data_iter = iter(event.data)
        from_ = felt_from_iter(data_iter)
        to = felt_from_iter(data_iter)
        token_id = uint256_from_iter(data_iter)
        return from_, to, token_id
    else:
        print('weird event data', event.data)
        return None, None, None
    

async def _main():
    async with IndexerManagerClient.insecure_channel(DEFAULT_APIBARA_SERVER_URL) as client:
        existing = await client.get_indexer(INDEXER_ID)
        if existing:
            await client.delete_indexer(INDEXER_ID)
        await client.create_indexer(INDEXER_ID, 98_000, FILTERS)

        print('connecting to server')
        server_stream, client = await client.connect_indexer()
        await client.connect_indexer(INDEXER_ID)

        print('stream started')
        contracts = dict()
        async for message in server_stream:
            if isinstance(message, NewEvents):
                block = await get_block_by_hash(message.block_hash)
                timestamp = datetime.fromtimestamp(block['accepted_time'])

                for event in message.events:
                    if event.address not in contracts:
                        is_erc721 = await supports_erc721(event.address)
                        contracts[event.address] = is_erc721
                    else:
                        is_erc721 = contracts[event.address]

                    if not is_erc721:
                        continue

                    print('Parse token transfer ', event.address.hex())
                    from_, to, token_id = parse_event_data(event)
                    if token_id is None:
                        continue
                    print('    ', from_, to, token_id)
                    await get_token_uri(event.address, token_id)


                await client.ack_block(message.block_hash)



def main():
    asyncio.run(_main())