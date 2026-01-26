"""
Base broker service interface
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum


class OrderSide(str, Enum):
    """Order side"""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """Order type"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderStatus(str, Enum):
    """Order status"""
    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class BrokerService(ABC):
    """
    Abstract base class for broker services
    
    All broker implementations (Paper, Kite, etc.) must inherit from this
    and implement all abstract methods.
    """
    
    def __init__(self, user_id: str, portfolio_id: str):
        self.user_id = user_id
        self.portfolio_id = portfolio_id
    
    @abstractmethod
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
        """
        Place an order
        
        Args:
            symbol: Trading symbol
            side: BUY or SELL
            quantity: Number of shares
            order_type: Order type (MARKET, LIMIT, etc.)
            limit_price: Limit price (for LIMIT orders)
            stop_price: Stop price (for STOP orders)
            **kwargs: Additional order parameters
            
        Returns:
            Order details dictionary with order_id, status, execution_price, etc.
        """
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            True if cancelled successfully
        """
        pass
    
    @abstractmethod
    async def get_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get current positions
        
        Args:
            symbol: Optional symbol to filter by
            
        Returns:
            List of position dictionaries
        """
        pass
    
    @abstractmethod
    async def get_orders(
        self,
        status: Optional[OrderStatus] = None,
        symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get orders
        
        Args:
            status: Optional status filter
            symbol: Optional symbol filter
            
        Returns:
            List of order dictionaries
        """
        pass
    
    @abstractmethod
    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        """
        Get current quote for a symbol
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Quote dictionary with price, volume, etc.
        """
        pass
    
    @abstractmethod
    async def get_portfolio_summary(self) -> Dict[str, Any]:
        """
        Get portfolio summary (cash, positions, PnL, etc.)
        
        Returns:
            Portfolio summary dictionary
        """
        pass






