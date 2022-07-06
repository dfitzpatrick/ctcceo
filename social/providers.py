from typing import Any

from social.abc import AsyncQueryStrategy, BaseProvider
import aiohttp


class QueryStringStrategy:

    async def get(self, endpoint: str, api_key: str) -> Any:
        params = (("api_key", api_key),)
        async with aiohttp.ClientSession() as session:
            async with session.get(endpoint, params=params) as resp:
                return resp.json()


    async def post(self):
        return NotImplemented

    async def put(self):
        return NotImplemented


class TwitchProvider(BaseProvider):

    def __init__(self, api_key: str):
        super(TwitchProvider, self).__init__(api_key, QueryStringStrategy())

