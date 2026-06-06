"""Concrete DataProvider implementations.

The composition root selects which implementation to use at startup based on
settings.data.name.
"""

from morning_brief.infrastructure.data.mock_data_provider import MockDataProvider
from morning_brief.infrastructure.data.yfinance_data_provider import YFinanceDataProvider

__all__ = [
    "MockDataProvider",
    "YFinanceDataProvider",
]
