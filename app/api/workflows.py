"""
FastAPI routes for workflow execution
"""

from fastapi import APIRouter, HTTPException, status, Request
from typing import List, Any
from datetime import datetime
import logging

from app.models.workflow import Workflow, Node, Edge, NodePosition, NodeData
from app.models.execution import (
    ExecutionState,
    ExecutionStatusResponse,
    ExecutionLogsResponse,
    ExecutionStartResponse
)
from app.services.workflow_engine import workflow_engine
from app.services.background_scheduler import get_background_scheduler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


def _convert_timestamp(value: Any) -> str:
    """Convert Firestore timestamp or other formats to ISO string"""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        # Handle Firestore timestamp format
        if "seconds" in value:
            timestamp = datetime.fromtimestamp(value["seconds"])
            return timestamp.isoformat()
    # Try to convert to string if it's a datetime-like object
    try:
        return str(value)
    except:
        return None


@router.post("/execute", response_model=ExecutionStartResponse)
async def execute_workflow(request: Request):
    """
    Execute a workflow
    
    Args:
        request: Raw request with workflow definition in body
        
    Returns:
        Execution ID and status
    """
    try:
        # Parse JSON body manually (no Pydantic validation)
        body = await request.json()
        
        # Extract workflow data
        workflow_data = body.get("workflow", body)  # Support both nested and flat structure
        user_id = body.get("userId", "default_user")
        portfolio_id = body.get("portfolioId", "default_portfolio")
        trading_mode = body.get("tradingMode", "paper")  # Default to paper trading
        broker_kwargs = body.get("brokerConfig", {})  # Additional broker config (e.g., access_token for Kite)
        
        # Validate basic structure
        if not workflow_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Workflow data is required"
            )
        
        # Validate nodes exist
        nodes = workflow_data.get("nodes", [])
        if not nodes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Workflow must have at least one node"
            )
        
        # Convert to Workflow model using model_construct to bypass validation
        # This allows accepting any data structure without strict Pydantic validation
        try:
            # Try normal validation first (for well-formed requests)
            workflow = Workflow.model_validate(workflow_data)
        except Exception as e:
            # If validation fails, use model_construct to bypass validation
            logger.warning(f"Workflow validation warning: {str(e)}, using model_construct to bypass validation")
            
            # Convert nested models manually when using model_construct
            # Convert nodes
            converted_nodes = []
            for node_data in workflow_data.get("nodes", []):
                if isinstance(node_data, dict):
                    # Convert node data
                    node_data_obj = node_data.get("data", {})
                    if isinstance(node_data_obj, dict):
                        node_data_obj = NodeData.model_construct(**node_data_obj)
                    
                    # Convert position
                    position_data = node_data.get("position", {})
                    if isinstance(position_data, dict):
                        position_data = NodePosition.model_construct(**position_data)
                    
                    # Create node
                    converted_nodes.append(Node.model_construct(
                        id=node_data.get("id", ""),
                        type=node_data.get("type", ""),
                        position=position_data,
                        data=node_data_obj
                    ))
                else:
                    converted_nodes.append(node_data)
            
            # Convert edges
            converted_edges = []
            for edge_data in workflow_data.get("edges", []):
                if isinstance(edge_data, dict):
                    converted_edges.append(Edge.model_construct(**edge_data))
                else:
                    converted_edges.append(edge_data)
            
            # Create workflow with converted nodes and edges
            workflow = Workflow.model_construct(
                id=workflow_data.get("id", "unknown"),
                name=workflow_data.get("name", "Unnamed Workflow"),
                description=workflow_data.get("description", ""),
                nodes=converted_nodes,
                edges=converted_edges,
                status=workflow_data.get("status", "draft"),
                createdAt=_convert_timestamp(workflow_data.get("createdAt")),
                updatedAt=_convert_timestamp(workflow_data.get("updatedAt")),
                userId=workflow_data.get("userId"),
                category=workflow_data.get("category"),
                tags=workflow_data.get("tags", []),
                executionCount=workflow_data.get("executionCount", 0),
                successCount=workflow_data.get("successCount", 0),
                errorCount=workflow_data.get("errorCount", 0),
                totalPnL=workflow_data.get("totalPnL", 0.0),
                isPublic=workflow_data.get("isPublic", False)
            )
        
        logger.info(f"Received workflow execution request: {workflow.name}")
        
        # Execute workflow
        execution_id = await workflow_engine.execute_workflow(
            workflow=workflow,
            user_id=user_id,
            portfolio_id=portfolio_id,
            trading_mode=trading_mode,
            **broker_kwargs
        )
        
        logger.info(f"Workflow execution started: {execution_id}")
        
        return ExecutionStartResponse(
            executionId=execution_id,
            status="started",
            message=f"Workflow execution started successfully"
        )
        
    except ValueError as e:
        logger.error(f"Invalid workflow: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error starting workflow execution: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start workflow execution: {str(e)}"
        )


@router.get("/executions/{execution_id}", response_model=ExecutionStatusResponse)
async def get_execution_status(execution_id: str):
    """
    Get the status of a workflow execution
    
    Args:
        execution_id: Execution ID
        
    Returns:
        Execution state with status, progress, and logs
    """
    try:
        execution = workflow_engine.get_execution(execution_id)
        
        if not execution:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Execution not found: {execution_id}"
            )
        
        return ExecutionStatusResponse(execution=execution)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting execution status: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get execution status: {str(e)}"
        )


@router.get("/executions/{execution_id}/logs", response_model=ExecutionLogsResponse)
async def get_execution_logs(execution_id: str):
    """
    Get detailed logs for a workflow execution
    
    Args:
        execution_id: Execution ID
        
    Returns:
        Execution logs
    """
    try:
        execution = workflow_engine.get_execution(execution_id)
        
        if not execution:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Execution not found: {execution_id}"
            )
        
        return ExecutionLogsResponse(
            executionId=execution_id,
            logs=execution.logs
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting execution logs: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get execution logs: {str(e)}"
        )


@router.post("/executions/{execution_id}/stop")
async def stop_execution(execution_id: str):
    """
    Stop a running workflow execution
    
    Args:
        execution_id: Execution ID
        
    Returns:
        Success message
    """
    try:
        stopped = await workflow_engine.stop_execution(execution_id)
        
        if not stopped:
            execution = workflow_engine.get_execution(execution_id)
            if not execution:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Execution not found: {execution_id}"
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Execution is not running (status: {execution.status})"
                )
        
        logger.info(f"Execution stopped: {execution_id}")
        
        return {
            "success": True,
            "message": f"Execution stopped successfully",
            "executionId": execution_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping execution: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop execution: {str(e)}"
        )


@router.get("/executions", response_model=List[ExecutionState])
async def list_executions():
    """
    List all workflow executions
    
    Returns:
        List of execution states
    """
    try:
        executions = workflow_engine.list_executions()
        return executions
        
    except Exception as e:
        logger.error(f"Error listing executions: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list executions: {str(e)}"
        )


@router.post("/schedule")
async def schedule_workflow(request: Request):
    """
    Schedule a workflow for background execution with condition checking
    
    Args:
        request: Request with workflow and schedule configuration
        
    Returns:
        Schedule ID and status
    """
    try:
        body = await request.json()
        workflow_data = body.get("workflow", body)
        user_id = body.get("userId", "default_user")
        portfolio_id = body.get("portfolioId", "default_portfolio")
        interval_seconds = body.get("intervalSeconds", 5.0)
        check_conditions_only = body.get("checkConditionsOnly", True)
        
        if not workflow_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Workflow data is required"
            )
        
        # Convert to Workflow model (similar to execute endpoint)
        try:
            workflow = Workflow.model_validate(workflow_data)
        except Exception as e:
            logger.warning(f"Workflow validation warning: {str(e)}, using model_construct")
            # Use same conversion logic as execute endpoint
            converted_nodes = []
            for node_data in workflow_data.get("nodes", []):
                if isinstance(node_data, dict):
                    node_data_obj = node_data.get("data", {})
                    if isinstance(node_data_obj, dict):
                        node_data_obj = NodeData.model_construct(**node_data_obj)
                    position_data = node_data.get("position", {})
                    if isinstance(position_data, dict):
                        position_data = NodePosition.model_construct(**position_data)
                    converted_nodes.append(Node.model_construct(
                        id=node_data.get("id", ""),
                        type=node_data.get("type", ""),
                        position=position_data,
                        data=node_data_obj
                    ))
            
            converted_edges = []
            for edge_data in workflow_data.get("edges", []):
                if isinstance(edge_data, dict):
                    converted_edges.append(Edge.model_construct(**edge_data))
            
            workflow = Workflow.model_construct(
                id=workflow_data.get("id", "unknown"),
                name=workflow_data.get("name", "Unnamed Workflow"),
                description=workflow_data.get("description", ""),
                nodes=converted_nodes,
                edges=converted_edges,
                status=workflow_data.get("status", "draft"),
                createdAt=_convert_timestamp(workflow_data.get("createdAt")),
                updatedAt=_convert_timestamp(workflow_data.get("updatedAt")),
                userId=workflow_data.get("userId"),
                category=workflow_data.get("category"),
                tags=workflow_data.get("tags", []),
                executionCount=workflow_data.get("executionCount", 0),
                successCount=workflow_data.get("successCount", 0),
                errorCount=workflow_data.get("errorCount", 0),
                totalPnL=workflow_data.get("totalPnL", 0.0),
                isPublic=workflow_data.get("isPublic", False)
            )
        
        scheduler = get_background_scheduler(workflow_engine)
        schedule_id = await scheduler.schedule_workflow(
            workflow=workflow,
            user_id=user_id,
            portfolio_id=portfolio_id,
            interval_seconds=float(interval_seconds),
            check_conditions_only=bool(check_conditions_only)
        )
        
        logger.info(f"Scheduled workflow for background execution: {workflow.name}")
        
        return {
            "scheduleId": schedule_id,
            "status": "scheduled",
            "message": f"Workflow scheduled for background execution every {interval_seconds}s",
            "workflowId": workflow.id
        }
        
    except Exception as e:
        logger.error(f"Error scheduling workflow: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to schedule workflow: {str(e)}"
        )


@router.post("/schedule/{workflow_id}/stop")
async def stop_scheduled_workflow(workflow_id: str):
    """
    Stop a scheduled workflow
    
    Args:
        workflow_id: Workflow ID to stop
        
    Returns:
        Success message
    """
    try:
        scheduler = get_background_scheduler(workflow_engine)
        stopped = await scheduler.stop_workflow(workflow_id)
        
        if not stopped:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Scheduled workflow not found: {workflow_id}"
            )
        
        return {
            "success": True,
            "message": f"Background execution stopped for workflow {workflow_id}",
            "workflowId": workflow_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping scheduled workflow: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop scheduled workflow: {str(e)}"
        )


@router.get("/schedule/{workflow_id}")
async def get_schedule_info(workflow_id: str):
    """
    Get schedule information for a workflow
    
    Args:
        workflow_id: Workflow ID
        
    Returns:
        Schedule information
    """
    try:
        scheduler = get_background_scheduler(workflow_engine)
        schedule_info = scheduler.get_schedule_info(workflow_id)
        
        if not schedule_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Scheduled workflow not found: {workflow_id}"
            )
        
        return schedule_info
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting schedule info: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get schedule info: {str(e)}"
        )


@router.get("/schedules")
async def list_scheduled_workflows():
    """
    List all scheduled workflows
    
    Returns:
        List of scheduled workflows
    """
    try:
        scheduler = get_background_scheduler(workflow_engine)
        schedules = scheduler.list_scheduled_workflows()
        return schedules
        
    except Exception as e:
        logger.error(f"Error listing scheduled workflows: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list scheduled workflows: {str(e)}"
        )


@router.get("/health")
async def health_check():
    """
    Health check endpoint
    
    Returns:
        Service health status
    """
    scheduler = get_background_scheduler(workflow_engine)
    scheduled_count = len(scheduler.list_scheduled_workflows())
    
    return {
        "status": "healthy",
        "service": "workflow-execution-backend",
        "version": "1.0.0",
        "executors": len(workflow_engine.node_executors),
        "active_executions": len([e for e in workflow_engine.executions.values() if e.status == "running"]),
        "scheduled_workflows": scheduled_count
    }

