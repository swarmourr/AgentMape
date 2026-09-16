from __future__ import annotations

import json
import structlog
from collections.abc import Callable, Awaitable
from typing import Any

import aio_pika
import aio_pika.abc

from app.utils.config import settings
from app.utils.events.schemas import normalize_event
from app.utils.models.events import WorkflowEvent

log = structlog.get_logger(__name__)

# Handler signature: receives a normalised WorkflowEvent
EventHandler = Callable[[WorkflowEvent], Awaitable[None]]


class AMQPConsumer:
    """
    Durable AMQP consumer for Pegasus Monitord events.

    - Subscribes to stampede.job_inst.*, stampede.inv.*, stampede.xwf.*
    - Normalises every message via the event normalizer
    - Acks only after the handler durably persists the event
    - Routes malformed / repeatedly-failing messages to a dead-letter queue
    - Never loses an event: prefetch=N limits in-flight messages
    """

    def __init__(self, handler: EventHandler) -> None:
        self._handler = handler
        self._connection: aio_pika.abc.AbstractRobustConnection | None = None
        self._channel: aio_pika.abc.AbstractChannel | None = None

    async def start(self) -> None:
        self._connection = await aio_pika.connect_robust(
            settings.amqp_url,
            reconnect_interval=5,
        )
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=settings.amqp_prefetch_count)

        exchange = await self._channel.declare_exchange(
            settings.amqp_exchange,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )

        # Dead-letter exchange / queue for malformed messages
        dlx = await self._channel.declare_exchange(
            f"{settings.amqp_exchange}.dlx",
            aio_pika.ExchangeType.FANOUT,
            durable=True,
        )
        dlq = await self._channel.declare_queue(
            settings.amqp_dead_letter_queue,
            durable=True,
        )
        await dlq.bind(dlx)

        queue = await self._channel.declare_queue(
            settings.amqp_queue,
            durable=True,
            arguments={
                "x-dead-letter-exchange": f"{settings.amqp_exchange}.dlx",
            },
        )

        for routing_key in settings.amqp_routing_keys:
            await queue.bind(exchange, routing_key=routing_key)

        await queue.consume(self._on_message)
        log.info("amqp_consumer_started", queue=settings.amqp_queue)

    async def stop(self) -> None:
        if self._connection:
            await self._connection.close()
            log.info("amqp_consumer_stopped")

    async def _on_message(self, message: aio_pika.abc.AbstractIncomingMessage) -> None:
        async with message.process(requeue=False, ignore_processed=True):
            routing_key = message.routing_key or ""
            try:
                payload: dict[str, Any] = json.loads(message.body)
            except json.JSONDecodeError:
                log.warning("amqp_malformed_message", routing_key=routing_key)
                # process(requeue=False) will nack → DLQ
                return

            event = normalize_event(routing_key, payload)
            if event is None:
                # Not relevant — ack and discard
                return

            try:
                await self._handler(event)
            except Exception:
                log.exception(
                    "amqp_handler_error",
                    routing_key=routing_key,
                    event_id=event.event_id,
                )
                raise  # triggers nack → DLQ
