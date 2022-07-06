import asyncio
from functools import partial
from typing import Optional

from discord.ext import commands, tasks
import logging

log = logging.getLogger(__name__)


class SomeTaskService:
    def __init__(self, name: str):
        self.name = name
        self.task: Optional[asyncio.Task] = None

    @tasks.loop(seconds=10, reconnect=True)
    async def some_task(self):
        log.debug(f"In task for {self.name}. Calling callback")


    def start(self):
        log.debug(f"Starting {self.name} Task Service")
        self.task = self.some_task.start()
        task_finished = partial(self._task_finished, name=self.name)
        self.task.add_done_callback(task_finished)
        return self.task

    def stop(self):
        self.some_task.cancel()

    @staticmethod
    def _task_finished(future: asyncio.Future, *, name: str):
        try:
            if future.exception() and not future.cancelled():
                log.error(str(future.exception()))
                raise future.exception()
        except asyncio.CancelledError:
            log.debug(f"ProviderTaskService task for {name} was cancelled")
            pass

class ReproduceTaskErrorCog(commands.Cog):

    def __init__(self, bot):
        names = ['Foo', 'Bar', 'Sit', 'Normal']
        for name in names:
            service = SomeTaskService(name)
            service.start()

async def setup(bot):
    await bot.add_cog(ReproduceTaskErrorCog(bot))
