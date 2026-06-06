"""Concrete DeliveryChannel implementations.

The composition root selects which channels are active at startup based on
settings.delivery.channels.
"""

from morning_brief.infrastructure.delivery.email_delivery_channel import EmailDeliveryChannel
from morning_brief.infrastructure.delivery.mock_delivery_channel import MockDeliveryChannel

__all__ = [
    "EmailDeliveryChannel",
    "MockDeliveryChannel",
]
