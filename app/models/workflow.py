"""
Pydantic models for workflow structure
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class NodeData(BaseModel):
    """Node configuration data"""
    type: Optional[str] = None
    label: Optional[str] = None
    description: Optional[str] = None
    # Node-specific configuration
    symbol: Optional[str] = None
    quantity: Optional[int] = None
    orderType: Optional[str] = None
    side: Optional[str] = None
    price: Optional[float] = None
    limitPrice: Optional[float] = None
    stopPrice: Optional[float] = None
    portfolioId: Optional[str] = None
    # Condition node config
    operator: Optional[str] = None
    value: Optional[Any] = None
    condition: Optional[str] = None
    threshold: Optional[float] = None
    thresholdType: Optional[str] = None
    # Technical indicator config
    indicator: Optional[str] = None
    period: Optional[int] = None
    shortPeriod: Optional[int] = None
    longPeriod: Optional[int] = None
    # Time config
    timeframe: Optional[str] = None
    interval: Optional[str] = None
    startDate: Optional[str] = None
    endDate: Optional[str] = None
    # Alert config
    alertType: Optional[str] = None
    message: Optional[str] = None
    recipients: Optional[List[str]] = None
    # Delay config
    duration: Optional[int] = None
    # Boolean logic config
    inputs: Optional[int] = None
    # Pattern detection
    patternType: Optional[str] = None
    pattern: Optional[str] = None
    # Stop loss config
    stopType: Optional[str] = None
    stopPercentage: Optional[float] = None
    # General purpose fields
    enabled: Optional[bool] = True
    
    class Config:
        extra = "allow"  # Allow additional fields


class NodePosition(BaseModel):
    """Node position on canvas"""
    x: float
    y: float


class Node(BaseModel):
    """Workflow node"""
    id: str
    type: str
    position: NodePosition
    data: NodeData
    
    class Config:
        extra = "allow"


class Edge(BaseModel):
    """Connection between nodes"""
    id: str
    source: str
    target: str
    sourceHandle: Optional[str] = None
    targetHandle: Optional[str] = None
    type: Optional[str] = None
    style: Optional[Dict[str, Any]] = None
    
    class Config:
        extra = "allow"


class Workflow(BaseModel):
    """Complete workflow definition"""
    id: str
    name: str
    description: Optional[str] = ""
    nodes: List[Node]
    edges: List[Edge]
    status: Optional[str] = "draft"
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None
    userId: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = Field(default_factory=list)
    executionCount: Optional[int] = 0
    successCount: Optional[int] = 0
    errorCount: Optional[int] = 0
    totalPnL: Optional[float] = 0.0
    isPublic: Optional[bool] = False
    
    class Config:
        extra = "allow"


class WorkflowExecuteRequest(BaseModel):
    """Request to execute a workflow"""
    workflow: Workflow
    userId: Optional[str] = "default_user"
    portfolioId: Optional[str] = "default_portfolio"

