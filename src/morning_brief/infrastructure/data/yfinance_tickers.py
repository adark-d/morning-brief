from __future__ import annotations

from typing import Final

# Yahoo doesn't expose 2Y directly; ^IRX is 13-week T-bill, used as short-end proxy.
TREASURY_YIELD_TICKERS: Final[dict[str, str]] = {
    "13W": "^IRX",
    "5Y": "^FVX",
    "10Y": "^TNX",
    "30Y": "^TYX",
}

INSTRUMENT_TICKERS: Final[dict[str, str]] = {
    "VIX": "^VIX",  # CBOE Volatility Index
    "CRUDE_OIL": "CL=F",  # WTI crude futures
    "GOLD": "GC=F",  # Gold futures
    "SP500": "^GSPC",  # S&P 500
    "DOLLAR_IDX": "DX-Y.NYB",  # ICE Dollar Index
}

FX_TICKERS: Final[dict[str, str]] = {
    "GBP/USD": "GBPUSD=X",
    "EUR/USD": "EURUSD=X",
    "USD/JPY": "USDJPY=X",
    "USD/CHF": "USDCHF=X",
}
