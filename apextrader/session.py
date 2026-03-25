"""
ApexTrader - Trading Session Management
Encapsulates session state and lifecycle management.
"""

from datetime import datetime, date
from typing import List, Optional


class TradingSession:
    """
    Manages the trading session state and daily statistics.
    Replaces module-level globals with an organized class.
    """

    def __init__(self):
        """Initialize a new trading session."""
        self.daily_pnl = 0.0
        self.daily_reset: Optional[date] = None
        self.trades = 0
        self.trending_stocks: List[str] = []
        self.last_trending_scan = 0

    def reset_daily(self, current_date: date) -> None:
        """
        Reset daily statistics for a new trading day.

        Args:
            current_date: The current date
        """
        if self.daily_reset != current_date:
            self.daily_pnl = 0.0
            self.trades = 0
            self.daily_reset = current_date

    def update_pnl(self, delta: float) -> None:
        """
        Update the daily P&L.

        Args:
            delta: Change in equity
        """
        self.daily_pnl += delta

    def increment_trade_count(self) -> None:
        """Increment the number of trades executed today."""
        self.trades += 1

    def update_trending_stocks(self, stocks: List[str], scan_time: int) -> None:
        """
        Update the trending stocks list and last scan time.

        Args:
            stocks: List of trending stock symbols
            scan_time: Timestamp of the scan
        """
        self.trending_stocks = stocks
        self.last_trending_scan = scan_time

    def should_rescan_trending(self, current_time: int, interval_seconds: int) -> bool:
        """
        Determine if trending stocks should be rescanned.

        Args:
            current_time: Current timestamp
            interval_seconds: Minimum interval between rescans

        Returns:
            True if a rescan is needed
        """
        return (current_time - self.last_trending_scan) >= interval_seconds

    @property
    def profit_factor(self) -> float:
        """Return the current profit factor (trades per hour or similar metric)."""
        return self.daily_pnl / max(self.trades, 1)

    def __repr__(self) -> str:
        return (
            f"TradingSession(date={self.daily_reset}, pnl={self.daily_pnl:.2f}, "
            f"trades={self.trades}, trending_count={len(self.trending_stocks)})"
        )
