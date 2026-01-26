"""
Node executors for utility and control flow nodes
"""

import asyncio
from typing import Any, Dict
import logging
from datetime import datetime

from .base import NodeExecutor
from app.models.execution import ExecutionResult, NodeExecutionContext

logger = logging.getLogger(__name__)


class DelayExecutor(NodeExecutor):
    """Executor for delay-timer node - adds delays between workflow steps"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Execute delay/wait"""
        
        duration = self.get_config(context, "duration", 1)
        
        try:
            duration = int(duration)
            if duration < 0:
                return self.create_result(False, None, "Duration must be non-negative")
            
            self.log_info(f"Waiting for {duration} seconds...", context)
            
            # Async sleep
            await asyncio.sleep(duration)
            
            self.log_success(f"Wait completed ({duration}s)", context)
            
            return self.create_result(True, {
                "waited": duration,
                "timestamp": datetime.now().isoformat()
            })
            
        except Exception as e:
            error_msg = f"Error during delay: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)


class LoggingExecutor(NodeExecutor):
    """Executor for logging node - logs messages during workflow execution"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Execute logging action"""
        
        message = self.get_config(context, "message", "Log entry")
        log_level = self.get_config(context, "level", "info")
        include_input = self.get_config(context, "includeInput", True)
        
        # Get input data to log
        input_data = self.get_input(context, "default") if include_input else None
        
        self.log_info(f"Logging: {message}", context)
        
        try:
            # Create log entry with data
            log_entry = {
                "message": message,
                "level": log_level,
                "timestamp": datetime.now().isoformat(),
                "node_id": context.nodeId
            }
            
            if input_data is not None:
                log_entry["data"] = input_data
            
            # Log based on level
            if log_level == "error":
                self.log_error(message, context)
            elif log_level == "warning":
                self.log_warning(message, context)
            elif log_level == "success":
                self.log_success(message, context)
            else:
                self.log_info(message, context)
            
            return self.create_result(True, log_entry)
            
        except Exception as e:
            error_msg = f"Error logging: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)


class AlertExecutor(NodeExecutor):
    """Executor for alert node - sends notifications/alerts"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Execute alert/notification"""
        
        # Validate required config
        error = self.validate_required_config(context, "message")
        if error:
            return self.create_result(False, None, error)
        
        alert_type = self.get_config(context, "alertType", "email")
        message = self.get_config(context, "message")
        recipients = self.get_config(context, "recipients", [])
        subject = self.get_config(context, "subject", "Workflow Alert")
        
        # Get input data to include in alert
        input_data = self.get_input(context, "default")
        
        self.log_info(f"Sending {alert_type} alert: {message}", context)
        
        try:
            # Create alert record
            alert_data = {
                "alert_id": f"alert_{datetime.now().timestamp()}",
                "type": alert_type,
                "subject": subject,
                "message": message,
                "recipients": recipients if isinstance(recipients, list) else [recipients],
                "timestamp": datetime.now().isoformat(),
                "status": "sent"
            }
            
            if input_data:
                alert_data["data"] = input_data
            
            # In a real implementation, this would send actual emails/SMS/etc.
            # For now, we just log the alert
            self.log_success(
                f"Alert sent: {alert_type} to {len(alert_data['recipients'])} recipient(s)",
                context
            )
            
            # Log the alert content for debugging
            logger.info(f"Alert content: {subject} - {message}")
            
            return self.create_result(True, alert_data)
            
        except Exception as e:
            error_msg = f"Error sending alert: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)


class StartEndExecutor(NodeExecutor):
    """Executor for start-end node - marks workflow start/end points"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Execute start/end marker"""
        
        node_mode = self.get_config(context, "mode", "start")
        
        try:
            if node_mode == "start":
                self.log_info("Workflow execution started", context)
            else:
                self.log_info("Workflow execution ended", context)
            
            return self.create_result(True, {
                "mode": node_mode,
                "timestamp": datetime.now().isoformat()
            })
            
        except Exception as e:
            error_msg = f"Error in start/end node: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)


class LoopExecutor(NodeExecutor):
    """Executor for loop node - repeats execution"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Execute loop iteration"""
        
        loop_type = self.get_config(context, "loopType", "count")
        max_iterations = self.get_config(context, "maxIterations", 10)
        delay_between = self.get_config(context, "delayBetween", 0)
        
        try:
            # Get current iteration from input or start at 0
            current_iteration = self.get_input(context, "iteration", 0)
            if isinstance(current_iteration, dict):
                current_iteration = current_iteration.get("iteration", 0)
            
            current_iteration = int(current_iteration) + 1
            
            # Check if loop should continue
            should_continue = current_iteration < max_iterations
            
            self.log_info(
                f"Loop iteration {current_iteration}/{max_iterations}",
                context
            )
            
            if delay_between > 0 and should_continue:
                await asyncio.sleep(delay_between)
            
            return self.create_result(True, {
                "iteration": current_iteration,
                "max_iterations": max_iterations,
                "should_continue": should_continue,
                "completed": not should_continue
            })
            
        except Exception as e:
            error_msg = f"Error in loop node: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)


class ErrorHandlingExecutor(NodeExecutor):
    """Executor for error-handling node - handles and recovers from errors"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Execute error handling logic"""
        
        action = self.get_config(context, "action", "continue")
        fallback_value = self.get_config(context, "fallbackValue")
        
        try:
            # Get input data which may contain error
            input_data = self.get_input(context, "default")
            
            has_error = False
            error_message = None
            
            if isinstance(input_data, dict):
                if "error" in input_data:
                    has_error = True
                    error_message = input_data["error"]
                elif "success" in input_data and not input_data["success"]:
                    has_error = True
                    error_message = input_data.get("error", "Unknown error")
            
            if has_error:
                self.log_warning(f"Error detected: {error_message}", context)
                
                if action == "continue":
                    self.log_info("Continuing with fallback value", context)
                    return self.create_result(True, {
                        "recovered": True,
                        "value": fallback_value,
                        "original_error": error_message
                    })
                
                elif action == "retry":
                    self.log_info("Retry would be triggered", context)
                    return self.create_result(True, {
                        "retry": True,
                        "original_error": error_message
                    })
                
                elif action == "stop":
                    return self.create_result(False, None, f"Workflow stopped due to error: {error_message}")
            
            else:
                # No error, pass through input
                self.log_info("No error detected, passing through", context)
                return self.create_result(True, input_data)
            
        except Exception as e:
            error_msg = f"Error in error handling node: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)


class ParallelExecutionExecutor(NodeExecutor):
    """Executor for parallel-execution node - runs multiple branches in parallel"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Execute parallel coordination"""
        
        try:
            # Get all inputs (from different branches)
            all_inputs = []
            for key, value in context.inputs.items():
                all_inputs.append(value)
            
            self.log_info(
                f"Parallel execution node received {len(all_inputs)} inputs",
                context
            )
            
            # Combine results from parallel branches
            combined_result = {
                "parallel_results": all_inputs,
                "branch_count": len(all_inputs),
                "timestamp": datetime.now().isoformat()
            }
            
            self.log_success(
                f"Parallel branches combined: {len(all_inputs)} branches",
                context
            )
            
            return self.create_result(True, combined_result)
            
        except Exception as e:
            error_msg = f"Error in parallel execution node: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)

