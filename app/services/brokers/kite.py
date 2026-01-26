"""
Zerodha Kite broker service - real trading integration
"""

from typing import Dict, List, Optional, Any
import logging
from datetime import datetime

from .base import BrokerService, OrderSide, OrderType, OrderStatus

logger = logging.getLogger(__name__)


class KiteBrokerService(BrokerService):
    """
    Zerodha Kite broker service for live trading
    
    Requires:
    - KiteConnect API key and secret
    - Access token (obtained via OAuth flow)
    """
    
    def __init__(self, user_id: str, portfolio_id: str, access_token: str, api_key: str):
        super().__init__(user_id, portfolio_id)
        self.access_token = access_token
        self.api_key = api_key
        self._kite = None
        
        logger.info(f"Initialized Kite broker for {user_id}/{portfolio_id}")
    
    def _get_kite(self):
        """Get or create KiteConnect instance"""
        if self._kite is None:
            try:
                from kiteconnect import KiteConnect
                self._kite = KiteConnect(api_key=self.api_key)
                self._kite.set_access_token(self.access_token)
            except ImportError:
                raise ImportError("kiteconnect package not installed. Install with: pip install kiteconnect")
            except Exception as e:
                logger.error(f"Failed to initialize KiteConnect: {str(e)}")
                raise
        
        return self._kite
    
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
        """Place an order via Kite"""
        
        logger.info(f"Placing {side.value} order via Kite: {quantity} {symbol} @ {order_type.value}")
        
        try:
            kite = self._get_kite()
            
            # Convert symbol to Kite format (e.g., "AAPL" -> "NSE:AAPL" or use exchange)
            exchange = kwargs.get("exchange", "NSE")  # Default to NSE
            product = kwargs.get("product", "MIS")  # MIS, CNC, NRML
            validity = kwargs.get("validity", "DAY")  # DAY, IOC, TTL
            
            # Map order types
            kite_variety = "regular"
            if order_type == OrderType.STOP or order_type == OrderType.STOP_LIMIT:
                kite_variety = "SL"
            
            # Build order params
            order_params = {
                "exchange": exchange,
                "tradingsymbol": symbol,
                "transaction_type": side.value,
                "quantity": quantity,
                "product": product,
                "validity": validity,
                "variety": kite_variety
            }
            
            if order_type == OrderType.LIMIT and limit_price:
                order_params["price"] = limit_price
                order_params["order_type"] = "LIMIT"
            elif order_type == OrderType.STOP and stop_price:
                order_params["trigger_price"] = stop_price
                order_params["order_type"] = "SL-M"
            elif order_type == OrderType.STOP_LIMIT and limit_price and stop_price:
                order_params["trigger_price"] = stop_price
                order_params["price"] = limit_price
                order_params["order_type"] = "SL"
            else:
                order_params["order_type"] = "MARKET"
            
            # Place order
            order_response = kite.place_order(**order_params)
            order_id = str(order_response)
            
            logger.info(f"Order placed via Kite: {order_id}")
            
            # Get order details
            order_details = await self._get_order_details(order_id)
            
            return order_details
            
        except Exception as e:
            error_msg = f"Error placing order via Kite: {str(e)}"
            logger.error(error_msg)
            raise
    
    async def _get_order_details(self, order_id: str) -> Dict[str, Any]:
        """Get order details from Kite"""
        
        try:
            kite = self._get_kite()
            orders = kite.orders()
            
            # Find the order
            for order in orders:
                if str(order.get("order_id")) == order_id:
                    return {
                        "order_id": order_id,
                        "symbol": order.get("tradingsymbol"),
                        "side": order.get("transaction_type"),
                        "quantity": order.get("quantity"),
                        "order_type": order.get("order_type"),
                        "status": self._map_kite_status(order.get("status")),
                        "execution_price": order.get("average_price"),
                        "filled_quantity": order.get("filled_quantity"),
                        "pending_quantity": order.get("pending_quantity"),
                        "timestamp": order.get("order_timestamp"),
                        "user_id": self.user_id,
                        "portfolio_id": self.portfolio_id
                    }
            
            # If not found in orders, return basic info
            return {
                "order_id": order_id,
                "status": OrderStatus.PENDING.value,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting order details: {str(e)}")
            return {
                "order_id": order_id,
                "status": OrderStatus.PENDING.value,
                "error": str(e)
            }
    
    def _map_kite_status(self, kite_status: str) -> str:
        """Map Kite order status to our OrderStatus"""
        
        status_map = {
            "COMPLETE": OrderStatus.FILLED.value,
            "REJECTED": OrderStatus.REJECTED.value,
            "CANCELLED": OrderStatus.CANCELLED.value,
            "OPEN": OrderStatus.PENDING.value,
            "TRANSIT": OrderStatus.PENDING.value,
        }
        
        return status_map.get(kite_status, OrderStatus.PENDING.value)
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order via Kite"""
        
        logger.info(f"Cancelling order via Kite: {order_id}")
        
        try:
            kite = self._get_kite()
            
            # Get order details to find variety
            orders = kite.orders()
            order_variety = "regular"
            
            for order in orders:
                if str(order.get("order_id")) == order_id:
                    order_variety = order.get("variety", "regular")
                    break
            
            # Cancel order
            kite.cancel_order(
                order_id=order_id,
                variety=order_variety
            )
            
            logger.info(f"Order cancelled via Kite: {order_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error cancelling order via Kite: {str(e)}")
            return False
    
    async def get_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get current positions from Kite"""
        
        try:
            kite = self._get_kite()
            positions = kite.positions()
            
            result = []
            
            # Kite returns net positions
            for pos in positions.get("net", []):
                pos_symbol = pos.get("tradingsymbol")
                if symbol and pos_symbol != symbol:
                    continue
                
                quantity = pos.get("quantity", 0)
                if quantity == 0:
                    continue
                
                result.append({
                    "symbol": pos_symbol,
                    "quantity": abs(quantity),
                    "average_price": pos.get("average_price", 0),
                    "current_price": pos.get("last_price", 0),
                    "cost_basis": pos.get("buy_value", 0),
                    "current_value": pos.get("sell_value", 0) if quantity < 0 else pos.get("buy_value", 0),
                    "unrealized_pnl": pos.get("pnl", 0),
                    "unrealized_pnl_percent": (pos.get("pnl", 0) / pos.get("buy_value", 1) * 100) if pos.get("buy_value", 0) > 0 else 0
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting positions from Kite: {str(e)}")
            return []
    
    async def get_orders(
        self,
        status: Optional[OrderStatus] = None,
        symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get orders from Kite"""
        
        try:
            kite = self._get_kite()
            orders = kite.orders()
            
            result = []
            
            for order in orders:
                if status and self._map_kite_status(order.get("status")) != status.value:
                    continue
                if symbol and order.get("tradingsymbol") != symbol:
                    continue
                
                result.append({
                    "order_id": str(order.get("order_id")),
                    "symbol": order.get("tradingsymbol"),
                    "side": order.get("transaction_type"),
                    "quantity": order.get("quantity"),
                    "order_type": order.get("order_type"),
                    "status": self._map_kite_status(order.get("status")),
                    "execution_price": order.get("average_price"),
                    "timestamp": order.get("order_timestamp")
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting orders from Kite: {str(e)}")
            return []
    
    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        """Get quote from Kite"""
        
        try:
            kite = self._get_kite()
            
            # Kite requires exchange:tradingsymbol format
            # Try common exchanges
            exchanges = ["NSE", "BSE", "NFO", "MCX"]
            
            for exchange in exchanges:
                try:
                    quote_key = f"{exchange}:{symbol}"
                    quote = kite.quote(quote_key)
                    
                    if quote:
                        ltp_data = quote.get(quote_key, {})
                        return {
                            "symbol": symbol,
                            "price": ltp_data.get("last_price", 0),
                            "volume": ltp_data.get("volume", 0),
                            "timestamp": datetime.now().isoformat()
                        }
                except:
                    continue
            
            # If not found, return empty
            return {
                "symbol": symbol,
                "price": 0.0,
                "volume": 0,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting quote from Kite: {str(e)}")
            return {
                "symbol": symbol,
                "price": 0.0,
                "volume": 0,
                "timestamp": datetime.now().isoformat()
            }
    
    async def get_portfolio_summary(self) -> Dict[str, Any]:
        """Get portfolio summary from Kite"""
        
        try:
            kite = self._get_kite()
            
            # Get margins
            margins = kite.margins()
            
            # Get positions
            positions = await self.get_positions()
            
            total_position_value = sum([p["current_value"] for p in positions])
            total_unrealized_pnl = sum([p["unrealized_pnl"] for p in positions])
            
            available_cash = margins.get("available", {}).get("cash", 0)
            portfolio_value = available_cash + total_position_value
            
            return {
                "portfolio_id": self.portfolio_id,
                "user_id": self.user_id,
                "available_cash": available_cash,
                "total_position_value": total_position_value,
                "portfolio_value": portfolio_value,
                "total_unrealized_pnl": total_unrealized_pnl,
                "positions_count": len(positions),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting portfolio summary from Kite: {str(e)}")
            return {
                "portfolio_id": self.portfolio_id,
                "user_id": self.user_id,
                "error": str(e)
            }






