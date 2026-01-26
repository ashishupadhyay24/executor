"""
Pydantic models for workflow execution state
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class ExecutionStatus(str, Enum):
    """Execution status enum"""
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"
    STOPPED = "stopped"
    PAUSED = "paused"


class LogLevel(str, Enum):
    """Log level enum"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"
    DEBUG = "debug"


class ExecutionLog(BaseModel):
    """Single log entry during execution"""
    id: str
    timestamp: str
    level: LogLevel
    message: str
    nodeId: Optional[str] = None
    data: Optional[Any] = None
    
    class Config:
        use_enum_values = True


class ExecutionResult(BaseModel):
    """Result of a node execution"""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    logs: Optional[List[ExecutionLog]] = Field(default_factory=list)


class NodeExecutionContext(BaseModel):
    """Context for executing a single node"""
    nodeId: str
    nodeType: str
    config: Dict[str, Any]
    inputs: Dict[str, Any]
    outputs: Dict[str, Any]
    executionId: str
    workflowId: str
    userId: Optional[str] = "default_user"
    portfolioId: Optional[str] = "default_portfolio"
    
    class Config:
        extra = "allow"


class ExecutionState(BaseModel):
    """Complete state of a workflow execution"""
    id: str
    workflowId: str
    status: ExecutionStatus
    startTime: str
    endTime: Optional[str] = None
    currentStep: Optional[str] = None
    progress: float = 0.0
    logs: List[ExecutionLog] = Field(default_factory=list)
    results: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    userId: Optional[str] = "default_user"
    portfolioId: Optional[str] = "default_portfolio"
    
    class Config:
        use_enum_values = True


class ExecutionStatusResponse(BaseModel):
    """Response for execution status query"""
    execution: ExecutionState
    
    
class ExecutionLogsResponse(BaseModel):
    """Response for execution logs query"""
    executionId: str
    logs: List[ExecutionLog]


class ExecutionStartResponse(BaseModel):
    """Response when starting an execution"""
    executionId: str
    status: str
    message: str

