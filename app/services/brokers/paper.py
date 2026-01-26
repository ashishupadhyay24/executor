"""
Paper trading broker service - simulates trading without real money
"""

from typing import Dict, List, Optional, Any
import logging
import uuid
from datetime import datetime

from .base import BrokerService, OrderSide, OrderType, OrderStatus
from app.services.market_data import market_data_service

logger = logging.getLogger(__name__)


class PaperBrokerService(BrokerService):
    """
    Paper trading broker - simulates trading with virtual money
    
    Tracks:
    - Cash balance
    - Positions
    - Orders
    - PnL (realized and unrealized)
    """
    
    def __init__(self, user_id: str, portfolio_id: str, initial_capital: float = 100000.0):
        super().__init__(user_id, portfolio_id)
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: Dict[str, Dict[str, Any]] = {}  # symbol -> position data
        self.orders: Dict[str, Dict[str, Any]] = {}  # order_id -> order data
        self.trades: List[Dict[str, Any]] = []  # Trade history
        
        logger.info(f"Initialized paper broker for {user_id}/{portfolio_id} with ${initial_capital:.2f}")
    
    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: int,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Place an order (paper trading simulation)"""
        
        logger.info(f"Placing {side.value} order: {quantity} {symbol} @ {order_type.value}")
        
        # Get current market price
        quote = await self.get_quote(symbol)
        if not quote:
            raise ValueError(f"Failed to get quote for {symbol}")
        
        current_price = float(quote.get("price", 0))
        
        # Generate order ID
        order_id = f"paper_order_{uuid.uuid4().hex[:16]}"
        
        # Determine execution price and status based on order type
        execution_price = current_price
        order_status = OrderStatus.PENDING
        
        if order_type == OrderType.MARKET:
            execution_price = current_price
            order_status = OrderStatus.FILLED
        
        elif order_type == OrderType.LIMIT:
            if limit_price is None:
                raise ValueError("Limit price required for LIMIT order")
            
            if side == OrderSide.BUY:
                # Buy limit: execute if current price <= limit price
                if current_price <= limit_price:
                    execution_price = min(current_price, limit_price)
                    order_status = OrderStatus.FILLED
            else:  # SELL
                # Sell limit: execute if current_price >= limit_price
                if current_price >= limit_price:
                    execution_price = max(current_price, limit_price)
                    order_status = OrderStatus.FILLED
        
        elif order_type == OrderType.STOP:
            if stop_price is None:
                raise ValueError("Stop price required for STOP order")
            
            if side == OrderSide.BUY:
                # Buy stop: execute if current price >= stop price
                if current_price >= stop_price:
                    execution_price = max(current_price, stop_price)
                    order_status = OrderStatus.FILLED
            else:  # SELL
                # Sell stop: execute if current price <= stop price
                if current_price <= stop_price:
                    execution_price = min(current_price, stop_price)
                    order_status = OrderStatus.FILLED
        
        elif order_type == OrderType.STOP_LIMIT:
            if limit_price is None or stop_price is None:
                raise ValueError("Both limit and stop prices required for STOP_LIMIT order")
            
            # For stop-limit, check stop first, then limit
            if side == OrderSide.BUY:
                if current_price >= stop_price:
                    execution_price = min(current_price, limit_price)
                    order_status = OrderStatus.FILLED if current_price <= limit_price else OrderStatus.PENDING
            else:  # SELL
                if current_price <= stop_price:
                    execution_price = max(current_price, limit_price)
                    order_status = OrderStatus.FILLED if current_price >= limit_price else OrderStatus.PENDING
        
        # Calculate order value
        order_value = execution_price * quantity
        
        # Check if we have enough cash for buy orders
        if side == OrderSide.BUY and order_status == OrderStatus.FILLED:
            if order_value > self.cash:
                order_status = OrderStatus.REJECTED
                logger.warning(f"Insufficient cash: ${order_value:.2f} > ${self.cash:.2f}")
        
        # Check if we have enough shares for sell orders
        if side == OrderSide.SELL and order_status == OrderStatus.FILLED:
            current_position = self.positions.get(symbol, {})
            current_quantity = current_position.get("quantity", 0)
            if quantity > current_quantity:
                order_status = OrderStatus.REJECTED
                logger.warning(f"Insufficient shares: {quantity} > {current_quantity}")
        
        # Create order record
        order = {
            "order_id": order_id,
            "symbol": symbol,
            "side": side.value,
            "quantity": quantity,
            "order_type": order_type.value,
            "status": order_status.value,
            "limit_price": limit_price,
            "stop_price": stop_price,
            "execution_price": execution_price if order_status == OrderStatus.FILLED else None,
            "order_value": order_value if order_status == OrderStatus.FILLED else None,
            "timestamp": datetime.now().isoformat(),
            "user_id": self.user_id,
            "portfolio_id": self.portfolio_id
        }
        
        self.orders[order_id] = order
        
        # If order is filled, update positions and cash
        if order_status == OrderStatus.FILLED:
            await self._execute_order(order)
        
        logger.info(f"Order placed: {order_id} - {order_status.value}")
        
        return order
    
    async def _execute_order(self, order: Dict[str, Any]):
        """Execute a filled order - update positions and cash"""
        
        symbol = order["symbol"]
        side = order["side"]
        quantity = order["quantity"]
        execution_price = order["execution_price"]
        order_value = order["order_value"]
        
        # Update position
        if symbol not in self.positions:
            self.positions[symbol] = {
                "symbol": symbol,
                "quantity": 0,
                "average_price": 0.0,
                "total_cost": 0.0
            }
        
        position = self.positions[symbol]
        
        if side == "BUY":
            # Buy: add to position
            old_quantity = position["quantity"]
            old_cost = position["total_cost"]
            
            new_quantity = old_quantity + quantity
            new_cost = old_cost + order_value
            new_avg_price = new_cost / new_quantity if new_quantity > 0 else 0
            
            position["quantity"] = new_quantity
            position["average_price"] = new_avg_price
            position["total_cost"] = new_cost
            
            # Deduct cash
            self.cash -= order_value
            
            logger.info(f"Bought {quantity} {symbol} @ ${execution_price:.2f}, new position: {new_quantity} @ ${new_avg_price:.2f} avg")
        
        else:  # SELL
            # Sell: reduce position
            old_quantity = position["quantity"]
            old_avg_price = position["average_price"]
            
            if quantity > old_quantity:
                quantity = old_quantity  # Can't sell more than we have
            
            new_quantity = old_quantity - quantity
            realized_pnl = (execution_price - old_avg_price) * quantity
            
            position["quantity"] = new_quantity
            if new_quantity == 0:
                position["average_price"] = 0.0
                position["total_cost"] = 0.0
            else:
                position["total_cost"] = position["average_price"] * new_quantity
            
            # Add cash
            self.cash += order_value
            
            logger.info(f"Sold {quantity} {symbol} @ ${execution_price:.2f}, realized PnL: ${realized_pnl:.2f}")
        
        # Record trade
        trade = {
            "trade_id": f"trade_{uuid.uuid4().hex[:16]}",
            "order_id": order["order_id"],
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": execution_price,
            "value": order_value,
            "timestamp": order["timestamp"],
            "realized_pnl": (execution_price - position.get("average_price", 0)) * quantity if side == "SELL" else 0
        }
        self.trades.append(trade)
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order"""
        
        if order_id not in self.orders:
            logger.warning(f"Order not found: {order_id}")
            return False
        
        order = self.orders[order_id]
        if order["status"] in [OrderStatus.FILLED.value, OrderStatus.CANCELLED.value]:
            logger.warning(f"Cannot cancel order {order_id}: status is {order['status']}")
            return False
        
        order["status"] = OrderStatus.CANCELLED.value
        order["cancelled_at"] = datetime.now().isoformat()
        
        logger.info(f"Order cancelled: {order_id}")
        return True
    
    async def get_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get current positions"""
        
        positions = []
        
        for pos_symbol, position in self.positions.items():
            if symbol and pos_symbol != symbol:
                continue
            
            # Get current price for unrealized PnL
            quote = await self.get_quote(pos_symbol)
            current_price = float(quote.get("price", 0)) if quote else position["average_price"]
            
            quantity = position["quantity"]
            avg_price = position["average_price"]
            current_value = quantity * current_price
            cost_basis = quantity * avg_price
            unrealized_pnl = current_value - cost_basis
            unrealized_pnl_pct = (unrealized_pnl / cost_basis * 100) if cost_basis > 0 else 0
            
            positions.append({
                "symbol": pos_symbol,
                "quantity": quantity,
                "average_price": avg_price,
                "current_price": current_price,
                "cost_basis": cost_basis,
                "current_value": current_value,
                "unrealized_pnl": unrealized_pnl,
                "unrealized_pnl_percent": unrealized_pnl_pct
            })
        
        return positions
    
    async def get_orders(
        self,
        status: Optional[OrderStatus] = None,
        symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get orders"""
        
        orders = []
        
        for order_id, order in self.orders.items():
            if status and order["status"] != status.value:
                continue
            if symbol and order["symbol"] != symbol:
                continue
            
            orders.append(order)
        
        return orders
    
    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get current quote"""
        
        quote_data = market_data_service.get_quote(symbol)
        if not quote_data:
            return {
                "symbol": symbol,
                "price": 0.0,
                "volume": 0,
                "timestamp": datetime.now().isoformat()
            }
        
        return quote_data
    
    async def get_portfolio_summary(self) -> Dict[str, Any]:
        """Get portfolio summary"""
        
        positions = await self.get_positions()
        
        total_position_value = sum([p["current_value"] for p in positions])
        total_unrealized_pnl = sum([p["unrealized_pnl"] for p in positions])
        total_realized_pnl = sum([t.get("realized_pnl", 0) for t in self.trades])
        
        portfolio_value = self.cash + total_position_value
        total_pnl = total_unrealized_pnl + total_realized_pnl
        total_return = (total_pnl / self.initial_capital * 100) if self.initial_capital > 0 else 0
        
        return {
            "portfolio_id": self.portfolio_id,
            "user_id": self.user_id,
            "initial_capital": self.initial_capital,
            "cash": self.cash,
            "total_position_value": total_position_value,
            "portfolio_value": portfolio_value,
            "total_unrealized_pnl": total_unrealized_pnl,
            "total_realized_pnl": total_realized_pnl,
            "total_pnl": total_pnl,
            "total_return_percent": total_return,
            "positions_count": len(positions),
            "trades_count": len(self.trades),
            "timestamp": datetime.now().isoformat()
        }






