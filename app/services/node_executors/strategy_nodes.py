"""
Node executors for strategy nodes
"""

from typing import Any, Dict, Optional
import logging

from .base import NodeExecutor
from app.models.execution import ExecutionResult, NodeExecutionContext

logger = logging.getLogger(__name__)


class SignalGeneratorExecutor(NodeExecutor):
    """Executor for signal-generator node - generates buy/sell/hold signals"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Generate trading signal from input conditions"""
        
        # Get input data (from condition nodes, indicators, etc.)
        input_data = self.get_input(context, "default")
        
        # Get signal generation logic
        signal_type = self.get_config(context, "signalType", "auto")
        threshold = self.get_config(context, "threshold", 0.5)
        
        self.log_info(f"Generating signal, type={signal_type}", context)
        
        try:
            signal = None
            confidence = 0.0
            
            if signal_type == "auto":
                # Auto-generate from input conditions
                if isinstance(input_data, dict):
                    # Check for boolean results
                    if "result" in input_data:
                        result = input_data["result"]
                        if result:
                            signal = "BUY"
                            confidence = 0.8
                        else:
                            signal = "HOLD"
                            confidence = 0.5
                    
                    # Check for RSI/indicator values
                    elif "rsi" in input_data:
                        rsi = input_data["rsi"]
                        if rsi < 30:
                            signal = "BUY"
                            confidence = 0.9
                        elif rsi > 70:
                            signal = "SELL"
                            confidence = 0.9
                        else:
                            signal = "HOLD"
                            confidence = 0.5
                    
                    # Check for MA crossover
                    elif "short_ma" in input_data and "long_ma" in input_data:
                        short_ma = input_data["short_ma"]
                        long_ma = input_data["long_ma"]
                        if short_ma > long_ma:
                            signal = "BUY"
                            confidence = 0.7
                        else:
                            signal = "SELL"
                            confidence = 0.7
                
                elif isinstance(input_data, bool):
                    signal = "BUY" if input_data else "HOLD"
                    confidence = 0.7
                
                else:
                    signal = "HOLD"
                    confidence = 0.5
            
            elif signal_type == "buy":
                signal = "BUY"
                confidence = float(threshold)
            
            elif signal_type == "sell":
                signal = "SELL"
                confidence = float(threshold)
            
            elif signal_type == "hold":
                signal = "HOLD"
                confidence = 0.5
            
            if signal is None:
                signal = "HOLD"
                confidence = 0.5
            
            self.log_success(f"Signal generated: {signal} (confidence: {confidence:.2f})", context)
            
            return self.create_result(True, {
                "signal": signal,
                "confidence": confidence,
                "timestamp": self._get_timestamp()
            })
            
        except Exception as e:
            error_msg = f"Error generating signal: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)
    
    def _get_timestamp(self) -> str:
        from datetime import datetime
        return datetime.now().isoformat()


class EntryConditionExecutor(NodeExecutor):
    """Executor for entry-condition node - checks if entry conditions are met"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Check entry conditions"""
        
        # Get input conditions
        input_data = self.get_input(context, "default")
        
        # Also check for additional inputs
        if input_data is None and context.inputs:
            input_data = next(iter(context.inputs.values()), None)
        
        condition_type = self.get_config(context, "conditionType", "all")
        
        self.log_info(f"Checking entry conditions, type={condition_type}", context)
        
        try:
            result = False
            
            # Evaluate conditions
            if isinstance(input_data, dict):
                # Check common result keys
                if "result" in input_data:
                    result = bool(input_data["result"])
                elif "conditionMet" in input_data:
                    result = bool(input_data["conditionMet"])
                elif "should_enter" in input_data:
                    result = bool(input_data["should_enter"])
                elif "entry_allowed" in input_data:
                    result = bool(input_data["entry_allowed"])
                else:
                    # Multiple conditions - check for boolean values
                    bool_results = []
                    for k, v in input_data.items():
                        if isinstance(v, bool):
                            bool_results.append(v)
                        elif isinstance(v, dict):
                            # Nested result
                            if "result" in v:
                                bool_results.append(bool(v["result"]))
                            elif "conditionMet" in v:
                                bool_results.append(bool(v["conditionMet"]))
                    
                    if bool_results:
                        if condition_type == "all":
                            result = all(bool_results)
                        else:  # any
                            result = any(bool_results)
                    else:
                        # No boolean conditions found - check if there's any truthy signal
                        result = bool(input_data.get("signal") == "BUY" or input_data.get("triggered", False))
            
            elif isinstance(input_data, bool):
                result = input_data
            elif input_data is None:
                # No input - default to NOT allowing entry (safer)
                result = False
                self.log_warning("No input data for entry condition - defaulting to NOT MET", context)
            else:
                # Try to interpret as boolean
                result = bool(input_data)
            
            self.log_success(f"Entry condition: {'MET' if result else 'NOT MET'}", context)
            
            return self.create_result(True, {
                "result": result,  # For gate node compatibility
                "conditionMet": result,  # Alias
                "should_enter": result,  # Explicit entry flag
                "entry_allowed": result,
                "condition_type": condition_type
            })
            
        except Exception as e:
            error_msg = f"Error checking entry condition: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)


class ExitConditionExecutor(NodeExecutor):
    """Executor for exit-condition node - checks if exit conditions are met"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Check exit conditions"""
        
        # Get input conditions
        input_data = self.get_input(context, "default")
        
        # Also check for additional inputs
        if input_data is None and context.inputs:
            input_data = next(iter(context.inputs.values()), None)
        
        condition_type = self.get_config(context, "conditionType", "any")
        
        self.log_info(f"Checking exit conditions, type={condition_type}", context)
        
        try:
            result = False
            
            # Evaluate conditions
            if isinstance(input_data, dict):
                # Check common result keys
                if "result" in input_data:
                    result = bool(input_data["result"])
                elif "conditionMet" in input_data:
                    result = bool(input_data["conditionMet"])
                elif "should_exit" in input_data:
                    result = bool(input_data["should_exit"])
                elif "exit_triggered" in input_data:
                    result = bool(input_data["exit_triggered"])
                elif "triggered" in input_data:
                    result = bool(input_data["triggered"])
                else:
                    # Multiple conditions - check for boolean values
                    bool_results = []
                    for k, v in input_data.items():
                        if isinstance(v, bool):
                            bool_results.append(v)
                        elif isinstance(v, dict):
                            # Nested result
                            if "result" in v:
                                bool_results.append(bool(v["result"]))
                            elif "conditionMet" in v:
                                bool_results.append(bool(v["conditionMet"]))
                            elif "triggered" in v:
                                bool_results.append(bool(v["triggered"]))
                    
                    if bool_results:
                        if condition_type == "all":
                            result = all(bool_results)
                        else:  # any
                            result = any(bool_results)
                    else:
                        # Check for SELL signal
                        result = input_data.get("signal") == "SELL"
            
            elif isinstance(input_data, bool):
                result = input_data
            elif input_data is None:
                # No input - default to NOT triggering exit (safer)
                result = False
                self.log_info("No input data for exit condition - defaulting to NOT MET", context)
            else:
                # Try to interpret as boolean
                result = bool(input_data)
            
            self.log_success(f"Exit condition: {'MET' if result else 'NOT MET'}", context)
            
            return self.create_result(True, {
                "result": result,  # For gate node compatibility
                "conditionMet": result,  # Alias
                "should_exit": result,  # Explicit exit flag
                "exit_triggered": result,
                "condition_type": condition_type
            })
            
        except Exception as e:
            error_msg = f"Error checking exit condition: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)


class StopTakeProfitExecutor(NodeExecutor):
    """Executor for stop-take-profit node - manages stop loss and take profit levels"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Calculate and manage stop loss/take profit levels"""
        
        symbol = self.get_config(context, "symbol")
        entry_price = self.get_config(context, "entryPrice")
        stop_loss_pct = self.get_config(context, "stopLossPercent", 5.0)
        take_profit_pct = self.get_config(context, "takeProfitPercent", 10.0)
        
        # Get entry price from input if not in config
        if entry_price is None:
            input_data = self.get_input(context, "default")
            if isinstance(input_data, dict):
                entry_price = input_data.get("execution_price") or input_data.get("price")
        
        if entry_price is None:
            return self.create_result(False, None, "Entry price required")
        
        entry_price = float(entry_price)
        
        self.log_info(
            f"Calculating stop/take-profit for {symbol}, entry=${entry_price:.2f}",
            context
        )
        
        try:
            # Calculate levels
            stop_loss_price = entry_price * (1 - stop_loss_pct / 100)
            take_profit_price = entry_price * (1 + take_profit_pct / 100)
            
            result = {
                "symbol": symbol,
                "entry_price": entry_price,
                "stop_loss_price": stop_loss_price,
                "take_profit_price": take_profit_price,
                "stop_loss_percent": stop_loss_pct,
                "take_profit_percent": take_profit_pct,
                "risk_reward_ratio": take_profit_pct / stop_loss_pct if stop_loss_pct > 0 else 0
            }
            
            self.log_success(
                f"Stop/Take-profit: SL=${stop_loss_price:.2f}, TP=${take_profit_price:.2f}",
                context
            )
            
            return self.create_result(True, result)
            
        except Exception as e:
            error_msg = f"Error calculating stop/take-profit: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)


class TrailingStopExecutor(NodeExecutor):
    """Executor for trailing-stop node - manages dynamic trailing stop loss"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Calculate trailing stop level"""
        
        symbol = self.get_config(context, "symbol")
        current_price = self.get_config(context, "currentPrice")
        highest_price = self.get_config(context, "highestPrice")
        trailing_pct = self.get_config(context, "trailingPercent", 5.0)
        
        # Get prices from input
        input_data = self.get_input(context, "default")
        if isinstance(input_data, dict):
            if current_price is None:
                current_price = input_data.get("price") or input_data.get("current_price")
            if highest_price is None:
                highest_price = input_data.get("highest_price") or current_price
        
        if current_price is None:
            return self.create_result(False, None, "Current price required")
        
        current_price = float(current_price)
        highest_price = float(highest_price) if highest_price else current_price
        
        # Update highest price if current is higher
        if current_price > highest_price:
            highest_price = current_price
        
        self.log_info(
            f"Calculating trailing stop for {symbol}, current=${current_price:.2f}, high=${highest_price:.2f}",
            context
        )
        
        try:
            # Calculate trailing stop below highest price
            trailing_stop_price = highest_price * (1 - trailing_pct / 100)
            
            # Check if stop is triggered
            triggered = current_price <= trailing_stop_price
            
            result = {
                "symbol": symbol,
                "current_price": current_price,
                "highest_price": highest_price,
                "trailing_stop_price": trailing_stop_price,
                "trailing_percent": trailing_pct,
                "triggered": triggered,
                "distance_to_stop": ((current_price - trailing_stop_price) / current_price * 100) if current_price > 0 else 0
            }
            
            if triggered:
                self.log_warning(
                    f"Trailing stop TRIGGERED: {symbol} @ ${current_price:.2f} <= ${trailing_stop_price:.2f}",
                    context
                )
            else:
                self.log_success(
                    f"Trailing stop active: ${trailing_stop_price:.2f} ({trailing_pct}% below high)",
                    context
                )
            
            return self.create_result(True, result)
            
        except Exception as e:
            error_msg = f"Error calculating trailing stop: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)






