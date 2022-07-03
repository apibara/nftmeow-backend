"""Make RPC calls to a StarkNet node."""

from typing import Any, List
import aiohttp
from apibara.starknet import get_selector_from_name


class StarkNetRpcClient:
    def __init__(self, url):
        self._url = url

    async def _request(self, method: str, params: List[Any]):
        async with aiohttp.ClientSession(self._url) as session:
            data = {"id": 1, "jsonrpc": "2.0", "method": method, "params": params}
            async with session.post("/", json=data) as response:
                response = await response.json()
                if "result" in response:
                    return response["result"]
                raise RuntimeError(response["error"]["message"])

    async def get_block_by_hash(self, hash: bytes):
        return await self._request(
            "starknet_getBlockByHash", ["0x" + hash.hex(), "TXN_HASH"]
        )

    async def call(self, contract: bytes, method: str, params: List[Any]):
        params = [
            {
                "contract_address": "0x" + contract.hex(),
                "entry_point_selector": hex(get_selector_from_name(method)),
                "calldata": params,
            },
            "latest",
        ]
        return await self._request("starknet_call", params)
