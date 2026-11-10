"""内存事件总线插件。

文档第 2 节事件总线插件,生产可替换 Kafka/RabbitMQ。
文档未定义发布/订阅接口【已确认 Q2】;这里实现最小 publish/subscribe 并保留最近事件。
"""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Callable
from typing import Any

from .base import EventBusPlugin


class MemoryEventBusPlugin(EventBusPlugin):
    plugin_id = "memory_event_bus"
    display_name = "内存事件总线"
    description = "进程内事件投递,用于 Demo;生产可替换 Kafka/RabbitMQ"
    config_schema = {}

    def __init__(self, config: dict[str, Any] | None = None, dependencies: dict[str, Any] | None = None):
        super().__init__(config, dependencies)
        self._lock = threading.RLock()
        self._subscribers: dict[str, list[Callable[[dict[str, Any]], None]]] = {}
        self._history: deque[dict[str, Any]] = deque(maxlen=1000)

    def subscribe(self, event_type: str, handler: Callable[[dict[str, Any]], None]) -> None:
        with self._lock:
            self._subscribers.setdefault(event_type, []).append(handler)

    async def publish(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("event_type", ""))
        with self._lock:
            self._history.append(event)
            handlers = list(self._subscribers.get(event_type, []))
        for handler in handlers:
            handler(event)

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._history)[-limit:]
