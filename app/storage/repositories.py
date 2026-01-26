"""
Repository classes for database operations
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime

from .models import (
    ExecutionModel,
    ExecutionLogModel,
    OrderModel,
    PositionModel,
    BrokerSessionModel
)
from app.models.execution import ExecutionState, ExecutionLog, ExecutionStatus, LogLevel


class ExecutionRepository:
    """Repository for execution operations"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create(self, execution: ExecutionState, trading_mode: str = "paper") -> ExecutionModel:
        """Create a new execution record"""
        db_execution = ExecutionModel(
            id=execution.id,
            workflow_id=execution.workflowId,
            user_id=execution.userId or "default_user",
            portfolio_id=execution.portfolioId or "default_portfolio",
            trading_mode=trading_mode,
            status=execution.status.value if hasattr(execution.status, 'value') else str(execution.status),
            start_time=datetime.fromisoformat(execution.startTime.replace('Z', '+00:00')) if execution.startTime else datetime.utcnow(),
            end_time=datetime.fromisoformat(execution.endTime.replace('Z', '+00:00')) if execution.endTime else None,
            current_step=execution.currentStep,
            progress=execution.progress,
            error=execution.error,
            results=execution.results
        )
        self.db.add(db_execution)
        self.db.commit()
        self.db.refresh(db_execution)
        return db_execution
    
    def get(self, execution_id: str) -> Optional[ExecutionModel]:
        """Get execution by ID"""
        return self.db.query(ExecutionModel).filter(ExecutionModel.id == execution_id).first()
    
    def update(self, execution: ExecutionState) -> Optional[ExecutionModel]:
        """Update execution"""
        db_execution = self.get(execution.id)
        if not db_execution:
            return None
        
        db_execution.status = execution.status.value if hasattr(execution.status, 'value') else str(execution.status)
        db_execution.end_time = datetime.fromisoformat(execution.endTime.replace('Z', '+00:00')) if execution.endTime else None
        db_execution.current_step = execution.currentStep
        db_execution.progress = execution.progress
        db_execution.error = execution.error
        db_execution.results = execution.results
        db_execution.updated_at = datetime.utcnow()
        
        self.db.commit()
        self.db.refresh(db_execution)
        return db_execution
    
    def list(self, user_id: Optional[str] = None, limit: int = 100) -> List[ExecutionModel]:
        """List executions"""
        query = self.db.query(ExecutionModel)
        if user_id:
            query = query.filter(ExecutionModel.user_id == user_id)
        return query.order_by(ExecutionModel.start_time.desc()).limit(limit).all()
    
    def add_log(self, execution_id: str, log: ExecutionLog) -> ExecutionLogModel:
        """Add log to execution"""
        db_log = ExecutionLogModel(
            id=log.id,
            execution_id=execution_id,
            timestamp=datetime.fromisoformat(log.timestamp.replace('Z', '+00:00')) if log.timestamp else datetime.utcnow(),
            level=log.level.value if hasattr(log.level, 'value') else str(log.level),
            message=log.message,
            node_id=log.nodeId,
            data=log.data
        )
        self.db.add(db_log)
        self.db.commit()
        self.db.refresh(db_log)
        return db_log


class OrderRepository:
    """Repository for order operations"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create(self, order_data: Dict[str, Any], execution_id: str, trading_mode: str = "paper") -> OrderModel:
        """Create order record"""
        # Normalize timestamps (accept ISO strings)
        def _parse_dt(value: Any) -> Optional[datetime]:
            if not value:
                return None
            if isinstance(value, datetime):
                return value
            if isinstance(value, str):
                try:
                    return datetime.fromisoformat(value.replace('Z', '+00:00'))
                except Exception:
                    return None
            return None

        status = (order_data.get("status") or "pending").lower()
        ts = _parse_dt(order_data.get("timestamp")) or datetime.utcnow()
        filled_at = _parse_dt(order_data.get("filled_at")) or (_parse_dt(order_data.get("filledAt")))
        cancelled_at = _parse_dt(order_data.get("cancelled_at")) or (_parse_dt(order_data.get("cancelledAt")))

        # If marked filled but no filled_at provided, default to timestamp
        if status == "filled" and not filled_at:
            filled_at = ts
        if status == "cancelled" and not cancelled_at:
            cancelled_at = ts

        db_order = OrderModel(
            id=f"order_db_{order_data.get('order_id', 'unknown')}",
            execution_id=execution_id,
            order_id=order_data.get("order_id", ""),
            symbol=order_data.get("symbol", ""),
            side=order_data.get("side", ""),
            quantity=order_data.get("quantity", 0),
            order_type=order_data.get("order_type", ""),
            status=status,
            execution_price=order_data.get("execution_price"),
            limit_price=order_data.get("limit_price"),
            stop_price=order_data.get("stop_price"),
            order_value=order_data.get("order_value") or order_data.get("total_cost") or order_data.get("total_proceeds"),
            trading_mode=trading_mode,
            user_id=order_data.get("user_id", "default_user"),
            portfolio_id=order_data.get("portfolio_id", "default_portfolio"),
            timestamp=ts,
            filled_at=filled_at,
            cancelled_at=cancelled_at,
            order_data=order_data
        )
        self.db.add(db_order)
        self.db.commit()
        self.db.refresh(db_order)
        return db_order
    
    def get(self, order_id: str) -> Optional[OrderModel]:
        """Get order by ID"""
        return self.db.query(OrderModel).filter(OrderModel.order_id == order_id).first()
    
    def list(
        self, 
        execution_id: Optional[str] = None, 
        user_id: Optional[str] = None,
        portfolio_id: Optional[str] = None,
        trading_mode: Optional[str] = None,
        limit: int = 100
    ) -> List[OrderModel]:
        """List orders with optional filters"""
        query = self.db.query(OrderModel)
        if execution_id:
            query = query.filter(OrderModel.execution_id == execution_id)
        if user_id:
            query = query.filter(OrderModel.user_id == user_id)
        if portfolio_id:
            query = query.filter(OrderModel.portfolio_id == portfolio_id)
        if trading_mode:
            query = query.filter(OrderModel.trading_mode == trading_mode)
        return query.order_by(OrderModel.timestamp.desc()).limit(limit).all()


class PositionRepository:
    """Repository for position operations"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def upsert(self, position_data: Dict[str, Any], user_id: str, portfolio_id: str, trading_mode: str = "paper") -> PositionModel:
        """Create or update position"""
        # Find existing position
        db_position = self.db.query(PositionModel).filter(
            PositionModel.user_id == user_id,
            PositionModel.portfolio_id == portfolio_id,
            PositionModel.symbol == position_data.get("symbol"),
            PositionModel.trading_mode == trading_mode
        ).first()
        
        if db_position:
            # Update
            db_position.quantity = position_data.get("quantity", 0)
            db_position.average_price = position_data.get("average_price", 0.0)
            db_position.current_price = position_data.get("current_price", 0.0)
            db_position.cost_basis = position_data.get("cost_basis", 0.0)
            db_position.current_value = position_data.get("current_value", 0.0)
            db_position.unrealized_pnl = position_data.get("unrealized_pnl", 0.0)
            db_position.updated_at = datetime.utcnow()
        else:
            # Create
            import uuid
            db_position = PositionModel(
                id=f"pos_{uuid.uuid4().hex[:16]}",
                user_id=user_id,
                portfolio_id=portfolio_id,
                symbol=position_data.get("symbol", ""),
                quantity=position_data.get("quantity", 0),
                average_price=position_data.get("average_price", 0.0),
                current_price=position_data.get("current_price", 0.0),
                cost_basis=position_data.get("cost_basis", 0.0),
                current_value=position_data.get("current_value", 0.0),
                unrealized_pnl=position_data.get("unrealized_pnl", 0.0),
                trading_mode=trading_mode
            )
            self.db.add(db_position)
        
        self.db.commit()
        self.db.refresh(db_position)
        return db_position
    
    def list(self, user_id: str, portfolio_id: Optional[str] = None, trading_mode: str = "paper") -> List[PositionModel]:
        """List positions"""
        query = self.db.query(PositionModel).filter(
            PositionModel.user_id == user_id,
            PositionModel.trading_mode == trading_mode
        )
        if portfolio_id:
            query = query.filter(PositionModel.portfolio_id == portfolio_id)
        return query.all()


class BrokerSessionRepository:
    """Repository for broker session operations"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def upsert(self, user_id: str, broker_type: str, access_token: Optional[str] = None, **kwargs) -> BrokerSessionModel:
        """Create or update broker session"""
        db_session = self.db.query(BrokerSessionModel).filter(
            BrokerSessionModel.user_id == user_id,
            BrokerSessionModel.broker_type == broker_type
        ).first()
        
        if db_session:
            # Update
            if access_token is not None:
                db_session.access_token = access_token
            if kwargs.get("api_key") is not None:
                db_session.api_key = kwargs.get("api_key")
            if kwargs.get("api_secret") is not None:
                db_session.api_secret = kwargs.get("api_secret")
            if kwargs.get("refresh_token") is not None:
                db_session.refresh_token = kwargs.get("refresh_token")
            if kwargs.get("expires_at") is not None:
                db_session.expires_at = kwargs.get("expires_at")
            db_session.updated_at = datetime.utcnow()
        else:
            # Create
            import uuid
            db_session = BrokerSessionModel(
                id=f"session_{uuid.uuid4().hex[:16]}",
                user_id=user_id,
                broker_type=broker_type,
                access_token=access_token,
                api_key=kwargs.get("api_key"),
                api_secret=kwargs.get("api_secret"),
                refresh_token=kwargs.get("refresh_token"),
                expires_at=kwargs.get("expires_at")
            )
            self.db.add(db_session)
        
        self.db.commit()
        self.db.refresh(db_session)
        return db_session
    
    def get(self, user_id: str, broker_type: str) -> Optional[BrokerSessionModel]:
        """Get broker session"""
        return self.db.query(BrokerSessionModel).filter(
            BrokerSessionModel.user_id == user_id,
            BrokerSessionModel.broker_type == broker_type
        ).first()

