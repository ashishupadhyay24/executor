"""
API routes for portfolio management and paper trading data
"""

from fastapi import APIRouter, HTTPException, status, Query
from pydantic import BaseModel
from typing import List, Optional, Any, Dict
from datetime import datetime
import logging
import os
import uuid

from app.storage.db import get_db
from app.storage.repositories import (
    PositionRepository,
    OrderRepository,
)
from app.services.market_data import market_data_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

# Default initial capital from environment
DEFAULT_INITIAL_CAPITAL = float(os.getenv("PAPER_TRADING_INITIAL_CAPITAL", "100000.0"))


# Request/Response models
class PlaceOrderRequest(BaseModel):
    """Request body for placing a paper trading order"""
    userId: str
    portfolioId: str = "default_portfolio"
    tradingMode: str = "paper"
    symbol: str
    side: str  # BUY or SELL
    quantity: int
    orderType: str = "MARKET"  # MARKET, LIMIT, STOP, STOP_LIMIT
    limitPrice: Optional[float] = None
    stopPrice: Optional[float] = None


def apply_order_to_position(
    db,
    user_id: str,
    portfolio_id: str,
    trading_mode: str,
    symbol: str,
    side: str,
    quantity: int,
    execution_price: float
) -> Dict[str, Any]:
    """
    Apply a filled order to a position record.
    
    - For BUY: increases position, updates average price
    - For SELL: decreases position, calculates realized PnL
    
    Returns the updated position data.
    """
    position_repo = PositionRepository(db)
    
    # Get current position (or create new one)
    positions = position_repo.list(
        user_id=user_id,
        portfolio_id=portfolio_id,
        trading_mode=trading_mode
    )
    
    current_position = None
    for pos in positions:
        if pos.symbol == symbol:
            current_position = pos
            break
    
    # Calculate new position values
    old_quantity = current_position.quantity if current_position else 0
    old_avg_price = current_position.average_price if current_position else 0.0
    old_cost_basis = current_position.cost_basis if current_position else 0.0
    
    realized_pnl = 0.0
    
    if side.upper() == "BUY":
        # Add to position
        new_quantity = old_quantity + quantity
        new_cost_basis = old_cost_basis + (quantity * execution_price)
        new_avg_price = new_cost_basis / new_quantity if new_quantity > 0 else 0.0
    else:  # SELL
        # Reduce position
        if quantity > old_quantity:
            # Can't sell more than we have
            quantity = old_quantity
        
        new_quantity = old_quantity - quantity
        
        # Calculate realized PnL for the sold shares
        realized_pnl = (execution_price - old_avg_price) * quantity
        
        # Reduce cost basis proportionally
        if old_quantity > 0:
            new_cost_basis = old_cost_basis * (new_quantity / old_quantity)
        else:
            new_cost_basis = 0.0
        
        new_avg_price = old_avg_price if new_quantity > 0 else 0.0
    
    # Get current market price for unrealized PnL calculation
    current_price = execution_price  # Default to execution price
    try:
        quote = market_data_service.get_quote(symbol)
        if quote and quote.get("price"):
            current_price = float(quote["price"])
    except Exception as e:
        logger.warning(f"Could not fetch current price for {symbol}: {e}")
    
    # Calculate current value and unrealized PnL
    current_value = new_quantity * current_price
    unrealized_pnl = current_value - new_cost_basis if new_quantity > 0 else 0.0
    
    # Build position data
    position_data = {
        "symbol": symbol,
        "quantity": new_quantity,
        "average_price": new_avg_price,
        "current_price": current_price,
        "cost_basis": new_cost_basis,
        "current_value": current_value,
        "unrealized_pnl": unrealized_pnl,
    }
    
    # Upsert position (only if quantity > 0, otherwise could delete)
    if new_quantity > 0:
        position_repo.upsert(
            position_data=position_data,
            user_id=user_id,
            portfolio_id=portfolio_id,
            trading_mode=trading_mode
        )
    elif current_position and new_quantity == 0:
        # Position closed - update to zero
        position_repo.upsert(
            position_data=position_data,
            user_id=user_id,
            portfolio_id=portfolio_id,
            trading_mode=trading_mode
        )
    
    return {
        "position": position_data,
        "realized_pnl": realized_pnl,
        "side": side,
        "quantity_executed": quantity,
        "execution_price": execution_price,
    }


@router.get("/summary")
async def get_portfolio_summary(
    userId: str = Query(..., description="User ID"),
    portfolioId: str = Query("default_portfolio", description="Portfolio ID"),
    tradingMode: str = Query("paper", description="Trading mode (paper or kite)")
):
    """
    Get portfolio summary including balance, positions, and PnL.
    
    Returns a shape compatible with the frontend PaperTradingPortfolio interface.
    """
    try:
        db = next(get_db())
        try:
            position_repo = PositionRepository(db)
            order_repo = OrderRepository(db)
            
            # Get positions
            positions = position_repo.list(
                user_id=userId,
                portfolio_id=portfolioId,
                trading_mode=tradingMode
            )
            
            # Get orders
            orders = order_repo.list(
                user_id=userId,
                portfolio_id=portfolioId,
                trading_mode=tradingMode,
                limit=2000
            )
            
            # Calculate portfolio metrics
            total_market_value = 0.0
            total_unrealized_pnl = 0.0
            total_cost_basis = 0.0
            
            # Convert positions to frontend format
            positions_data = []
            for pos in positions:
                market_value = pos.current_value or (pos.quantity * pos.current_price if pos.current_price else 0)
                unrealized_pnl = pos.unrealized_pnl or 0
                cost_basis = pos.cost_basis or (pos.quantity * pos.average_price if pos.average_price else 0)
                
                total_market_value += market_value
                total_unrealized_pnl += unrealized_pnl
                total_cost_basis += cost_basis
                
                # Calculate PnL percent
                pnl_percent = (unrealized_pnl / cost_basis * 100) if cost_basis > 0 else 0
                
                positions_data.append({
                    "id": pos.id,
                    "symbol": pos.symbol,
                    "quantity": pos.quantity,
                    "averageEntryPrice": pos.average_price,
                    "currentPrice": pos.current_price,
                    "marketValue": market_value,
                    "unrealizedPnL": unrealized_pnl,
                    "unrealizedPnLPercent": pnl_percent,
                    "realizedPnL": 0,  # Would need trade history to calculate
                    "totalPnL": unrealized_pnl,
                    "totalPnLPercent": pnl_percent,
                    "lastUpdated": pos.updated_at.isoformat() if pos.updated_at else datetime.utcnow().isoformat(),
                    "orders": [],  # Order IDs would need association
                })
            
            # Convert orders to frontend format
            orders_data = []
            total_realized_pnl = 0.0
            cash_spent = 0.0
            cash_received = 0.0

            # Replay fills in chronological order to compute realized PnL robustly
            # (works even if older rows don't have realized_pnl stored)
            positions_state: Dict[str, Dict[str, float]] = {}  # symbol -> {qty, avg}
            filled_orders = [o for o in orders if (o.status or "").lower() == "filled" and o.execution_price is not None]
            filled_orders.sort(key=lambda o: o.timestamp or datetime.utcnow())

            for o in filled_orders:
                sym = (o.symbol or "").upper()
                side = (o.side or "").upper()
                price = float(o.execution_price or 0.0)
                executed_qty = int((o.order_data or {}).get("quantity_executed") or o.quantity or 0)

                if sym not in positions_state:
                    positions_state[sym] = {"qty": 0.0, "avg": 0.0}
                st = positions_state[sym]

                if side == "BUY":
                    cash_spent += price * executed_qty
                    old_qty = st["qty"]
                    old_avg = st["avg"]
                    new_qty = old_qty + executed_qty
                    if new_qty > 0:
                        st["avg"] = ((old_qty * old_avg) + (executed_qty * price)) / new_qty
                    st["qty"] = new_qty
                elif side == "SELL":
                    cash_received += price * executed_qty
                    old_qty = st["qty"]
                    sell_qty = min(executed_qty, int(old_qty))
                    total_realized_pnl += (price - st["avg"]) * sell_qty
                    st["qty"] = max(0.0, old_qty - sell_qty)
                    if st["qty"] == 0:
                        st["avg"] = 0.0
            
            for order in orders:
                order_data = {
                    "id": order.order_id or order.id,
                    "symbol": order.symbol,
                    "orderType": order.order_type.upper() if order.order_type else "MARKET",
                    "side": order.side.upper() if order.side else "BUY",
                    "quantity": order.quantity,
                    "price": order.limit_price or order.execution_price,
                    "stopPrice": order.stop_price,
                    "status": order.status.upper() if order.status else "PENDING",
                    "filledQuantity": (
                        int((order.order_data or {}).get("quantity_executed") or order.quantity)
                        if (order.status or "").lower() == "filled"
                        else 0
                    ),
                    "averageFillPrice": order.execution_price or 0,
                    "createdAt": order.timestamp.isoformat() if order.timestamp else datetime.utcnow().isoformat(),
                    "updatedAt": (order.filled_at.isoformat() if order.filled_at else order.timestamp.isoformat()) if order.timestamp else datetime.utcnow().isoformat(),
                }
                orders_data.append(order_data)
            
            # Calculate available cash
            initial_balance = DEFAULT_INITIAL_CAPITAL
            # Cash = initial - buys + sells (from filled orders)
            available_cash = initial_balance - cash_spent + cash_received
            current_balance = available_cash
            total_equity = available_cash + total_market_value
            # Total PnL based on equity change (robust) + expose realized/unrealized split
            total_pnl = total_equity - initial_balance
            total_pnl_percent = (total_pnl / initial_balance * 100) if initial_balance > 0 else 0
            
            # Build portfolio summary in frontend-compatible format
            portfolio_summary = {
                "id": portfolioId,
                "userId": userId,
                "name": f"Portfolio - {portfolioId}",
                "description": f"Paper trading portfolio for {userId}",
                "initialBalance": initial_balance,
                "currentBalance": current_balance,
                "availableCash": available_cash,
                "totalEquity": total_equity,
                "totalMarketValue": total_market_value,
                "totalUnrealizedPnL": total_unrealized_pnl,
                "totalRealizedPnL": total_realized_pnl,
                "totalPnL": total_pnl,
                "totalPnLPercent": total_pnl_percent,
                "positions": positions_data,
                "orders": orders_data,
                "createdAt": datetime.utcnow().isoformat(),
                "updatedAt": datetime.utcnow().isoformat(),
                "isActive": True,
                "settings": {
                    "allowShortSelling": False,
                    "maxPositionSize": 20,
                    "maxLeverage": 1,
                    "tradingHours": {
                        "start": "09:15",
                        "end": "15:30",
                        "timezone": "Asia/Kolkata",
                    },
                    "commission": 0.0,
                    "slippage": 0.1,
                    "riskManagement": {
                        "maxDrawdown": 20,
                        "stopLossPercentage": 10,
                        "takeProfitPercentage": 20,
                    },
                },
            }
            
            return portfolio_summary
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error getting portfolio summary: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get portfolio summary: {str(e)}"
        )


@router.get("/positions")
async def get_positions(
    userId: str = Query(..., description="User ID"),
    portfolioId: str = Query(None, description="Portfolio ID (optional)"),
    tradingMode: str = Query("paper", description="Trading mode (paper or kite)")
):
    """
    Get positions for a user/portfolio.
    
    Returns positions in frontend-compatible format.
    """
    try:
        db = next(get_db())
        try:
            position_repo = PositionRepository(db)
            
            positions = position_repo.list(
                user_id=userId,
                portfolio_id=portfolioId,
                trading_mode=tradingMode
            )
            
            # Convert to frontend format
            positions_data = []
            for pos in positions:
                market_value = pos.current_value or (pos.quantity * pos.current_price if pos.current_price else 0)
                unrealized_pnl = pos.unrealized_pnl or 0
                cost_basis = pos.cost_basis or (pos.quantity * pos.average_price if pos.average_price else 0)
                pnl_percent = (unrealized_pnl / cost_basis * 100) if cost_basis > 0 else 0
                
                positions_data.append({
                    "id": pos.id,
                    "symbol": pos.symbol,
                    "quantity": pos.quantity,
                    "averageEntryPrice": pos.average_price,
                    "currentPrice": pos.current_price,
                    "marketValue": market_value,
                    "unrealizedPnL": unrealized_pnl,
                    "unrealizedPnLPercent": pnl_percent,
                    "realizedPnL": 0,
                    "totalPnL": unrealized_pnl,
                    "totalPnLPercent": pnl_percent,
                    "lastUpdated": pos.updated_at.isoformat() if pos.updated_at else datetime.utcnow().isoformat(),
                    "orders": [],
                })
            
            return {
                "positions": positions_data,
                "count": len(positions_data),
                "userId": userId,
                "portfolioId": portfolioId,
                "tradingMode": tradingMode
            }
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error getting positions: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get positions: {str(e)}"
        )


@router.get("/orders")
async def get_orders(
    userId: str = Query(..., description="User ID"),
    portfolioId: str = Query(None, description="Portfolio ID (optional)"),
    tradingMode: str = Query("paper", description="Trading mode (paper or kite)"),
    limit: int = Query(100, description="Maximum number of orders to return")
):
    """
    Get orders for a user/portfolio.
    
    Returns orders in frontend-compatible format.
    """
    try:
        db = next(get_db())
        try:
            order_repo = OrderRepository(db)
            
            orders = order_repo.list(
                user_id=userId,
                portfolio_id=portfolioId,
                trading_mode=tradingMode,
                limit=limit
            )
            
            # Convert to frontend format
            orders_data = []
            for order in orders:
                orders_data.append({
                    "id": order.order_id or order.id,
                    "symbol": order.symbol,
                    "orderType": order.order_type.upper() if order.order_type else "MARKET",
                    "side": order.side.upper() if order.side else "BUY",
                    "quantity": order.quantity,
                    "price": order.limit_price or order.execution_price,
                    "stopPrice": order.stop_price,
                    "status": order.status.upper() if order.status else "PENDING",
                    "filledQuantity": (
                        int((order.order_data or {}).get("quantity_executed") or order.quantity)
                        if (order.status or "").lower() == "filled"
                        else 0
                    ),
                    "averageFillPrice": order.execution_price or 0,
                    "createdAt": order.timestamp.isoformat() if order.timestamp else datetime.utcnow().isoformat(),
                    "updatedAt": (order.filled_at.isoformat() if order.filled_at else order.timestamp.isoformat()) if order.timestamp else datetime.utcnow().isoformat(),
                    "executionId": order.execution_id,
                })
            
            return {
                "orders": orders_data,
                "count": len(orders_data),
                "userId": userId,
                "portfolioId": portfolioId,
                "tradingMode": tradingMode
            }
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error getting orders: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get orders: {str(e)}"
        )


@router.post("/place-order")
async def place_order(request: PlaceOrderRequest):
    """
    Place a paper trading order.
    
    For MARKET orders, executes immediately using current Yahoo quote.
    Returns the order details and updated portfolio summary.
    """
    try:
        db = next(get_db())
        try:
            order_repo = OrderRepository(db)
            
            symbol = request.symbol.upper()
            side = request.side.upper()
            quantity = request.quantity
            order_type = request.orderType.upper()
            
            # Validate side
            if side not in ["BUY", "SELL"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid side: {side}. Must be BUY or SELL."
                )
            
            # Validate quantity
            if quantity <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Quantity must be greater than 0"
                )
            
            # Get current market price
            quote = market_data_service.get_quote(symbol)
            if not quote or not quote.get("price"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Could not get quote for symbol: {symbol}"
                )
            
            current_price = float(quote["price"])
            
            # Determine execution price and status based on order type
            execution_price = None
            order_status = "pending"
            
            if order_type == "MARKET":
                execution_price = current_price
                order_status = "filled"
            elif order_type == "LIMIT":
                if request.limitPrice is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Limit price required for LIMIT order"
                    )
                # Check if limit order can be filled immediately
                if side == "BUY" and current_price <= request.limitPrice:
                    execution_price = min(current_price, request.limitPrice)
                    order_status = "filled"
                elif side == "SELL" and current_price >= request.limitPrice:
                    execution_price = max(current_price, request.limitPrice)
                    order_status = "filled"
                else:
                    order_status = "pending"
            elif order_type == "STOP":
                if request.stopPrice is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Stop price required for STOP order"
                    )
                # Check if stop order is triggered
                if side == "BUY" and current_price >= request.stopPrice:
                    execution_price = current_price
                    order_status = "filled"
                elif side == "SELL" and current_price <= request.stopPrice:
                    execution_price = current_price
                    order_status = "filled"
                else:
                    order_status = "pending"
            
            # For SELL orders, check if we have enough shares
            if side == "SELL" and order_status == "filled":
                position_repo = PositionRepository(db)
                positions = position_repo.list(
                    user_id=request.userId,
                    portfolio_id=request.portfolioId,
                    trading_mode=request.tradingMode
                )
                current_qty = 0
                for pos in positions:
                    if pos.symbol == symbol:
                        current_qty = pos.quantity
                        break
                
                if quantity > current_qty:
                    order_status = "rejected"
                    execution_price = None
                    logger.warning(f"Insufficient shares to sell: {quantity} > {current_qty}")
            
            # For BUY orders, check if we have enough cash (simplified)
            if side == "BUY" and order_status == "filled":
                # Get current portfolio to check available cash
                position_repo = PositionRepository(db)
                positions = position_repo.list(
                    user_id=request.userId,
                    portfolio_id=request.portfolioId,
                    trading_mode=request.tradingMode
                )
                total_cost_basis = sum(pos.cost_basis or 0 for pos in positions)
                available_cash = DEFAULT_INITIAL_CAPITAL - total_cost_basis
                order_value = execution_price * quantity
                
                if order_value > available_cash:
                    order_status = "rejected"
                    execution_price = None
                    logger.warning(f"Insufficient cash: ${order_value:.2f} > ${available_cash:.2f}")
            
            # Generate order ID
            order_id = f"manual_order_{uuid.uuid4().hex[:16]}"
            
            # Build order data
            order_data = {
                "order_id": order_id,
                "symbol": symbol,
                "side": side.lower(),
                "quantity": quantity,
                "order_type": order_type.lower(),
                "status": order_status,
                "limit_price": request.limitPrice,
                "stop_price": request.stopPrice,
                "execution_price": execution_price,
                "order_value": (execution_price * quantity) if execution_price else None,
                "timestamp": datetime.utcnow().isoformat(),
                "user_id": request.userId,
                "portfolio_id": request.portfolioId,
            }

            # If filled, update position and attach realized_pnl to order_data for persistence
            position_result = None
            if order_status == "filled" and execution_price:
                position_result = apply_order_to_position(
                    db=db,
                    user_id=request.userId,
                    portfolio_id=request.portfolioId,
                    trading_mode=request.tradingMode,
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    execution_price=execution_price
                )
                if position_result:
                    order_data["realized_pnl"] = float(position_result.get("realized_pnl") or 0.0)
                    order_data["quantity_executed"] = int(position_result.get("quantity_executed") or quantity)
                    order_data["filled_at"] = datetime.utcnow().isoformat()

            # Persist order (with realized_pnl when applicable)
            order_repo.create(
                order_data=order_data,
                execution_id=f"manual_{uuid.uuid4().hex[:8]}",
                trading_mode=request.tradingMode
            )
            
            # Build response order in frontend format
            order_response = {
                "id": order_id,
                "symbol": symbol,
                "orderType": order_type,
                "side": side,
                "quantity": quantity,
                "price": request.limitPrice or execution_price,
                "stopPrice": request.stopPrice,
                "status": order_status.upper(),
                "filledQuantity": (position_result.get("quantity_executed") if position_result else quantity) if order_status == "filled" else 0,
                "averageFillPrice": execution_price or 0,
                "createdAt": datetime.utcnow().isoformat(),
                "updatedAt": datetime.utcnow().isoformat(),
            }
            
            # Get updated portfolio summary
            db.commit()  # Commit all changes before fetching summary
            
        finally:
            db.close()
        
        # Fetch fresh portfolio summary
        portfolio_summary = await get_portfolio_summary(
            userId=request.userId,
            portfolioId=request.portfolioId,
            tradingMode=request.tradingMode
        )
        
        return {
            "success": order_status == "filled",
            "order": order_response,
            "portfolio": portfolio_summary,
            "positionUpdate": position_result,
            "message": f"Order {order_status}" if order_status != "filled" else f"Order filled at ${execution_price:.2f}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error placing order: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to place order: {str(e)}"
        )
