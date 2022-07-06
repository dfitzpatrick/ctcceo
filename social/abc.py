from typing import Protocol, Any
from abc import abstractmethod, ABC

class AsyncQueryStrategy(Protocol):



    async def get(self, endpoint: str, api_key: str) -> Any:
        ...

    async def post(self, endpoint: str, api_key: str) -> Any:
        ...

    async def put(self, endpoint: str, api_key: str) -> Any:
        ...


class BaseProvider(ABC):

    def __init__(self, api_key: str, query_strategy: AsyncQueryStrategy):
        self._api_key = api_key
        self.query_strategy = query_strategy

    @abstractmethod
    @property
    def base_url(self):
        return NotImplemented

    @abstractmethod
    @property
    def subscriber_count(self) -> int:
        return NotImplemented






