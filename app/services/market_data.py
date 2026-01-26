"""
Market data service using yfinance with caching
"""

import yfinance as yf
import pandas as pd
import math
import re
from typing import Dict, Optional, Any, List, Tuple
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


# yfinance interval constraints: interval -> max period allowed
INTERVAL_MAX_PERIOD = {
    "1m": "7d",
    "2m": "60d",
    "5m": "60d",
    "15m": "60d",
    "30m": "60d",
    "60m": "730d",
    "1h": "730d",
    "90m": "60d",
    "1d": "max",
    "5d": "max",
    "1wk": "max",
    "1mo": "max",
    "3mo": "max",
}

# Period to approximate days (for comparison)
PERIOD_TO_DAYS = {
    "1d": 1,
    "5d": 5,
    "7d": 7,
    "1mo": 30,
    "3mo": 90,
    "6mo": 180,
    "1y": 365,
    "2y": 730,
    "5y": 1825,
    "10y": 3650,
    "ytd": 365,  # approximate
    "max": 99999,
    "60d": 60,
    "730d": 730,
}


def normalize_symbol(symbol: str, default_exchange: str = "NS") -> str:
    """
    Normalize stock symbol to yfinance-compatible format.
    
    Handles:
    - NSE:TCS -> TCS.NS
    - BSE:TCS -> TCS.BO
    - TCS (no suffix) -> TCS.NS (default to NSE for Indian stocks)
    - TCS.NS -> TCS.NS (unchanged)
    - AAPL -> AAPL (US stocks without suffix stay unchanged)
    - ^NSEI -> ^NSEI (indices unchanged)
    
    Args:
        symbol: Input symbol in various formats
        default_exchange: Default exchange suffix (NS for NSE, BO for BSE)
        
    Returns:
        Normalized symbol for yfinance
    """
    if not symbol:
        return symbol
    
    symbol = symbol.strip().upper()
    original_symbol = symbol
    
    # Handle exchange prefix format (NSE:TCS, BSE:TCS)
    if ":" in symbol:
        parts = symbol.split(":", 1)
        exchange = parts[0].upper()
        ticker = parts[1].strip()
        
        if exchange == "NSE":
            return f"{ticker}.NS"
        elif exchange == "BSE":
            return f"{ticker}.BO"
        else:
            # Unknown exchange, return ticker with default
            return f"{ticker}.{default_exchange}"
    
    # If already has a suffix (.NS, .BO, etc.) or is an index (^), keep as is
    if "." in symbol or symbol.startswith("^"):
        return symbol
    
    # Check if it looks like a US stock (common US tickers are typically 1-5 chars)
    # For Indian stocks, we'll add .NS by default
    # Heuristic: If it's all letters and common US pattern, keep as is
    # Otherwise, assume Indian and add .NS
    
    # Common US stock patterns (this is a heuristic)
    us_patterns = [
        r"^[A-Z]{1,5}$",  # Standard US tickers like AAPL, TSLA, MSFT
    ]
    
    # Known US exchanges/suffixes that shouldn't get .NS
    # If someone types AAPL, we should NOT add .NS
    # But if someone types RELIANCE, TCS, INFY we should add .NS
    
    # List of common Indian stock tickers (partial list for heuristic)
    indian_tickers = {
        "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "HINDUNILVR",
        "ITC", "SBIN", "BHARTIARTL", "KOTAKBANK", "LT", "AXISBANK",
        "ASIANPAINT", "MARUTI", "TITAN", "BAJFINANCE", "NESTLEIND",
        "WIPRO", "HCLTECH", "ULTRACEMCO", "SUNPHARMA", "TATAMOTORS",
        "POWERGRID", "NTPC", "ONGC", "TATASTEEL", "JSWSTEEL", "TECHM",
        "ADANIGREEN", "ADANIPORTS", "COALINDIA", "DRREDDY", "CIPLA",
        "GRASIM", "DIVISLAB", "BPCL", "BRITANNIA", "EICHERMOT", "HEROMOTOCO",
        "BAJAJ-AUTO", "BAJAJFINSV", "HDFC", "NIFTY", "BANKNIFTY", "SENSEX",
    }
    
    # If it's a known Indian ticker, add .NS
    if symbol in indian_tickers:
        normalized = f"{symbol}.NS"
        logger.debug(f"Symbol normalized (known Indian): {original_symbol} -> {normalized}")
        return normalized
    
    # If ticker is longer than 5 chars, likely Indian (US rarely exceeds 5)
    if len(symbol) > 5:
        normalized = f"{symbol}.{default_exchange}"
        logger.debug(f"Symbol normalized (length heuristic): {original_symbol} -> {normalized}")
        return normalized
    
    # Default: keep as is (assume US or already valid)
    # User can always explicitly use NSE:SYMBOL or SYMBOL.NS
    return symbol


def sanitize_date(date_str: Optional[str]) -> Optional[str]:
    """
    Sanitize date string to YYYY-MM-DD format.
    
    Handles:
    - "2024-01-15" -> "2024-01-15"
    - "2024-01-15T10:30:00" -> "2024-01-15"
    - "2024-01-15T10:30:00.000Z" -> "2024-01-15"
    """
    if not date_str:
        return None
    
    # Try to extract just the date part
    date_str = date_str.strip()
    
    # If it contains 'T', it's ISO format - take date part
    if "T" in date_str:
        date_str = date_str.split("T")[0]
    
    # If it contains space, take first part
    if " " in date_str:
        date_str = date_str.split(" ")[0]
    
    # Validate it looks like a date
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return date_str
    except ValueError:
        logger.warning(f"Invalid date format: {date_str}")
        return None


def validate_interval_period(interval: str, period: str) -> Tuple[str, str, Optional[str]]:
    """
    Validate and adjust interval/period combination for yfinance constraints.
    
    Args:
        interval: Data interval (1m, 5m, 1h, 1d, etc.)
        period: Data period (1d, 1mo, 1y, etc.)
        
    Returns:
        Tuple of (adjusted_interval, adjusted_period, warning_message)
    """
    interval = interval.lower()
    period = period.lower()
    
    # Default values if invalid
    if interval not in INTERVAL_MAX_PERIOD:
        logger.warning(f"Unknown interval '{interval}', defaulting to '1d'")
        interval = "1d"
    
    if period not in PERIOD_TO_DAYS:
        logger.warning(f"Unknown period '{period}', defaulting to '1mo'")
        period = "1mo"
    
    max_period = INTERVAL_MAX_PERIOD.get(interval, "max")
    
    # If max_period is "max", any period is fine
    if max_period == "max":
        return interval, period, None
    
    # Compare periods
    requested_days = PERIOD_TO_DAYS.get(period, 30)
    max_days = PERIOD_TO_DAYS.get(max_period, 99999)
    
    if requested_days > max_days:
        warning = f"interval={interval} supports max period={max_period}, but {period} was requested. Adjusting to {max_period}."
        logger.warning(warning)
        return interval, max_period, warning
    
    return interval, period, None


def get_last_finite_value(values: List[float]) -> Optional[float]:
    """
    Get the last finite (non-NaN, non-None) value from a list.
    
    Args:
        values: List of numeric values that may contain NaN/None
        
    Returns:
        Last finite value, or None if all values are NaN/None
    """
    if not values:
        return None
    
    for val in reversed(values):
        if val is not None and not (isinstance(val, float) and math.isnan(val)):
            return val
    
    return None


class MarketDataCache:
    """Simple in-memory cache for market data"""
    
    def __init__(self, ttl_seconds: int = 60):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.ttl_seconds = ttl_seconds
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached data if not expired"""
        if key in self.cache:
            entry = self.cache[key]
            if datetime.now() < entry["expires"]:
                return entry["data"]
            else:
                # Remove expired entry
                del self.cache[key]
        return None
    
    def set(self, key: str, data: Any):
        """Set data in cache with expiration"""
        self.cache[key] = {
            "data": data,
            "expires": datetime.now() + timedelta(seconds=self.ttl_seconds)
        }
    
    def clear(self):
        """Clear all cached data"""
        self.cache.clear()


class MarketDataService:
    """Service for fetching market data using yfinance"""
    
    def __init__(self, cache_ttl: int = 60):
        self.cache = MarketDataCache(ttl_seconds=cache_ttl)
        logger.info(f"MarketDataService initialized with cache TTL: {cache_ttl}s")
    
    def get_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get real-time quote for a symbol
        
        Args:
            symbol: Stock symbol (e.g., 'AAPL', 'TSLA', 'TCS', 'NSE:RELIANCE')
            
        Returns:
            Dictionary with quote data or None if failed
        """
        # Normalize symbol for yfinance (e.g., TCS -> TCS.NS, NSE:TCS -> TCS.NS)
        normalized_symbol = normalize_symbol(symbol)
        
        cache_key = f"quote:{normalized_symbol}"
        cached = self.cache.get(cache_key)
        
        if cached is not None:
            logger.debug(f"Using cached quote for {normalized_symbol}")
            return cached
        
        try:
            logger.info(f"Fetching quote for {normalized_symbol} (original: {symbol})")
            ticker = yf.Ticker(normalized_symbol)
            
            # Try to get info first - this helps validate the ticker
            try:
                info = ticker.info
            except Exception as info_err:
                logger.warning(f"Could not fetch info for {normalized_symbol}: {info_err}")
                info = {}
            
            # Get the most recent price data
            hist = ticker.history(period="5d", interval="1d")
            
            if hist.empty:
                # Try with 1m interval for more recent data
                hist = ticker.history(period="1d", interval="1m")
            
            if hist.empty:
                logger.warning(f"No historical data available for {normalized_symbol} (original: {symbol})")
                return None
            
            current_price = hist['Close'].iloc[-1]
            
            # Handle potential NaN values
            if pd.isna(current_price):
                # Try to find the last valid price
                valid_closes = hist['Close'].dropna()
                if valid_closes.empty:
                    logger.warning(f"All price data is NaN for {normalized_symbol}")
                    return None
                current_price = valid_closes.iloc[-1]
            
            open_price = hist['Open'].iloc[0]
            if pd.isna(open_price):
                open_price = current_price
            
            quote_data = {
                "symbol": symbol,  # Return original symbol for user reference
                "normalizedSymbol": normalized_symbol,  # Include normalized for debugging
                "price": float(current_price),
                "regularMarketPrice": float(current_price),
                "regularMarketChange": float(current_price - open_price) if not pd.isna(open_price) else 0.0,
                "regularMarketChangePercent": float(((current_price - open_price) / open_price * 100)) if not pd.isna(open_price) and open_price != 0 else 0.0,
                "regularMarketVolume": int(hist['Volume'].iloc[-1]) if 'Volume' in hist.columns and not pd.isna(hist['Volume'].iloc[-1]) else 0,
                "regularMarketDayHigh": float(hist['High'].max()) if not pd.isna(hist['High'].max()) else float(current_price),
                "regularMarketDayLow": float(hist['Low'].min()) if not pd.isna(hist['Low'].min()) else float(current_price),
                "regularMarketOpen": float(open_price),
                "regularMarketPreviousClose": info.get("previousClose", float(open_price)),
                "timestamp": datetime.now().isoformat(),
                "source": "yfinance",
                "dataQuality": "realtime"
            }
            
            self.cache.set(cache_key, quote_data)
            return quote_data
            
        except Exception as e:
            logger.error(f"Error fetching quote for {normalized_symbol} (original: {symbol}): {str(e)}")
            return None
    
    def get_historical_data(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        period: str = "1mo",
        interval: str = "1d"
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Get historical OHLCV data
        
        Args:
            symbol: Stock symbol (e.g., 'AAPL', 'TCS', 'NSE:RELIANCE')
            start_date: Start date (YYYY-MM-DD or ISO format)
            end_date: End date (YYYY-MM-DD or ISO format)
            period: Period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
            interval: Data interval (1m, 5m, 15m, 30m, 1h, 1d, 1wk, 1mo)
            
        Returns:
            List of OHLCV data dictionaries sorted by date ascending
        """
        # Normalize symbol for yfinance
        normalized_symbol = normalize_symbol(symbol)
        
        # Sanitize dates
        clean_start = sanitize_date(start_date)
        clean_end = sanitize_date(end_date)
        
        # Validate and adjust interval/period if using period-based fetch
        warning_msg = None
        if not (clean_start and clean_end):
            interval, period, warning_msg = validate_interval_period(interval, period)
        
        # Build cache key with all relevant parameters
        cache_key = f"hist:{normalized_symbol}:{interval}:{period}:{clean_start}:{clean_end}"
        cached = self.cache.get(cache_key)
        
        if cached is not None:
            logger.debug(f"Using cached historical data for {normalized_symbol}")
            return cached
        
        try:
            logger.info(
                f"Fetching historical data for {normalized_symbol} (original: {symbol}), "
                f"period={period}, interval={interval}, start={clean_start}, end={clean_end}"
            )
            
            if warning_msg:
                logger.warning(warning_msg)
            
            ticker = yf.Ticker(normalized_symbol)
            
            if clean_start and clean_end:
                hist = ticker.history(start=clean_start, end=clean_end, interval=interval)
            else:
                hist = ticker.history(period=period, interval=interval)
            
            if hist.empty:
                logger.warning(
                    f"No historical data available for {normalized_symbol} (original: {symbol}) "
                    f"with period={period}, interval={interval}, start={clean_start}, end={clean_end}"
                )
                return None
            
            # Convert DataFrame to list of dictionaries
            data = []
            for index, row in hist.iterrows():
                # Skip rows with all NaN values
                if pd.isna(row['Close']) and pd.isna(row['Open']):
                    continue
                
                data.append({
                    "date": index.isoformat(),
                    "open": float(row['Open']) if not pd.isna(row['Open']) else 0.0,
                    "high": float(row['High']) if not pd.isna(row['High']) else 0.0,
                    "low": float(row['Low']) if not pd.isna(row['Low']) else 0.0,
                    "close": float(row['Close']) if not pd.isna(row['Close']) else 0.0,
                    "volume": int(row['Volume']) if 'Volume' in row and not pd.isna(row['Volume']) else 0,
                    "symbol": symbol,  # Include original symbol
                    "normalizedSymbol": normalized_symbol,
                })
            
            if not data:
                logger.warning(f"All data points were NaN for {normalized_symbol}")
                return None
            
            # Ensure data is sorted by date ascending (important for indicators)
            data.sort(key=lambda x: x["date"])
            
            logger.info(f"Retrieved {len(data)} historical data points for {normalized_symbol} (original: {symbol})")
            
            # Cache the result
            self.cache.set(cache_key, data)
            
            return data
            
        except Exception as e:
            logger.error(
                f"Error fetching historical data for {normalized_symbol} (original: {symbol}): {str(e)}"
            )
            return None
    
    def get_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get company information
        
        Args:
            symbol: Stock symbol (e.g., 'AAPL', 'TCS', 'NSE:RELIANCE')
            
        Returns:
            Dictionary with company info
        """
        # Normalize symbol for yfinance
        normalized_symbol = normalize_symbol(symbol)
        
        cache_key = f"info:{normalized_symbol}"
        cached = self.cache.get(cache_key)
        
        if cached is not None:
            return cached
        
        try:
            logger.info(f"Fetching info for {normalized_symbol} (original: {symbol})")
            ticker = yf.Ticker(normalized_symbol)
            info = ticker.info
            
            # Add original and normalized symbols for reference
            info["_originalSymbol"] = symbol
            info["_normalizedSymbol"] = normalized_symbol
            
            # Cache with longer TTL for company info (5 minutes)
            self.cache.set(cache_key, info)
            return info
            
        except Exception as e:
            logger.error(f"Error fetching info for {normalized_symbol} (original: {symbol}): {str(e)}")
            return None
    
    def calculate_rsi(self, prices: List[float], period: int = 14) -> List[float]:
        """
        Calculate RSI (Relative Strength Index)
        
        Args:
            prices: List of closing prices
            period: RSI period (default 14)
            
        Returns:
            List of RSI values
        """
        if len(prices) < period + 1:
            return []
        
        # Convert to pandas Series for easier calculation
        prices_series = pd.Series(prices)
        
        # Calculate price changes
        delta = prices_series.diff()
        
        # Separate gains and losses
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        # Calculate RS and RSI
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi.tolist()
    
    def calculate_sma(self, prices: List[float], period: int) -> List[float]:
        """
        Calculate Simple Moving Average
        
        Args:
            prices: List of closing prices
            period: SMA period
            
        Returns:
            List of SMA values
        """
        if len(prices) < period:
            return []
        
        prices_series = pd.Series(prices)
        sma = prices_series.rolling(window=period).mean()
        return sma.tolist()
    
    def calculate_ema(self, prices: List[float], period: int) -> List[float]:
        """
        Calculate Exponential Moving Average
        
        Args:
            prices: List of closing prices
            period: EMA period
            
        Returns:
            List of EMA values
        """
        if len(prices) < period:
            return []
        
        prices_series = pd.Series(prices)
        ema = prices_series.ewm(span=period, adjust=False).mean()
        return ema.tolist()
    
    def calculate_macd(
        self,
        prices: List[float],
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9
    ) -> Dict[str, List[float]]:
        """
        Calculate MACD (Moving Average Convergence Divergence)
        
        Args:
            prices: List of closing prices
            fast_period: Fast EMA period (default 12)
            slow_period: Slow EMA period (default 26)
            signal_period: Signal line period (default 9)
            
        Returns:
            Dictionary with macd, signal, and histogram
        """
        if len(prices) < slow_period:
            return {"macd": [], "signal": [], "histogram": []}
        
        prices_series = pd.Series(prices)
        
        # Calculate EMAs
        fast_ema = prices_series.ewm(span=fast_period, adjust=False).mean()
        slow_ema = prices_series.ewm(span=slow_period, adjust=False).mean()
        
        # MACD line
        macd = fast_ema - slow_ema
        
        # Signal line
        signal = macd.ewm(span=signal_period, adjust=False).mean()
        
        # Histogram
        histogram = macd - signal
        
        return {
            "macd": macd.tolist(),
            "signal": signal.tolist(),
            "histogram": histogram.tolist()
        }
    
    def calculate_bollinger_bands(
        self,
        prices: List[float],
        period: int = 20,
        std_dev: float = 2.0
    ) -> Dict[str, List[float]]:
        """
        Calculate Bollinger Bands
        
        Args:
            prices: List of closing prices
            period: Moving average period (default 20)
            std_dev: Standard deviation multiplier (default 2.0)
            
        Returns:
            Dictionary with upper, middle, and lower bands
        """
        if len(prices) < period:
            return {"upper": [], "middle": [], "lower": []}
        
        prices_series = pd.Series(prices)
        
        # Middle band (SMA)
        middle = prices_series.rolling(window=period).mean()
        
        # Standard deviation
        std = prices_series.rolling(window=period).std()
        
        # Upper and lower bands
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        
        return {
            "upper": upper.tolist(),
            "middle": middle.tolist(),
            "lower": lower.tolist()
        }


# Global instance
market_data_service = MarketDataService(cache_ttl=60)

