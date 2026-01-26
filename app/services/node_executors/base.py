"""
Base class for node executors
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import logging
from datetime import datetime
import uuid

from app.models.execution import (
    ExecutionResult,
    ExecutionLog,
    LogLevel,
    NodeExecutionContext
)

logger = logging.getLogger(__name__)


class NodeExecutor(ABC):
    """
    Abstract base class for all node executors
    
    All node type executors must inherit from this class and implement
    the execute() method.
    """
    
    def __init__(self):
        self.logger = logger
    
    @abstractmethod
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """
        Execute the node logic
        
        Args:
            context: Node execution context with configuration and inputs
            
        Returns:
            ExecutionResult with success status, data, and optional error
        """
        pass
    
    def create_result(
        self,
        success: bool,
        data: Optional[Any] = None,
        error: Optional[str] = None
    ) -> ExecutionResult:
        """
        Create a standardized execution result
        
        Args:
            success: Whether execution was successful
            data: Output data from the node
            error: Error message if execution failed
            
        Returns:
            ExecutionResult object
        """
        return ExecutionResult(
            success=success,
            data=data,
            error=error,
            logs=[]
        )
    
    def create_log(
        self,
        level: LogLevel,
        message: str,
        node_id: Optional[str] = None,
        data: Optional[Any] = None
    ) -> ExecutionLog:
        """
        Create a log entry
        
        Args:
            level: Log level (info, warning, error, success, debug)
            message: Log message
            node_id: ID of the node that generated the log
            data: Additional data to include in log
            
        Returns:
            ExecutionLog object
        """
        return ExecutionLog(
            id=f"log_{uuid.uuid4().hex[:16]}",
            timestamp=datetime.now().isoformat(),
            level=level,
            message=message,
            nodeId=node_id,
            data=data
        )
    
    def log_info(self, message: str, context: Optional[NodeExecutionContext] = None):
        """Log info message"""
        self.logger.info(f"[{context.nodeId if context else 'unknown'}] {message}")
    
    def log_warning(self, message: str, context: Optional[NodeExecutionContext] = None):
        """Log warning message"""
        self.logger.warning(f"[{context.nodeId if context else 'unknown'}] {message}")
    
    def log_error(self, message: str, context: Optional[NodeExecutionContext] = None):
        """Log error message"""
        self.logger.error(f"[{context.nodeId if context else 'unknown'}] {message}")
    
    def log_success(self, message: str, context: Optional[NodeExecutionContext] = None):
        """Log success message"""
        self.logger.info(f"[{context.nodeId if context else 'unknown'}] ✓ {message}")
    
    def get_input(
        self,
        context: NodeExecutionContext,
        key: str = "default",
        default: Any = None
    ) -> Any:
        """
        Get input value from context
        
        Args:
            context: Execution context
            key: Input key (default: "default")
            default: Default value if input not found
            
        Returns:
            Input value or default
        """
        return context.inputs.get(key, default)
    
    def get_config(
        self,
        context: NodeExecutionContext,
        key: str,
        default: Any = None
    ) -> Any:
        """
        Get configuration value
        
        Args:
            context: Execution context
            key: Config key
            default: Default value if config not found
            
        Returns:
            Config value or default
        """
        return context.config.get(key, default)
    
    def validate_required_config(
        self,
        context: NodeExecutionContext,
        *keys: str
    ) -> Optional[str]:
        """
        Validate that required config keys are present
        
        Args:
            context: Execution context
            *keys: Required config keys
            
        Returns:
            Error message if validation fails, None otherwise
        """
        missing = []
        for key in keys:
            if key not in context.config or context.config[key] is None:
                missing.append(key)
        
        if missing:
            return f"Missing required configuration: {', '.join(missing)}"
        
        return None
    
    def validate_required_inputs(
        self,
        context: NodeExecutionContext,
        *keys: str
    ) -> Optional[str]:
        """
        Validate that required input keys are present
        
        Args:
            context: Execution context
            *keys: Required input keys
            
        Returns:
            Error message if validation fails, None otherwise
        """
        missing = []
        for key in keys:
            if key not in context.inputs or context.inputs[key] is None:
                missing.append(key)
        
        if missing:
            return f"Missing required inputs: {', '.join(missing)}"
        
        return None
    
    async def safe_execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """
        Execute with error handling wrapper
        
        Args:
            context: Execution context
            
        Returns:
            ExecutionResult
        """
        try:
            self.log_info(f"Executing {context.nodeType} node", context)
            result = await self.execute(context)
            
            if result.success:
                self.log_success(f"Node executed successfully", context)
            else:
                self.log_error(f"Node execution failed: {result.error}", context)
            
            return result
            
        except Exception as e:
            error_msg = f"Unexpected error in {context.nodeType} executor: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(success=False, error=error_msg)

