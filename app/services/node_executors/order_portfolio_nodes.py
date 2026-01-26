"""
Node executors for order and portfolio management nodes
"""

from typing import Any, Dict, List, Optional
import logging

from .base import NodeExecutor
from app.models.execution import ExecutionResult, NodeExecutionContext

logger = logging.getLogger(__name__)


class PositionManagementExecutor(NodeExecutor):
    """Executor for position-management node - tracks and manages positions"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Track and manage positions"""
        
        action = self.get_config(context, "action", "get")
        symbol = self.get_config(context, "symbol")
        portfolio_id = self.get_config(context, "portfolioId", context.portfolioId)
        
        self.log_info(f"Position management: {action} for {symbol}", context)
        
        try:
            # Get position data from input (from broker/previous nodes)
            position_data = self.get_input(context, "default")
            
            if action == "get":
                # Get current position
                if isinstance(position_data, dict) and "quantity" in position_data:
                    position = position_data
                else:
                    # Placeholder - would fetch from broker/store
                    position = {
                        "symbol": symbol,
                        "quantity": 0,
                        "average_price": 0.0,
                        "current_price": 0.0,
                        "unrealized_pnl": 0.0,
                        "realized_pnl": 0.0
                    }
                
                self.log_success(f"Position retrieved: {position.get('quantity', 0)} shares", context)
                return self.create_result(True, position)
            
            elif action == "update":
                # Update position (from order execution)
                if not isinstance(position_data, dict):
                    return self.create_result(False, None, "Position data required for update")
                
                self.log_success("Position updated", context)
                return self.create_result(True, position_data)
            
            elif action == "close":
                # Close position
                if isinstance(position_data, dict):
                    quantity = position_data.get("quantity", 0)
                    if quantity > 0:
                        self.log_info(f"Closing position: {quantity} shares of {symbol}", context)
                        # Would trigger sell order
                        return self.create_result(True, {
                            "action": "close",
                            "symbol": symbol,
                            "quantity": quantity,
                            "status": "pending"
                        })
                    else:
                        return self.create_result(False, None, "No position to close")
                else:
                    return self.create_result(False, None, "Position data required")
            
            else:
                return self.create_result(False, None, f"Unsupported action: {action}")
            
        except Exception as e:
            error_msg = f"Error in position management: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)


class PortfolioAllocationExecutor(NodeExecutor):
    """Executor for portfolio-allocation node - manages portfolio allocation"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Calculate and manage portfolio allocation"""
        
        allocation_type = self.get_config(context, "allocationType", "percentage")
        total_capital = self.get_config(context, "totalCapital")
        symbols = self.get_config(context, "symbols", [])
        allocations = self.get_config(context, "allocations", {})
        
        # Get capital from input if not in config
        if total_capital is None:
            input_data = self.get_input(context, "default")
            if isinstance(input_data, dict):
                total_capital = input_data.get("capital") or input_data.get("total_capital")
        
        if total_capital is None:
            return self.create_result(False, None, "Total capital required")
        
        total_capital = float(total_capital)
        
        self.log_info(
            f"Calculating portfolio allocation, type={allocation_type}, capital=${total_capital:.2f}",
            context
        )
        
        try:
            allocation_results = {}
            
            if allocation_type == "percentage":
                # Percentage-based allocation
                if isinstance(allocations, dict):
                    for symbol, pct in allocations.items():
                        allocation_amount = total_capital * (float(pct) / 100)
                        allocation_results[symbol] = {
                            "percentage": float(pct),
                            "amount": allocation_amount,
                            "capital": total_capital
                        }
                elif symbols:
                    # Equal allocation
                    pct_per_symbol = 100.0 / len(symbols)
                    for symbol in symbols:
                        allocation_amount = total_capital * (pct_per_symbol / 100)
                        allocation_results[symbol] = {
                            "percentage": pct_per_symbol,
                            "amount": allocation_amount,
                            "capital": total_capital
                        }
            
            elif allocation_type == "fixed":
                # Fixed amount per symbol
                fixed_amount = self.get_config(context, "fixedAmount")
                if fixed_amount:
                    fixed_amount = float(fixed_amount)
                    for symbol in symbols:
                        allocation_results[symbol] = {
                            "amount": fixed_amount,
                            "capital": total_capital
                        }
            
            elif allocation_type == "equal":
                # Equal dollar amount
                if symbols:
                    amount_per_symbol = total_capital / len(symbols)
                    for symbol in symbols:
                        allocation_results[symbol] = {
                            "amount": amount_per_symbol,
                            "percentage": (amount_per_symbol / total_capital * 100),
                            "capital": total_capital
                        }
            
            total_allocated = sum([r["amount"] for r in allocation_results.values()])
            
            result = {
                "allocation_type": allocation_type,
                "total_capital": total_capital,
                "total_allocated": total_allocated,
                "remaining": total_capital - total_allocated,
                "allocations": allocation_results
            }
            
            self.log_success(
                f"Portfolio allocation calculated: ${total_allocated:.2f} allocated across {len(allocation_results)} symbols",
                context
            )
            
            return self.create_result(True, result)
            
        except Exception as e:
            error_msg = f"Error calculating portfolio allocation: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)






