"""
Node executors for data input nodes
"""

from typing import Any, Dict, List, Optional
import logging

from .base import NodeExecutor
from app.models.execution import ExecutionResult, NodeExecutionContext, LogLevel
from app.services.market_data import market_data_service

logger = logging.getLogger(__name__)


class MarketDataExecutor(NodeExecutor):
    """Executor for market-data node - fetches real-time market data"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Fetch real-time market data for a symbol"""
        
        # Validate required config
        error = self.validate_required_config(context, "symbol")
        if error:
            return self.create_result(False, None, error)
        
        symbol = self.get_config(context, "symbol")
        data_type = self.get_config(context, "dataType", "live_price")
        
        self.log_info(f"Fetching market data for {symbol}, type={data_type}", context)
        
        try:
            # Get quote data
            quote_data = market_data_service.get_quote(symbol)
            
            if quote_data is None:
                error_msg = f"Failed to fetch market data for {symbol}"
                self.log_error(error_msg, context)
                return self.create_result(False, None, error_msg)
            
            self.log_success(
                f"Market data fetched: {symbol} @ ${quote_data['price']:.2f}",
                context
            )
            
            return self.create_result(True, quote_data)
            
        except Exception as e:
            error_msg = f"Error fetching market data: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)


class HistoricalDataExecutor(NodeExecutor):
    """Executor for historical-data node - fetches historical OHLCV data"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Fetch historical OHLCV data for a symbol"""
        
        # Validate required config
        error = self.validate_required_config(context, "symbol")
        if error:
            return self.create_result(False, None, error)
        
        symbol = self.get_config(context, "symbol")
        start_date = self.get_config(context, "startDate")
        end_date = self.get_config(context, "endDate")
        period = self.get_config(context, "period", "1mo")
        interval = self.get_config(context, "interval", "1d")
        
        # Build detailed request info for logging
        request_info = f"symbol={symbol}, period={period}, interval={interval}"
        if start_date:
            request_info += f", startDate={start_date}"
        if end_date:
            request_info += f", endDate={end_date}"
        
        self.log_info(f"Fetching historical data: {request_info}", context)
        
        # Warn if period/interval combination might return very few data points
        if not start_date and not end_date:
            if period == "1d" and interval in ["1d", "1wk", "1mo"]:
                self.log_warning(
                    f"Configuration may return only 1-2 data points (period={period}, interval={interval}). "
                    f"For technical indicators, consider period='1mo' or longer.",
                    context
                )
        
        try:
            # Get historical data (market_data_service handles symbol normalization)
            hist_data = market_data_service.get_historical_data(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                period=period,
                interval=interval
            )
            
            if hist_data is None or len(hist_data) == 0:
                # Include normalized symbol info if available
                normalized_info = ""
                if hist_data is None:
                    # Try to get what the normalized symbol would be for the error message
                    from app.services.market_data import normalize_symbol
                    normalized = normalize_symbol(symbol)
                    if normalized != symbol:
                        normalized_info = f" (normalized to: {normalized})"
                
                error_msg = (
                    f"No historical data available for {symbol}{normalized_info}. "
                    f"Request: {request_info}. "
                    f"Tips: Check if the symbol is valid for Yahoo Finance. "
                    f"For NSE stocks, try 'NSE:SYMBOL' or 'SYMBOL.NS' format."
                )
                self.log_error(error_msg, context)
                return self.create_result(False, None, error_msg)
            
            # Extract normalized symbol from result if available
            normalized_symbol = hist_data[0].get("normalizedSymbol", symbol) if hist_data else symbol
            
            self.log_success(
                f"Historical data fetched: {len(hist_data)} data points for {symbol} "
                f"(normalized: {normalized_symbol}), date range: {hist_data[0]['date'][:10]} to {hist_data[-1]['date'][:10]}",
                context
            )
            
            return self.create_result(True, hist_data)
            
        except Exception as e:
            error_msg = f"Error fetching historical data for {symbol}: {str(e)}. Request: {request_info}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)


class TechnicalIndicatorExecutor(NodeExecutor):
    """Executor for technical-indicator node - calculates technical indicators"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Calculate technical indicators from price data"""
        
        # Validate required config
        error = self.validate_required_config(context, "indicator")
        if error:
            return self.create_result(False, None, error)
        
        indicator = self.get_config(context, "indicator")
        period = self.get_config(context, "period", 14)
        symbol = self.get_config(context, "symbol")
        
        # Ensure period is an integer
        try:
            period = int(period)
        except (ValueError, TypeError):
            period = 14
        
        # Get input data (can be from historical data node or market data)
        input_data = self.get_input(context, "default")
        
        # If no input data, try to fetch historical data for the symbol
        if input_data is None and symbol:
            self.log_info(f"No input data, fetching historical data for {symbol}", context)
            hist_data = market_data_service.get_historical_data(
                symbol=symbol,
                period="1y",
                interval="1d"
            )
            if hist_data:
                input_data = hist_data
        
        if input_data is None:
            return self.create_result(
                False,
                None,
                "No input data available and no symbol configured"
            )
        
        self.log_info(f"Calculating {indicator} with period {period}", context)
        
        # Log input data details for debugging
        if isinstance(input_data, list):
            self.log_info(f"Input data: list with {len(input_data)} items", context)
            if input_data and isinstance(input_data[0], dict):
                first_keys = list(input_data[0].keys())
                self.log_info(f"First item keys: {first_keys}", context)
        elif isinstance(input_data, dict):
            self.log_info(f"Input data: dict with keys: {list(input_data.keys())}", context)
        
        try:
            # Extract prices from input data (sorted by date)
            prices = self._extract_prices(input_data)
            
            if not prices:
                return self.create_result(
                    False, 
                    None, 
                    f"Could not extract prices from input data. Data type: {type(input_data).__name__}, "
                    f"Length: {len(input_data) if isinstance(input_data, (list, dict)) else 'N/A'}. "
                    f"Expected list of dicts with 'close' or 'price' keys."
                )
            
            self.log_info(f"Extracted {len(prices)} price points for {indicator} calculation", context)
            
            # Check if we have enough data for the indicator
            min_required = period + 1
            if len(prices) < min_required:
                # Provide helpful guidance
                if isinstance(input_data, list) and len(input_data) > len(prices):
                    hint = f"Input had {len(input_data)} items but only {len(prices)} had valid prices (non-NaN)."
                else:
                    hint = f"Ensure the previous historical-data node fetches enough data (e.g., period='3mo' for daily data)."
                
                return self.create_result(
                    False,
                    None,
                    f"Insufficient data for {indicator}: need at least {min_required} points, got {len(prices)}. "
                    f"{hint}"
                )
            
            # Calculate indicator based on type
            result_data = None
            
            if indicator.upper() == "RSI":
                rsi_values = market_data_service.calculate_rsi(prices, period)
                current_rsi = self._get_last_finite(rsi_values)
                result_data = {
                    "indicator": "RSI",
                    "values": rsi_values,
                    "current": current_rsi,
                    "period": period,
                    "dataPoints": len(prices)
                }
                
            elif indicator.upper() == "SMA":
                sma_values = market_data_service.calculate_sma(prices, period)
                current_sma = self._get_last_finite(sma_values)
                result_data = {
                    "indicator": "SMA",
                    "values": sma_values,
                    "current": current_sma,
                    "period": period,
                    "dataPoints": len(prices)
                }
                
            elif indicator.upper() == "EMA":
                ema_values = market_data_service.calculate_ema(prices, period)
                current_ema = self._get_last_finite(ema_values)
                result_data = {
                    "indicator": "EMA",
                    "values": ema_values,
                    "current": current_ema,
                    "period": period,
                    "dataPoints": len(prices)
                }
                
            elif indicator.upper() == "MACD":
                fast_period = int(self.get_config(context, "fastPeriod", 12))
                slow_period = int(self.get_config(context, "slowPeriod", 26))
                signal_period = int(self.get_config(context, "signalPeriod", 9))
                
                macd_data = market_data_service.calculate_macd(
                    prices,
                    fast_period,
                    slow_period,
                    signal_period
                )
                result_data = {
                    "indicator": "MACD",
                    "macd": macd_data["macd"],
                    "signal": macd_data["signal"],
                    "histogram": macd_data["histogram"],
                    "current_macd": self._get_last_finite(macd_data["macd"]),
                    "current_signal": self._get_last_finite(macd_data["signal"]),
                    "current_histogram": self._get_last_finite(macd_data["histogram"]),
                    "current": self._get_last_finite(macd_data["macd"]),  # Alias for consistency
                    "dataPoints": len(prices)
                }
                
            elif indicator.upper() in ("BOLLINGER", "BB", "BOLLINGER_BANDS"):
                std_dev = float(self.get_config(context, "stdDev", 2.0))
                bb_data = market_data_service.calculate_bollinger_bands(
                    prices,
                    period,
                    std_dev
                )
                result_data = {
                    "indicator": "BOLLINGER_BANDS",
                    "upper": bb_data["upper"],
                    "middle": bb_data["middle"],
                    "lower": bb_data["lower"],
                    "current_upper": self._get_last_finite(bb_data["upper"]),
                    "current_middle": self._get_last_finite(bb_data["middle"]),
                    "current_lower": self._get_last_finite(bb_data["lower"]),
                    "current": self._get_last_finite(bb_data["middle"]),  # Middle band as default current
                    "period": period,
                    "std_dev": std_dev,
                    "dataPoints": len(prices)
                }
                
            elif indicator.upper() == "ATR":
                # ATR needs high, low, close - extract from input data
                atr_data = self._calculate_atr(input_data, period)
                if atr_data:
                    result_data = {
                        "indicator": "ATR",
                        "values": atr_data,
                        "current": self._get_last_finite(atr_data),
                        "period": period,
                        "dataPoints": len(prices)
                    }
                else:
                    return self.create_result(False, None, "Could not calculate ATR - need OHLC data")
            else:
                return self.create_result(
                    False,
                    None,
                    f"Unsupported indicator: {indicator}. Supported: RSI, SMA, EMA, MACD, BOLLINGER/BB, ATR"
                )
            
            if result_data:
                current_value = result_data.get("current")
                if current_value is None:
                    self.log_warning(
                        f"{indicator} calculated but current value is None (possible NaN issue)",
                        context
                    )
                else:
                    self.log_success(
                        f"{indicator} calculated: current={current_value:.4f}, period={period}, data points={len(prices)}",
                        context
                    )
                return self.create_result(True, result_data)
            else:
                return self.create_result(False, None, f"Failed to calculate {indicator}")
            
        except Exception as e:
            error_msg = f"Error calculating {indicator}: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)
    
    def _get_last_finite(self, values: List[float]) -> Optional[float]:
        """Get the last finite (non-NaN, non-None) value from a list"""
        if not values:
            return None
        
        import math
        for val in reversed(values):
            if val is not None:
                try:
                    if not math.isnan(val):
                        return float(val)
                except (TypeError, ValueError):
                    continue
        
        return None
    
    def _extract_prices(self, data: Any) -> List[float]:
        """
        Extract closing prices from various data formats.
        Sorts by date if available to ensure chronological order.
        """
        prices = []
        
        try:
            if isinstance(data, list):
                # Sort by date if items have date field
                sorted_data = data
                if data and isinstance(data[0], dict):
                    # Check for date fields
                    date_keys = ["date", "Date", "datetime", "timestamp", "time"]
                    date_key = None
                    for key in date_keys:
                        if key in data[0]:
                            date_key = key
                            break
                    
                    if date_key:
                        try:
                            sorted_data = sorted(data, key=lambda x: x.get(date_key, ""))
                        except Exception:
                            sorted_data = data  # Keep original order if sort fails
                
                # Extract prices from sorted data
                price_keys = ["close", "Close", "price", "Price", "last", "Last", "adjClose", "Adj Close"]
                
                for item in sorted_data:
                    if isinstance(item, dict):
                        for key in price_keys:
                            if key in item and item[key] is not None:
                                try:
                                    price = float(item[key])
                                    import math
                                    if not math.isnan(price):
                                        prices.append(price)
                                        break
                                except (ValueError, TypeError):
                                    continue
                    elif isinstance(item, (int, float)):
                        import math
                        if not math.isnan(item):
                            prices.append(float(item))
            
            elif isinstance(data, dict):
                # Single data point - extract price
                price_keys = ["price", "regularMarketPrice", "close", "Close", "last", "Last"]
                for key in price_keys:
                    if key in data and data[key] is not None:
                        try:
                            price = float(data[key])
                            import math
                            if not math.isnan(price):
                                prices.append(price)
                                break
                        except (ValueError, TypeError):
                            continue
        
        except Exception as e:
            logger.warning(f"Error extracting prices: {str(e)}")
        
        return prices
    
    def _calculate_atr(self, data: Any, period: int) -> Optional[List[float]]:
        """Calculate Average True Range from OHLC data"""
        if not isinstance(data, list) or len(data) < period + 1:
            return None
        
        try:
            # Sort by date
            date_key = None
            for key in ["date", "Date", "datetime", "timestamp"]:
                if key in data[0]:
                    date_key = key
                    break
            
            if date_key:
                sorted_data = sorted(data, key=lambda x: x.get(date_key, ""))
            else:
                sorted_data = data
            
            # Extract OHLC
            highs = []
            lows = []
            closes = []
            
            for item in sorted_data:
                h = item.get("high") or item.get("High")
                l = item.get("low") or item.get("Low")
                c = item.get("close") or item.get("Close")
                
                if h is not None and l is not None and c is not None:
                    highs.append(float(h))
                    lows.append(float(l))
                    closes.append(float(c))
            
            if len(closes) < period + 1:
                return None
            
            # Calculate True Range
            true_ranges = []
            for i in range(1, len(closes)):
                tr = max(
                    highs[i] - lows[i],
                    abs(highs[i] - closes[i-1]),
                    abs(lows[i] - closes[i-1])
                )
                true_ranges.append(tr)
            
            # Calculate ATR using simple moving average
            import pandas as pd
            tr_series = pd.Series(true_ranges)
            atr = tr_series.rolling(window=period).mean()
            
            return atr.tolist()
            
        except Exception as e:
            logger.warning(f"Error calculating ATR: {str(e)}")
            return None

