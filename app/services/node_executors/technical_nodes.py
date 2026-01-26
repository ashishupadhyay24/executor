"""
Node executors for technical analysis nodes
"""

from typing import Any, List, Optional
import logging
import math

from .base import NodeExecutor
from app.models.execution import ExecutionResult, NodeExecutionContext
from app.services.market_data import market_data_service

logger = logging.getLogger(__name__)


def get_last_finite(values: List[float], count: int = 1) -> Optional[List[float]]:
    """
    Get the last N finite (non-NaN, non-None) values from a list.
    
    Args:
        values: List of numeric values
        count: Number of values to return
        
    Returns:
        List of last N finite values, or None if not enough values
    """
    if not values:
        return None
    
    finite_values = []
    for val in reversed(values):
        if val is not None:
            try:
                if not math.isnan(val):
                    finite_values.append(float(val))
                    if len(finite_values) >= count:
                        break
            except (TypeError, ValueError):
                continue
    
    if len(finite_values) < count:
        return None
    
    return list(reversed(finite_values))


class RSIConditionExecutor(NodeExecutor):
    """Executor for RSI condition node - RSI-based trading conditions"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Execute RSI condition check"""
        
        # Validate required config
        error = self.validate_required_config(context, "symbol", "condition")
        if error:
            return self.create_result(False, None, error)
        
        symbol = self.get_config(context, "symbol")
        period = int(self.get_config(context, "period", 14))
        threshold = float(self.get_config(context, "threshold", 30))
        condition = self.get_config(context, "condition", "oversold")
        timeframe = self.get_config(context, "timeframe", "1d")
        
        self.log_info(
            f"Checking RSI condition for {symbol}: {condition} (threshold={threshold}, period={period})",
            context
        )
        
        try:
            # Get historical data (symbol normalization happens in market_data_service)
            hist_data = market_data_service.get_historical_data(
                symbol=symbol,
                period="3mo",
                interval=timeframe
            )
            
            if not hist_data or len(hist_data) < period + 1:
                return self.create_result(
                    False,
                    None,
                    f"Insufficient data for RSI calculation for {symbol} (need at least {period + 1} points, got {len(hist_data) if hist_data else 0})"
                )
            
            # Extract closing prices, filtering out NaN
            prices = []
            for item in hist_data:
                close = item.get("close")
                if close is not None:
                    try:
                        price = float(close)
                        if not math.isnan(price):
                            prices.append(price)
                    except (ValueError, TypeError):
                        continue
            
            if len(prices) < period + 1:
                return self.create_result(
                    False,
                    None,
                    f"Insufficient valid price data for RSI calculation (need {period + 1}, got {len(prices)})"
                )
            
            # Calculate RSI
            rsi_values = market_data_service.calculate_rsi(prices, period)
            
            if not rsi_values:
                return self.create_result(False, None, "Failed to calculate RSI - empty result")
            
            # Get last two finite RSI values for crossing detection
            last_two = get_last_finite(rsi_values, 2)
            if not last_two or len(last_two) < 2:
                # Fall back to just the last value
                last_one = get_last_finite(rsi_values, 1)
                if not last_one:
                    return self.create_result(False, None, "RSI calculation returned only NaN values")
                current_rsi = last_one[0]
                previous_rsi = current_rsi
            else:
                previous_rsi, current_rsi = last_two
            
            # Evaluate condition
            result = False
            
            if condition == "oversold":
                result = current_rsi < threshold
            elif condition == "overbought":
                result = current_rsi > threshold
            elif condition == "crosses_above":
                result = previous_rsi <= threshold < current_rsi
            elif condition == "crosses_below":
                result = previous_rsi >= threshold > current_rsi
            elif condition == "above":
                result = current_rsi > threshold
            elif condition == "below":
                result = current_rsi < threshold
            else:
                return self.create_result(
                    False,
                    None,
                    f"Unsupported RSI condition: {condition}. Supported: oversold, overbought, crosses_above, crosses_below, above, below"
                )
            
            self.log_success(
                f"RSI condition: {symbol} RSI={current_rsi:.2f} (prev={previous_rsi:.2f}) {condition} {threshold} = {result}",
                context
            )
            
            return self.create_result(True, {
                "result": result,
                "conditionMet": result,  # Alias for gate node compatibility
                "rsi": current_rsi,
                "previous_rsi": previous_rsi,
                "threshold": threshold,
                "condition": condition,
                "symbol": symbol,
                "period": period
            })
            
        except Exception as e:
            error_msg = f"Error calculating RSI condition for {symbol}: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)


class MovingAverageConditionExecutor(NodeExecutor):
    """Executor for moving average condition node - MA crossover conditions"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Execute moving average condition check"""
        
        # Validate required config
        error = self.validate_required_config(context, "symbol", "condition")
        if error:
            return self.create_result(False, None, error)
        
        symbol = self.get_config(context, "symbol")
        short_period = int(self.get_config(context, "shortPeriod", 10))
        long_period = int(self.get_config(context, "longPeriod", 20))
        condition = self.get_config(context, "condition", "crossover")
        timeframe = self.get_config(context, "timeframe", "1d")
        ma_type = self.get_config(context, "maType", "SMA")  # SMA or EMA
        
        self.log_info(
            f"Checking MA condition for {symbol}: {condition} ({short_period}/{long_period} {ma_type})",
            context
        )
        
        try:
            # Get historical data (need enough for long MA + some buffer)
            hist_data = market_data_service.get_historical_data(
                symbol=symbol,
                period="6mo",
                interval=timeframe
            )
            
            if not hist_data or len(hist_data) < long_period + 1:
                return self.create_result(
                    False,
                    None,
                    f"Insufficient data for MA calculation for {symbol} (need at least {long_period + 1} points, got {len(hist_data) if hist_data else 0})"
                )
            
            # Extract closing prices, filtering out NaN
            prices = []
            for item in hist_data:
                close = item.get("close")
                if close is not None:
                    try:
                        price = float(close)
                        if not math.isnan(price):
                            prices.append(price)
                    except (ValueError, TypeError):
                        continue
            
            if len(prices) < long_period + 1:
                return self.create_result(
                    False,
                    None,
                    f"Insufficient valid price data for MA calculation (need {long_period + 1}, got {len(prices)})"
                )
            
            # Calculate moving averages
            if ma_type.upper() == "EMA":
                short_ma = market_data_service.calculate_ema(prices, short_period)
                long_ma = market_data_service.calculate_ema(prices, long_period)
            else:  # Default to SMA
                short_ma = market_data_service.calculate_sma(prices, short_period)
                long_ma = market_data_service.calculate_sma(prices, long_period)
            
            if not short_ma or not long_ma:
                return self.create_result(False, None, "Failed to calculate moving averages")
            
            # Get last two finite values for each MA for crossing detection
            short_last_two = get_last_finite(short_ma, 2)
            long_last_two = get_last_finite(long_ma, 2)
            
            if not short_last_two or not long_last_two:
                return self.create_result(False, None, "MA calculation returned insufficient finite values")
            
            previous_short, current_short = short_last_two
            previous_long, current_long = long_last_two
            
            # Evaluate condition
            result = False
            
            if condition == "crossover":
                # Short MA crosses above long MA
                result = previous_short <= previous_long and current_short > current_long
            elif condition == "crossunder":
                # Short MA crosses below long MA
                result = previous_short >= previous_long and current_short < current_long
            elif condition == "above":
                # Short MA is above long MA
                result = current_short > current_long
            elif condition == "below":
                # Short MA is below long MA
                result = current_short < current_long
            elif condition == "golden_cross":
                # Short (typically 50) crosses above Long (typically 200)
                result = previous_short <= previous_long and current_short > current_long
            elif condition == "death_cross":
                # Short crosses below Long
                result = previous_short >= previous_long and current_short < current_long
            else:
                return self.create_result(
                    False,
                    None,
                    f"Unsupported MA condition: {condition}. Supported: crossover, crossunder, above, below, golden_cross, death_cross"
                )
            
            self.log_success(
                f"MA condition: {symbol} {short_period}{ma_type}={current_short:.2f} vs {long_period}{ma_type}={current_long:.2f} {condition} = {result}",
                context
            )
            
            return self.create_result(True, {
                "result": result,
                "conditionMet": result,  # Alias for gate node compatibility
                "short_ma": current_short,
                "long_ma": current_long,
                "previous_short_ma": previous_short,
                "previous_long_ma": previous_long,
                "short_period": short_period,
                "long_period": long_period,
                "ma_type": ma_type,
                "condition": condition,
                "symbol": symbol
            })
            
        except Exception as e:
            error_msg = f"Error calculating MA condition for {symbol}: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)


class PriceTriggerExecutor(NodeExecutor):
    """Executor for price-trigger node - price-based triggers"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Execute price trigger check"""
        
        # Validate required config
        error = self.validate_required_config(context, "symbol", "targetPrice", "condition")
        if error:
            return self.create_result(False, None, error)
        
        symbol = self.get_config(context, "symbol")
        target_price = float(self.get_config(context, "targetPrice"))
        condition = self.get_config(context, "condition", "above")
        
        self.log_info(
            f"Checking price trigger for {symbol}: {condition} target={target_price}",
            context
        )
        
        try:
            # Get current quote (symbol normalization happens in market_data_service)
            quote_data = market_data_service.get_quote(symbol)
            
            if not quote_data:
                return self.create_result(
                    False,
                    None,
                    f"Failed to fetch price for {symbol}"
                )
            
            current_price = float(quote_data["price"])
            previous_price = None
            
            # For crossing conditions, we need historical data
            if condition in ("crosses_above", "crosses_below"):
                # Get recent historical data to find previous close
                hist_data = market_data_service.get_historical_data(
                    symbol=symbol,
                    period="5d",
                    interval="1d"
                )
                
                if hist_data and len(hist_data) >= 2:
                    # Get the second-to-last close price as "previous"
                    prices = []
                    for item in hist_data:
                        close = item.get("close")
                        if close is not None:
                            try:
                                price = float(close)
                                if not math.isnan(price):
                                    prices.append(price)
                            except (ValueError, TypeError):
                                continue
                    
                    if len(prices) >= 2:
                        previous_price = prices[-2]
            
            # Evaluate condition
            result = False
            triggered = False
            
            if condition == "above":
                result = current_price > target_price
                triggered = result
            elif condition == "below":
                result = current_price < target_price
                triggered = result
            elif condition == "crosses_above":
                if previous_price is not None:
                    # True crossing: was at or below, now above
                    result = previous_price <= target_price < current_price
                else:
                    # Fallback: just check if above
                    result = current_price > target_price
                triggered = result
            elif condition == "crosses_below":
                if previous_price is not None:
                    # True crossing: was at or above, now below
                    result = previous_price >= target_price > current_price
                else:
                    # Fallback: just check if below
                    result = current_price < target_price
                triggered = result
            elif condition == "equals" or condition == "at":
                # Price is at target (with small tolerance)
                tolerance = target_price * 0.001  # 0.1% tolerance
                result = abs(current_price - target_price) <= tolerance
                triggered = result
            elif condition == "percent_above":
                # Price is X% above target
                percent_threshold = float(self.get_config(context, "percentThreshold", 5))
                percent_change = ((current_price - target_price) / target_price) * 100
                result = percent_change >= percent_threshold
                triggered = result
            elif condition == "percent_below":
                # Price is X% below target
                percent_threshold = float(self.get_config(context, "percentThreshold", 5))
                percent_change = ((target_price - current_price) / target_price) * 100
                result = percent_change >= percent_threshold
                triggered = result
            else:
                return self.create_result(
                    False,
                    None,
                    f"Unsupported price condition: {condition}. Supported: above, below, crosses_above, crosses_below, equals, at, percent_above, percent_below"
                )
            
            self.log_success(
                f"Price trigger: {symbol} {current_price:.2f} (prev={previous_price:.2f if previous_price else 'N/A'}) {condition} {target_price:.2f} = {result}",
                context
            )
            
            return self.create_result(True, {
                "result": result,
                "conditionMet": result,  # Alias for gate node compatibility
                "triggered": triggered,
                "current_price": current_price,
                "previous_price": previous_price,
                "target_price": target_price,
                "condition": condition,
                "symbol": symbol,
                "quote_data": quote_data
            })
            
        except Exception as e:
            error_msg = f"Error checking price trigger for {symbol}: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)

