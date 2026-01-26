"""
Node executors for trading action nodes
"""

from typing import Any, Dict, Optional
import logging
from datetime import datetime
import uuid

from .base import NodeExecutor
from app.models.execution import ExecutionResult, NodeExecutionContext
from app.services.market_data import market_data_service
from app.services.brokers.base import BrokerService, OrderSide, OrderType

logger = logging.getLogger(__name__)


class BuyOrderExecutor(NodeExecutor):
    """Executor for buy-order node - places buy orders via broker"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Execute buy order via broker service"""
        
        # Validate required config
        error = self.validate_required_config(context, "symbol", "quantity")
        if error:
            return self.create_result(False, None, error)
        
        symbol = self.get_config(context, "symbol")
        quantity = int(self.get_config(context, "quantity"))
        order_type_str = self.get_config(context, "orderType", "market")
        limit_price = self.get_config(context, "limitPrice")
        stop_price = self.get_config(context, "stopPrice")
        portfolio_id = self.get_config(context, "portfolioId", context.portfolioId)
        
        # Get broker service from context
        broker: Optional[BrokerService] = getattr(context, "broker", None)
        if not broker:
            return self.create_result(
                False,
                None,
                "Broker service not available in context"
            )
        
        self.log_info(
            f"Placing BUY order: {quantity} shares of {symbol} @ {order_type_str}",
            context
        )
        
        try:
            # Map order type string to enum
            order_type_map = {
                "market": OrderType.MARKET,
                "limit": OrderType.LIMIT,
                "stop": OrderType.STOP,
                "stop_limit": OrderType.STOP_LIMIT
            }
            order_type = order_type_map.get(order_type_str.lower(), OrderType.MARKET)
            
            # Place order via broker
            order_data = await broker.place_order(
                symbol=symbol,
                side=OrderSide.BUY,
                quantity=quantity,
                order_type=order_type,
                limit_price=float(limit_price) if limit_price else None,
                stop_price=float(stop_price) if stop_price else None
            )
            
            if order_data.get("status") == "filled":
                self.log_success(
                    f"BUY order filled: {quantity} {symbol} @ ${order_data.get('execution_price', 0):.2f}",
                    context
                )
            else:
                self.log_info(
                    f"BUY order placed: {order_data.get('status')}",
                    context
                )
            
            return self.create_result(True, order_data)
            
        except Exception as e:
            error_msg = f"Error placing buy order: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)


class SellOrderExecutor(NodeExecutor):
    """Executor for sell-order node - places sell orders via broker"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Execute sell order via broker service"""
        
        # Validate required config
        error = self.validate_required_config(context, "symbol", "quantity")
        if error:
            return self.create_result(False, None, error)
        
        symbol = self.get_config(context, "symbol")
        quantity = int(self.get_config(context, "quantity"))
        order_type_str = self.get_config(context, "orderType", "market")
        limit_price = self.get_config(context, "limitPrice")
        stop_price = self.get_config(context, "stopPrice")
        portfolio_id = self.get_config(context, "portfolioId", context.portfolioId)
        
        # Get broker service from context
        broker: Optional[BrokerService] = getattr(context, "broker", None)
        if not broker:
            return self.create_result(
                False,
                None,
                "Broker service not available in context"
            )
        
        self.log_info(
            f"Placing SELL order: {quantity} shares of {symbol} @ {order_type_str}",
            context
        )
        
        try:
            # Map order type string to enum
            order_type_map = {
                "market": OrderType.MARKET,
                "limit": OrderType.LIMIT,
                "stop": OrderType.STOP,
                "stop_limit": OrderType.STOP_LIMIT
            }
            order_type = order_type_map.get(order_type_str.lower(), OrderType.MARKET)
            
            # Place order via broker
            order_data = await broker.place_order(
                symbol=symbol,
                side=OrderSide.SELL,
                quantity=quantity,
                order_type=order_type,
                limit_price=float(limit_price) if limit_price else None,
                stop_price=float(stop_price) if stop_price else None
            )
            
            if order_data.get("status") == "filled":
                self.log_success(
                    f"SELL order filled: {quantity} {symbol} @ ${order_data.get('execution_price', 0):.2f}",
                    context
                )
            else:
                self.log_info(
                    f"SELL order placed: {order_data.get('status')}",
                    context
                )
            
            return self.create_result(True, order_data)
            
        except Exception as e:
            error_msg = f"Error placing sell order: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)


class StopLossExecutor(NodeExecutor):
    """Executor for stop-loss node - manages stop loss orders"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Execute stop loss check and order via broker"""
        
        # Validate required config
        error = self.validate_required_config(context, "symbol")
        if error:
            return self.create_result(False, None, error)
        
        symbol = self.get_config(context, "symbol")
        stop_type = self.get_config(context, "stopType", "percentage")
        stop_percentage = self.get_config(context, "stopPercentage", 5.0)
        stop_price = self.get_config(context, "stopPrice")
        quantity = self.get_config(context, "quantity", "all")
        
        # Get broker service from context
        broker: Optional[BrokerService] = getattr(context, "broker", None)
        
        self.log_info(
            f"Checking stop loss for {symbol}: {stop_type}",
            context
        )
        
        try:
            # Get current market price
            if broker:
                quote_data = await broker.get_quote(symbol)
            else:
                quote_data = market_data_service.get_quote(symbol)
            
            if not quote_data:
                return self.create_result(
                    False,
                    None,
                    f"Failed to fetch price for {symbol}"
                )
            
            current_price = float(quote_data.get("price", 0))
            
            # Get entry price from input or use current price
            entry_price = self.get_input(context, "entry_price", current_price)
            if isinstance(entry_price, dict):
                entry_price = entry_price.get("execution_price", current_price)
            entry_price = float(entry_price)
            
            # Calculate stop loss trigger price
            trigger_price = None
            
            if stop_type == "percentage":
                # Calculate stop price as percentage below entry
                trigger_price = entry_price * (1 - stop_percentage / 100)
            
            elif stop_type == "fixed":
                if stop_price is None:
                    return self.create_result(False, None, "Stop price required for fixed stop loss")
                trigger_price = float(stop_price)
            
            elif stop_type == "trailing":
                # Trailing stop tracks highest price and sets stop below it
                highest_price = self.get_input(context, "highest_price", entry_price)
                if isinstance(highest_price, dict):
                    highest_price = highest_price.get("price", entry_price)
                highest_price = float(max(highest_price, current_price))
                
                trigger_price = highest_price * (1 - stop_percentage / 100)
            
            if trigger_price is None:
                return self.create_result(False, None, "Could not calculate stop loss trigger price")
            
            # Check if stop loss is triggered
            triggered = current_price <= trigger_price
            
            result_data = {
                "symbol": symbol,
                "current_price": current_price,
                "entry_price": entry_price,
                "trigger_price": trigger_price,
                "stop_type": stop_type,
                "triggered": triggered,
                "loss_percentage": ((current_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
            }
            
            if triggered:
                self.log_warning(
                    f"STOP LOSS TRIGGERED: {symbol} @ ${current_price:.2f} <= ${trigger_price:.2f} (loss: {result_data['loss_percentage']:.2f}%)",
                    context
                )
                
                # Place stop loss order via broker if available
                if broker:
                    try:
                        # Get position quantity if quantity is "all"
                        if quantity == "all":
                            positions = await broker.get_positions(symbol=symbol)
                            if positions and positions[0].get("quantity", 0) > 0:
                                quantity = positions[0]["quantity"]
                            else:
                                quantity = 1  # Default to 1 if no position found
                        else:
                            quantity = int(quantity)
                        
                        # Place market sell order
                        order_data = await broker.place_order(
                            symbol=symbol,
                            side=OrderSide.SELL,
                            quantity=quantity,
                            order_type=OrderType.MARKET
                        )
                        result_data["order"] = order_data
                        self.log_success(f"Stop loss order placed: {order_data.get('order_id')}", context)
                    except Exception as e:
                        self.log_error(f"Failed to place stop loss order via broker: {str(e)}", context)
                        # Fallback to creating order record without broker
                        order_id = f"stop_order_{uuid.uuid4().hex[:16]}"
                        result_data["order"] = {
                            "order_id": order_id,
                            "symbol": symbol,
                            "side": "SELL",
                            "quantity": quantity,
                            "order_type": "market",
                            "status": "pending",
                            "execution_price": current_price,
                            "timestamp": datetime.now().isoformat(),
                            "reason": "stop_loss_triggered",
                            "error": str(e)
                        }
                else:
                    # No broker, create order record
                    order_id = f"stop_order_{uuid.uuid4().hex[:16]}"
                    result_data["order"] = {
                        "order_id": order_id,
                        "symbol": symbol,
                        "side": "SELL",
                        "quantity": quantity if quantity != "all" else 1,
                        "order_type": "market",
                        "status": "pending",
                        "execution_price": current_price,
                        "timestamp": datetime.now().isoformat(),
                        "reason": "stop_loss_triggered"
                    }
            else:
                self.log_info(
                    f"Stop loss not triggered: {symbol} @ ${current_price:.2f} > ${trigger_price:.2f}",
                    context
                )
            
            return self.create_result(True, result_data)
            
        except Exception as e:
            error_msg = f"Error executing stop loss: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)


class OrderManagementExecutor(NodeExecutor):
    """Executor for order-management node - manages and modifies orders"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Manage existing orders via broker"""
        
        action = self.get_config(context, "action", "check_status")
        order_id = self.get_config(context, "orderId")
        
        # Get broker service from context
        broker: Optional[BrokerService] = getattr(context, "broker", None)
        if not broker:
            return self.create_result(
                False,
                None,
                "Broker service not available in context"
            )
        
        self.log_info(f"Order management action: {action}", context)
        
        try:
            # Get order from input or order_id
            order_input = self.get_input(context, "default")
            
            if not order_id and isinstance(order_input, dict):
                order_id = order_input.get("order_id")
            
            if not order_id:
                return self.create_result(False, None, "Order ID required")
            
            # Perform action
            if action == "cancel":
                cancelled = await broker.cancel_order(order_id)
                if cancelled:
                    self.log_success(f"Order cancelled: {order_id}", context)
                    return self.create_result(True, {"order_id": order_id, "status": "cancelled"})
                else:
                    return self.create_result(False, None, f"Failed to cancel order: {order_id}")
            
            elif action == "check_status":
                orders = await broker.get_orders()
                order = next((o for o in orders if o.get("order_id") == order_id), None)
                if order:
                    self.log_info(f"Order status: {order.get('status')}", context)
                    return self.create_result(True, order)
                else:
                    return self.create_result(False, None, f"Order not found: {order_id}")
            
            elif action == "modify":
                # Order modification would require broker support
                # For now, return error
                return self.create_result(
                    False,
                    None,
                    "Order modification not yet implemented"
                )
            
            else:
                return self.create_result(False, None, f"Unsupported action: {action}")
            
        except Exception as e:
            error_msg = f"Error managing order: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)

