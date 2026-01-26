"""
Node executors for risk management nodes
"""

from typing import Any, Dict, Optional
import logging

from .base import NodeExecutor
from app.models.execution import ExecutionResult, NodeExecutionContext

logger = logging.getLogger(__name__)


class MaxLossDrawdownExecutor(NodeExecutor):
    """Executor for max-loss-drawdown node - enforces maximum loss/drawdown limits"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Check and enforce maximum loss/drawdown limits"""
        
        max_loss_pct = self.get_config(context, "maxLossPercent")
        max_drawdown_pct = self.get_config(context, "maxDrawdownPercent")
        portfolio_id = self.get_config(context, "portfolioId", context.portfolioId)
        
        # Get portfolio data from input
        portfolio_data = self.get_input(context, "default")
        
        self.log_info(
            f"Checking max loss/drawdown limits for portfolio {portfolio_id}",
            context
        )
        
        try:
            # Extract portfolio metrics
            if isinstance(portfolio_data, dict):
                current_value = portfolio_data.get("current_value") or portfolio_data.get("value", 0)
                initial_value = portfolio_data.get("initial_value") or portfolio_data.get("capital", 0)
                peak_value = portfolio_data.get("peak_value") or current_value
                total_pnl = portfolio_data.get("total_pnl") or 0
            else:
                # Placeholder values
                current_value = 10000
                initial_value = 10000
                peak_value = 10000
                total_pnl = 0
            
            violations = []
            should_stop = False
            
            # Check max loss
            if max_loss_pct is not None:
                max_loss_pct = float(max_loss_pct)
                loss_pct = (total_pnl / initial_value * 100) if initial_value > 0 else 0
                if loss_pct < -max_loss_pct:
                    violations.append(f"Max loss exceeded: {loss_pct:.2f}% > {max_loss_pct}%")
                    should_stop = True
            
            # Check max drawdown
            if max_drawdown_pct is not None:
                max_drawdown_pct = float(max_drawdown_pct)
                drawdown_pct = ((peak_value - current_value) / peak_value * 100) if peak_value > 0 else 0
                if drawdown_pct > max_drawdown_pct:
                    violations.append(f"Max drawdown exceeded: {drawdown_pct:.2f}% > {max_drawdown_pct}%")
                    should_stop = True
            
            result = {
                "portfolio_id": portfolio_id,
                "current_value": current_value,
                "initial_value": initial_value,
                "peak_value": peak_value,
                "total_pnl": total_pnl,
                "loss_percent": (total_pnl / initial_value * 100) if initial_value > 0 else 0,
                "drawdown_percent": ((peak_value - current_value) / peak_value * 100) if peak_value > 0 else 0,
                "violations": violations,
                "should_stop": should_stop
            }
            
            if should_stop:
                self.log_warning(
                    f"Risk limits EXCEEDED: {', '.join(violations)}",
                    context
                )
            else:
                self.log_success("Risk limits within bounds", context)
            
            return self.create_result(True, result)
            
        except Exception as e:
            error_msg = f"Error checking risk limits: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)


class PositionSizingExecutor(NodeExecutor):
    """Executor for position-sizing node - calculates position sizes"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Calculate position size based on risk parameters"""
        
        sizing_method = self.get_config(context, "sizingMethod", "fixed")
        risk_per_trade = self.get_config(context, "riskPerTrade", 2.0)  # percentage
        fixed_quantity = self.get_config(context, "fixedQuantity")
        fixed_amount = self.get_config(context, "fixedAmount")
        symbol = self.get_config(context, "symbol")
        entry_price = self.get_config(context, "entryPrice")
        stop_loss_price = self.get_config(context, "stopLossPrice")
        
        # Get capital/price from input
        input_data = self.get_input(context, "default")
        if isinstance(input_data, dict):
            if entry_price is None:
                entry_price = input_data.get("price") or input_data.get("entry_price")
            if stop_loss_price is None:
                stop_loss_price = input_data.get("stop_loss_price")
            capital = input_data.get("capital") or input_data.get("available_capital", 10000)
        else:
            capital = 10000  # Default
        
        if entry_price is None:
            return self.create_result(False, None, "Entry price required")
        
        entry_price = float(entry_price)
        capital = float(capital)
        
        self.log_info(
            f"Calculating position size for {symbol}, method={sizing_method}",
            context
        )
        
        try:
            quantity = 0
            position_value = 0.0
            
            if sizing_method == "fixed_quantity":
                if fixed_quantity:
                    quantity = int(fixed_quantity)
                    position_value = quantity * entry_price
                else:
                    return self.create_result(False, None, "Fixed quantity required")
            
            elif sizing_method == "fixed_amount":
                if fixed_amount:
                    position_value = float(fixed_amount)
                    quantity = int(position_value / entry_price)
                else:
                    return self.create_result(False, None, "Fixed amount required")
            
            elif sizing_method == "risk_percentage":
                if stop_loss_price:
                    stop_loss_price = float(stop_loss_price)
                    risk_per_share = abs(entry_price - stop_loss_price)
                    if risk_per_share > 0:
                        risk_amount = capital * (risk_per_trade / 100)
                        quantity = int(risk_amount / risk_per_share)
                        position_value = quantity * entry_price
                    else:
                        return self.create_result(False, None, "Invalid stop loss price")
                else:
                    return self.create_result(False, None, "Stop loss price required for risk-based sizing")
            
            elif sizing_method == "percentage_of_capital":
                position_value = capital * (risk_per_trade / 100)
                quantity = int(position_value / entry_price)
            
            else:
                return self.create_result(False, None, f"Unsupported sizing method: {sizing_method}")
            
            result = {
                "symbol": symbol,
                "quantity": quantity,
                "entry_price": entry_price,
                "position_value": position_value,
                "sizing_method": sizing_method,
                "capital_used": position_value,
                "capital_remaining": capital - position_value,
                "risk_per_trade": risk_per_trade if sizing_method in ["risk_percentage", "percentage_of_capital"] else None
            }
            
            self.log_success(
                f"Position size calculated: {quantity} shares (${position_value:.2f})",
                context
            )
            
            return self.create_result(True, result)
            
        except Exception as e:
            error_msg = f"Error calculating position size: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)


class LeverageControlExecutor(NodeExecutor):
    """Executor for leverage-control node - enforces maximum leverage limits"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Check and enforce leverage limits"""
        
        max_leverage = self.get_config(context, "maxLeverage", 1.0)
        portfolio_id = self.get_config(context, "portfolioId", context.portfolioId)
        
        # Get portfolio/position data
        position_data = self.get_input(context, "default")
        
        self.log_info(
            f"Checking leverage limits, max={max_leverage}x for portfolio {portfolio_id}",
            context
        )
        
        try:
            # Calculate current leverage
            if isinstance(position_data, dict):
                total_position_value = position_data.get("total_position_value", 0)
                capital = position_data.get("capital") or position_data.get("available_capital", 0)
            else:
                total_position_value = 0
                capital = 10000
            
            current_leverage = (total_position_value / capital) if capital > 0 else 0
            
            violation = current_leverage > max_leverage
            allowed_position_value = capital * max_leverage if not violation else None
            
            result = {
                "portfolio_id": portfolio_id,
                "current_leverage": current_leverage,
                "max_leverage": max_leverage,
                "total_position_value": total_position_value,
                "capital": capital,
                "violation": violation,
                "allowed_position_value": allowed_position_value
            }
            
            if violation:
                self.log_warning(
                    f"Leverage limit EXCEEDED: {current_leverage:.2f}x > {max_leverage}x",
                    context
                )
            else:
                self.log_success(f"Leverage within limits: {current_leverage:.2f}x", context)
            
            return self.create_result(True, result)
            
        except Exception as e:
            error_msg = f"Error checking leverage: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)


class DailyLimitExecutor(NodeExecutor):
    """Executor for daily-limits node - enforces daily trading limits"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Check and enforce daily profit/loss limits"""
        
        max_daily_loss = self.get_config(context, "maxDailyLoss")
        max_daily_profit = self.get_config(context, "maxDailyProfit")
        portfolio_id = self.get_config(context, "portfolioId", context.portfolioId)
        
        # Get daily PnL from input
        daily_data = self.get_input(context, "default")
        
        self.log_info(
            f"Checking daily limits for portfolio {portfolio_id}",
            context
        )
        
        try:
            # Extract daily metrics
            if isinstance(daily_data, dict):
                daily_pnl = daily_data.get("daily_pnl") or daily_data.get("pnl", 0)
                daily_trades = daily_data.get("daily_trades", 0)
            else:
                daily_pnl = 0
                daily_trades = 0
            
            violations = []
            should_stop = False
            
            # Check max daily loss
            if max_daily_loss is not None:
                max_daily_loss = float(max_daily_loss)
                if daily_pnl < -max_daily_loss:
                    violations.append(f"Max daily loss exceeded: ${abs(daily_pnl):.2f} > ${max_daily_loss:.2f}")
                    should_stop = True
            
            # Check max daily profit
            if max_daily_profit is not None:
                max_daily_profit = float(max_daily_profit)
                if daily_pnl > max_daily_profit:
                    violations.append(f"Max daily profit exceeded: ${daily_pnl:.2f} > ${max_daily_profit:.2f}")
                    should_stop = True
            
            result = {
                "portfolio_id": portfolio_id,
                "daily_pnl": daily_pnl,
                "daily_trades": daily_trades,
                "max_daily_loss": max_daily_loss,
                "max_daily_profit": max_daily_profit,
                "violations": violations,
                "should_stop": should_stop
            }
            
            if should_stop:
                self.log_warning(
                    f"Daily limits EXCEEDED: {', '.join(violations)}",
                    context
                )
            else:
                self.log_success(f"Daily limits within bounds: PnL=${daily_pnl:.2f}", context)
            
            return self.create_result(True, result)
            
        except Exception as e:
            error_msg = f"Error checking daily limits: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)






