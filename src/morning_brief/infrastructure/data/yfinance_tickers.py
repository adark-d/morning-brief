"""Yahoo Finance ticker definitions.

These mappings are internal to the yfinance implementation. If we ever swap
to a different data provider, this module is replaced — the rest of the
infrastructure layer is unaffected.

Maturity-to-ticker map for US Treasuries:
    Yahoo only exposes a subset of Treasury yields. We work with what's available
    and let the input guardrail decide if the coverage is sufficient for a brief.
"""

from __future__ import annotations

from typing import Final

# Treasury yield tickers — what Yahoo gives us
# (Yahoo doesn't expose 2Y directly; ^IRX is 13-week T-bill, used as short-end proxy)
TREASURY_YIELD_TICKERS: Final[dict[str, str]] = {
    "13W": "^IRX",
    "5Y": "^FVX",
    "10Y": "^TNX",
    "30Y": "^TYX",
}

# Equity, commodity, volatility instruments
INSTRUMENT_TICKERS: Final[dict[str, str]] = {
    "VIX": "^VIX",  # CBOE Volatility Index
    "CRUDE_OIL": "CL=F",  # WTI crude futures
    "GOLD": "GC=F",  # Gold futures
    "SP500": "^GSPC",  # S&P 500
    "DOLLAR_IDX": "DX-Y.NYB",  # ICE Dollar Index
}

# FX pairs — pair name to Yahoo ticker
FX_TICKERS: Final[dict[str, str]] = {
    "GBP/USD": "GBPUSD=X",
    "EUR/USD": "EURUSD=X",
    "USD/JPY": "USDJPY=X",
    "USD/CHF": "USDCHF=X",
}
