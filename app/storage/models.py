"""
SQLAlchemy models for persistence
"""

from sqlalchemy import Column, String, Integer, Float, Boolean, Text, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
import json

from .db import Base


class ExecutionModel(Base):
    """Execution persistence model"""
    __tablename__ = "executions"
    
    id = Column(String, primary_key=True)
    workflow_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    portfolio_id = Column(String, nullable=False, index=True)
    trading_mode = Column(String, default="paper")
    status = Column(String, nullable=False, index=True)
    start_time = Column(DateTime, nullable=False, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    current_step = Column(String, nullable=True)
    progress = Column(Float, default=0.0)
    error = Column(Text, nullable=True)
    results = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    logs = relationship("ExecutionLogModel", back_populates="execution", cascade="all, delete-orphan")
    orders = relationship("OrderModel", back_populates="execution", cascade="all, delete-orphan")


class ExecutionLogModel(Base):
    """Execution log persistence model"""
    __tablename__ = "execution_logs"
    
    id = Column(String, primary_key=True)
    execution_id = Column(String, ForeignKey("executions.id"), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    level = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    node_id = Column(String, nullable=True)
    data = Column(JSON, nullable=True)
    
    # Relationship
    execution = relationship("ExecutionModel", back_populates="logs")


class OrderModel(Base):
    """Order persistence model"""
    __tablename__ = "orders"
    
    id = Column(String, primary_key=True)
    execution_id = Column(String, ForeignKey("executions.id"), nullable=False, index=True)
    order_id = Column(String, nullable=False, unique=True, index=True)
    symbol = Column(String, nullable=False, index=True)
    side = Column(String, nullable=False)  # BUY, SELL
    quantity = Column(Integer, nullable=False)
    order_type = Column(String, nullable=False)  # MARKET, LIMIT, etc.
    status = Column(String, nullable=False, index=True)
    execution_price = Column(Float, nullable=True)
    limit_price = Column(Float, nullable=True)
    stop_price = Column(Float, nullable=True)
    order_value = Column(Float, nullable=True)
    trading_mode = Column(String, default="paper")
    user_id = Column(String, nullable=False, index=True)
    portfolio_id = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    filled_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    order_data = Column(JSON, default=dict)
    
    # Relationship
    execution = relationship("ExecutionModel", back_populates="orders")


class PositionModel(Base):
    """Position persistence model"""
    __tablename__ = "positions"
    
    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    portfolio_id = Column(String, nullable=False, index=True)
    symbol = Column(String, nullable=False, index=True)
    quantity = Column(Integer, nullable=False, default=0)
    average_price = Column(Float, nullable=False, default=0.0)
    current_price = Column(Float, nullable=False, default=0.0)
    cost_basis = Column(Float, nullable=False, default=0.0)
    current_value = Column(Float, nullable=False, default=0.0)
    unrealized_pnl = Column(Float, nullable=False, default=0.0)
    trading_mode = Column(String, default="paper")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Unique constraint on user/portfolio/symbol/mode
    __table_args__ = (
        {"sqlite_autoincrement": True},
    )


class BrokerSessionModel(Base):
    """Broker session/token persistence model"""
    __tablename__ = "broker_sessions"
    
    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    broker_type = Column(String, nullable=False)  # kite, paper, etc.
    access_token = Column(Text, nullable=True)  # Encrypted in production
    api_key = Column(String, nullable=True)
    api_secret = Column(Text, nullable=True)  # Encrypted in production
    refresh_token = Column(Text, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

