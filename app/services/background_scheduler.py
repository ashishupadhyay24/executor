"""
Background workflow scheduler service
Handles continuous execution of workflows with condition checking
"""

import asyncio
import logging
from typing import Dict, Optional, Set
from datetime import datetime
import uuid

from app.models.workflow import Workflow
from app.models.execution import ExecutionState, ExecutionStatus
from app.services.workflow_engine import WorkflowEngine

logger = logging.getLogger(__name__)


class BackgroundScheduler:
    """
    Schedules and manages background workflow executions
    
    Features:
    - Continuous execution of workflows
    - Condition-first evaluation
    - Periodic checking of conditions
    - Automatic action execution when conditions are met
    """
    
    def __init__(self, workflow_engine: WorkflowEngine):
        self.workflow_engine = workflow_engine
        self.scheduled_workflows: Dict[str, Dict] = {}  # workflow_id -> schedule info
        self.running_tasks: Dict[str, asyncio.Task] = {}  # workflow_id -> task
        self.execution_intervals: Dict[str, float] = {}  # workflow_id -> interval in seconds
        
    async def schedule_workflow(
        self,
        workflow: Workflow,
        user_id: str = "default_user",
        portfolio_id: str = "default_portfolio",
        interval_seconds: float = 5.0,
        check_conditions_only: bool = True
    ) -> str:
        """
        Schedule a workflow for background execution
        
        Args:
            workflow: Workflow to schedule
            user_id: User ID
            portfolio_id: Portfolio ID
            interval_seconds: How often to check conditions (default: 5 seconds)
            check_conditions_only: If True, only check conditions and execute actions when met
            
        Returns:
            Schedule ID
        """
        schedule_id = f"schedule_{uuid.uuid4().hex[:16]}"
        
        schedule_info = {
            "id": schedule_id,
            "workflow": workflow,
            "userId": user_id,
            "portfolioId": portfolio_id,
            "intervalSeconds": interval_seconds,
            "checkConditionsOnly": check_conditions_only,
            "status": "running",
            "createdAt": datetime.now().isoformat(),
            "lastCheck": None,
            "conditionMetCount": 0,
            "actionExecutedCount": 0
        }
        
        self.scheduled_workflows[workflow.id] = schedule_info
        self.execution_intervals[workflow.id] = interval_seconds
        
        # Start background task
        task = asyncio.create_task(
            self._run_scheduled_workflow(workflow.id, check_conditions_only)
        )
        self.running_tasks[workflow.id] = task
        
        logger.info(
            f"Scheduled workflow {workflow.name} (ID: {workflow.id}) "
            f"for background execution every {interval_seconds}s"
        )
        
        return schedule_id
    
    async def _run_scheduled_workflow(
        self,
        workflow_id: str,
        check_conditions_only: bool
    ):
        """Run a scheduled workflow continuously"""
        
        schedule_info = self.scheduled_workflows.get(workflow_id)
        if not schedule_info:
            logger.error(f"Schedule info not found for workflow {workflow_id}")
            return
        
        workflow = schedule_info["workflow"]
        interval = schedule_info["intervalSeconds"]
        
        logger.info(f"Starting background execution for workflow {workflow.name}")
        
        try:
            while schedule_info["status"] == "running":
                try:
                    # Execute workflow with condition-first logic
                    if check_conditions_only:
                        await self._execute_conditional_workflow(
                            workflow,
                            schedule_info["userId"],
                            schedule_info["portfolioId"],
                            schedule_info
                        )
                    else:
                        # Full workflow execution
                        await self.workflow_engine.execute_workflow(
                            workflow=workflow,
                            user_id=schedule_info["userId"],
                            portfolio_id=schedule_info["portfolioId"]
                        )
                    
                    schedule_info["lastCheck"] = datetime.now().isoformat()
                    
                except Exception as e:
                    logger.error(f"Error in background execution of {workflow.name}: {str(e)}")
                
                # Wait for next interval
                await asyncio.sleep(interval)
                
        except asyncio.CancelledError:
            logger.info(f"Background execution cancelled for workflow {workflow_id}")
        except Exception as e:
            logger.error(f"Fatal error in background execution: {str(e)}")
        finally:
            # Cleanup
            if workflow_id in self.running_tasks:
                del self.running_tasks[workflow_id]
            if workflow_id in self.scheduled_workflows:
                schedule_info["status"] = "stopped"
    
    async def _execute_conditional_workflow(
        self,
        workflow: Workflow,
        user_id: str,
        portfolio_id: str,
        schedule_info: Dict
    ):
        """
        Execute workflow with condition-first logic:
        1. Check all condition nodes
        2. Only execute action nodes if conditions are met
        """
        
        # Separate nodes into conditions and actions
        condition_nodes = []
        action_nodes = []
        data_nodes = []
        
        for node in workflow.nodes:
            logical_type = self.workflow_engine._get_logical_node_type(node)
            
            # Identify node types
            if logical_type in [
                'comparison', 'boolean-logic', 'threshold', 'rsi-condition',
                'ma-condition', 'technical-indicator'
            ]:
                condition_nodes.append(node)
            elif logical_type in [
                'buy-order', 'sell-order', 'order-placement', 'order-management',
                'alert', 'logging'
            ]:
                action_nodes.append(node)
            elif logical_type in [
                'market-data', 'historical-data', 'technical-indicator'
            ]:
                data_nodes.append(node)
        
        # Create a minimal execution state for logging
        from app.models.execution import ExecutionState, ExecutionStatus, LogLevel
        execution = ExecutionState(
            id=f"bg_{uuid.uuid4().hex[:16]}",
            workflowId=workflow.id,
            status=ExecutionStatus.RUNNING,
            startTime=datetime.now().isoformat(),
            progress=0.0,
            logs=[],
            results={},
            userId=user_id,
            portfolioId=portfolio_id
        )
        
        # Step 1: Execute data nodes first (they provide inputs)
        node_results = {}
        
        for node in data_nodes:
            try:
                result = await self.workflow_engine._execute_node(
                    execution=execution,
                    node=node,
                    node_results=node_results,
                    edges=workflow.edges,
                    user_id=user_id,
                    portfolio_id=portfolio_id
                )
                if result.success:
                    node_results[node.id] = result.data
            except Exception as e:
                logger.warning(f"Error executing data node {node.id}: {str(e)}")
        
        # Step 2: Check all conditions
        all_conditions_met = True
        condition_results = {}
        
        for node in condition_nodes:
            try:
                result = await self.workflow_engine._execute_node(
                    execution=execution,
                    node=node,
                    node_results=node_results,
                    edges=workflow.edges,
                    user_id=user_id,
                    portfolio_id=portfolio_id
                )
                
                condition_results[node.id] = result
                
                if result.success:
                    # Check if condition result is True
                    condition_met = result.data if isinstance(result.data, bool) else bool(result.data)
                    if not condition_met:
                        all_conditions_met = False
                        logger.debug(f"Condition {node.id} not met: {result.data}")
                else:
                    all_conditions_met = False
                    logger.warning(f"Condition {node.id} failed: {result.error}")
                    
            except Exception as e:
                logger.warning(f"Error checking condition {node.id}: {str(e)}")
                all_conditions_met = False
        
        schedule_info["lastCheck"] = datetime.now().isoformat()
        
        # Step 3: Only execute actions if all conditions are met
        if all_conditions_met:
            schedule_info["conditionMetCount"] = schedule_info.get("conditionMetCount", 0) + 1
            logger.info(f"All conditions met for workflow {workflow.name}, executing actions")
            
            # Merge condition results into node_results for action nodes
            for node_id, result in condition_results.items():
                if result.success:
                    node_results[node_id] = result.data
            
            # Execute action nodes
            for node in action_nodes:
                try:
                    result = await self.workflow_engine._execute_node(
                        execution=execution,
                        node=node,
                        node_results=node_results,
                        edges=workflow.edges,
                        user_id=user_id,
                        portfolio_id=portfolio_id
                    )
                    
                    if result.success:
                        schedule_info["actionExecutedCount"] = schedule_info.get("actionExecutedCount", 0) + 1
                        logger.info(f"Action {node.id} executed successfully")
                    else:
                        logger.error(f"Action {node.id} failed: {result.error}")
                        
                except Exception as e:
                    logger.error(f"Error executing action {node.id}: {str(e)}")
        else:
            logger.debug(f"Conditions not met for workflow {workflow.name}, skipping actions")
    
    async def stop_workflow(self, workflow_id: str) -> bool:
        """Stop a scheduled workflow"""
        
        if workflow_id not in self.scheduled_workflows:
            return False
        
        schedule_info = self.scheduled_workflows[workflow_id]
        schedule_info["status"] = "stopped"
        
        # Cancel running task
        if workflow_id in self.running_tasks:
            task = self.running_tasks[workflow_id]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        logger.info(f"Stopped background execution for workflow {workflow_id}")
        return True
    
    async def stop_all(self):
        """Stop all scheduled workflows"""
        workflow_ids = list(self.scheduled_workflows.keys())
        for workflow_id in workflow_ids:
            await self.stop_workflow(workflow_id)
    
    def get_schedule_info(self, workflow_id: str) -> Optional[Dict]:
        """Get schedule information for a workflow"""
        return self.scheduled_workflows.get(workflow_id)
    
    def list_scheduled_workflows(self) -> list:
        """List all scheduled workflows"""
        return list(self.scheduled_workflows.values())
    
    def is_scheduled(self, workflow_id: str) -> bool:
        """Check if a workflow is scheduled"""
        return workflow_id in self.scheduled_workflows


# Global scheduler instance
background_scheduler: Optional[BackgroundScheduler] = None

def get_background_scheduler(workflow_engine: WorkflowEngine) -> BackgroundScheduler:
    """Get or create the global background scheduler"""
    global background_scheduler
    if background_scheduler is None:
        background_scheduler = BackgroundScheduler(workflow_engine)
    return background_scheduler

