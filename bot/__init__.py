from __future__ import annotations

import logging
import os
import sys
from logging import StreamHandler, FileHandler
import sentry_sdk
sentry_sdk.init(
    dsn="https://6e802b09c5ef4ebbb1cdc1673066e6e9@o391198.ingest.sentry.io/6556670",

    # Set traces_sample_rate to 1.0 to capture 100%
    # of transactions for performance monitoring.
    # We recommend adjusting this value in production.
    traces_sample_rate=1.0
)

BASE_DIR = os.path.normpath(os.path.dirname(os.path.realpath(__file__)))
handler_console = StreamHandler(stream=sys.stdout)
handler_console.setLevel(logging.DEBUG)
handler_filestream = FileHandler(filename=f"{BASE_DIR}/bot.log", encoding='utf-8')
handler_filestream.setLevel(logging.INFO)

logging_handlers = [
        handler_console,
        handler_filestream
]

logging.basicConfig(
    format="%(asctime)s | %(name)25s | %(funcName)25s | %(levelname)6s | %(message)s",
    datefmt="%b %d %H:%M:%S",
    level=logging.DEBUG,
    handlers=logging_handlers
)
logging.getLogger('asyncio').setLevel(logging.ERROR)
logging.getLogger('discord').setLevel(logging.ERROR)
logging.getLogger('websockets').setLevel(logging.ERROR)
log = logging.getLogger(__name__)


