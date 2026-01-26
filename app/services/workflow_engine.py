"""
Main workflow execution engine
"""

from typing import Dict, List, Set, Optional, Any
from datetime import datetime
import logging
import uuid
import asyncio

from app.models.workflow import Workflow, Node, Edge
from app.models.execution import (
    ExecutionState,
    ExecutionStatus,
    ExecutionLog,
    ExecutionResult,
    NodeExecutionContext,
    LogLevel
)
from app.storage.db import get_db, init_db
from app.storage.repositories import (
    ExecutionRepository,
    OrderRepository,
    PositionRepository,
    BrokerSessionRepository
)
from app.services.node_executors import (
    NodeExecutor,
    MarketDataExecutor,
    HistoricalDataExecutor,
    TechnicalIndicatorExecutor,
    FundamentalDataExecutor,
    ComparisonExecutor,
    BooleanLogicExecutor,
    ThresholdExecutor,
    PatternDetectionExecutor,
    CustomScriptExecutor,
    RSIConditionExecutor,
    MovingAverageConditionExecutor,
    PriceTriggerExecutor,
    BuyOrderExecutor,
    SellOrderExecutor,
    StopLossExecutor,
    OrderManagementExecutor,
    DelayExecutor,
    LoggingExecutor,
    AlertExecutor,
    StartEndExecutor,
    LoopExecutor,
    ErrorHandlingExecutor,
    ParallelExecutionExecutor,
    SignalGeneratorExecutor,
    EntryConditionExecutor,
    ExitConditionExecutor,
    StopTakeProfitExecutor,
    TrailingStopExecutor,
    PositionManagementExecutor,
    PortfolioAllocationExecutor,
    MaxLossDrawdownExecutor,
    PositionSizingExecutor,
    LeverageControlExecutor,
    DailyLimitExecutor,
    DashboardExecutor,
    ReportExecutor,
    TimeTriggerExecutor,
)

logger = logging.getLogger(__name__)

# Node types that act as "gates" - when they return false, the workflow loops back to start
GATE_NODE_TYPES = {
    'comparison',
    'threshold',
    'boolean-logic',
    'entry-condition',
    'exit-condition',
    'rsi-condition',
    'ma-condition',
    'price-trigger',
    'time-trigger',
    'pattern-detection',
    'custom-script',
}

# Default execution settings
DEFAULT_MAX_ITERATIONS = 500
DEFAULT_ITERATION_DELAY_SECONDS = 1.0


class WorkflowEngine:
    """
    Main engine for executing workflows
    
    Handles:
    - Topological sorting of nodes
    - Node execution orchestration
    - State management
    - Error handling
    """
    
    def __init__(self):
        self.executions: Dict[str, ExecutionState] = {}
        self.node_executors: Dict[str, NodeExecutor] = {}
        self._initialize_executors()
    
    def _initialize_executors(self):
        """Initialize all node type executors"""
        
        # Data & Input Nodes
        self.node_executors['market-data'] = MarketDataExecutor()
        self.node_executors['historical-data'] = HistoricalDataExecutor()
        self.node_executors['technical-indicator'] = TechnicalIndicatorExecutor()
        self.node_executors['fundamental-data'] = FundamentalDataExecutor()
        
        # Condition / Logic Nodes
        self.node_executors['comparison'] = ComparisonExecutor()
        self.node_executors['boolean-logic'] = BooleanLogicExecutor()
        self.node_executors['threshold'] = ThresholdExecutor()
        self.node_executors['pattern-detection'] = PatternDetectionExecutor()
        self.node_executors['custom-script'] = CustomScriptExecutor()
        
        # Technical Nodes
        self.node_executors['rsi-condition'] = RSIConditionExecutor()
        self.node_executors['ma-condition'] = MovingAverageConditionExecutor()
        self.node_executors['price-trigger'] = PriceTriggerExecutor()
        
        # Strategy Nodes
        self.node_executors['signal-generator'] = SignalGeneratorExecutor()
        self.node_executors['entry-condition'] = EntryConditionExecutor()
        self.node_executors['exit-condition'] = ExitConditionExecutor()
        self.node_executors['stop-take-profit'] = StopTakeProfitExecutor()
        self.node_executors['trailing-stop'] = TrailingStopExecutor()
        
        # Trading Nodes
        self.node_executors['buy-order'] = BuyOrderExecutor()
        self.node_executors['sell-order'] = SellOrderExecutor()
        self.node_executors['stop-loss'] = StopLossExecutor()
        self.node_executors['order-placement'] = BuyOrderExecutor()  # Alias
        self.node_executors['order-management'] = OrderManagementExecutor()
        
        # Order & Portfolio Nodes
        self.node_executors['position-management'] = PositionManagementExecutor()
        self.node_executors['portfolio-allocation'] = PortfolioAllocationExecutor()
        
        # Risk Management Nodes
        self.node_executors['max-loss-drawdown'] = MaxLossDrawdownExecutor()
        self.node_executors['position-sizing'] = PositionSizingExecutor()
        self.node_executors['leverage-control'] = LeverageControlExecutor()
        self.node_executors['daily-limits'] = DailyLimitExecutor()
        
        # Utility / Control Flow Nodes
        self.node_executors['delay-timer'] = DelayExecutor()
        self.node_executors['delay'] = DelayExecutor()  # Alias
        self.node_executors['logging'] = LoggingExecutor()
        self.node_executors['alert'] = AlertExecutor()
        self.node_executors['start-end'] = StartEndExecutor()
        self.node_executors['loop'] = LoopExecutor()
        self.node_executors['error-handling'] = ErrorHandlingExecutor()
        self.node_executors['parallel-execution'] = ParallelExecutionExecutor()
        
        # Output & Monitoring Nodes
        self.node_executors['dashboard'] = DashboardExecutor()
        self.node_executors['report'] = ReportExecutor()
        
        # Time Trigger
        self.node_executors['time-trigger'] = TimeTriggerExecutor()
        
        logger.info(f"Initialized {len(self.node_executors)} node executors")
    
    async def execute_workflow(
        self,
        workflow: Workflow,
        user_id: str = "default_user",
        portfolio_id: str = "default_portfolio",
        trading_mode: str = "paper",
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
        iteration_delay_seconds: float = DEFAULT_ITERATION_DELAY_SECONDS,
        **broker_kwargs
    ) -> str:
        """
        Execute a workflow with iteration-based looping.
        
        When a gate condition (comparison, entry-condition, etc.) evaluates to false,
        the workflow restarts from the beginning instead of continuing to downstream nodes.
        
        Args:
            workflow: Workflow to execute
            user_id: User ID for the execution
            portfolio_id: Portfolio ID for trading operations
            trading_mode: Trading mode ("paper" or "kite")
            max_iterations: Maximum number of loop iterations (prevents infinite loops)
            iteration_delay_seconds: Delay between loop iterations
            **broker_kwargs: Additional broker configuration (e.g., access_token for Kite)
                If trading_mode is "kite" and access_token/api_key are missing,
                they will be loaded from the database using user_id.
            
        Returns:
            Execution ID
        """
        execution_id = f"exec_{uuid.uuid4().hex[:16]}"
        
        # For Kite mode, load stored credentials if not provided
        if trading_mode == "kite":
            if not broker_kwargs.get("access_token") or not broker_kwargs.get("api_key"):
                try:
                    db = next(get_db())
                    try:
                        broker_repo = BrokerSessionRepository(db)
                        session = broker_repo.get(user_id=user_id, broker_type="kite")
                        
                        if session:
                            if not broker_kwargs.get("access_token") and session.access_token:
                                broker_kwargs["access_token"] = session.access_token
                            if not broker_kwargs.get("api_key") and session.api_key:
                                broker_kwargs["api_key"] = session.api_key
                    finally:
                        db.close()
                except Exception as e:
                    logger.warning(f"Failed to load stored Kite credentials: {str(e)}")
        
        # Create broker service based on trading mode
        from app.services.brokers.factory import BrokerFactory
        try:
            broker = BrokerFactory.create_broker(
                trading_mode=trading_mode,
                user_id=user_id,
                portfolio_id=portfolio_id,
                **broker_kwargs
            )
        except Exception as e:
            logger.error(f"Failed to create broker: {str(e)}")
            raise ValueError(f"Failed to create broker service: {str(e)}")
        
        # Create execution state
        execution = ExecutionState(
            id=execution_id,
            workflowId=workflow.id,
            status=ExecutionStatus.RUNNING,
            startTime=datetime.now().isoformat(),
            progress=0.0,
            logs=[],
            results={},
            userId=user_id,
            portfolioId=portfolio_id
        )
        
        self.executions[execution_id] = execution
        
        # Persist execution to database
        try:
            db = next(get_db())
            exec_repo = ExecutionRepository(db)
            exec_repo.create(execution, trading_mode=trading_mode)
            db.close()
        except Exception as e:
            logger.warning(f"Failed to persist execution to database: {str(e)}")
        
        self._add_log(execution, LogLevel.INFO, f"Starting workflow execution: {workflow.name} (mode: {trading_mode})")
        
        try:
            # Validate workflow
            validation_error = self._validate_workflow(workflow)
            if validation_error:
                raise ValueError(validation_error)
            
            # Get execution order using topological sort
            execution_order = self._topological_sort(workflow.nodes, workflow.edges)
            
            if not execution_order:
                raise ValueError("Could not determine execution order (possible circular dependency)")
            
            self._add_log(
                execution,
                LogLevel.INFO,
                f"Execution order determined: {len(execution_order)} nodes (max iterations: {max_iterations})"
            )
            
            # Iteration-based execution loop
            iteration = 0
            workflow_completed = False
            
            while not workflow_completed and iteration < max_iterations:
                iteration += 1
                
                # Check if execution was stopped
                if execution.status != ExecutionStatus.RUNNING:
                    self._add_log(execution, LogLevel.INFO, "Execution stopped by user")
                    break
                
                self._add_log(
                    execution, 
                    LogLevel.INFO, 
                    f"Starting iteration {iteration}/{max_iterations}"
                )
                
                # Reset node results for this iteration
                node_results: Dict[str, Any] = {}
                gate_blocked = False
                
                for i, node in enumerate(execution_order):
                    # Check if execution was stopped mid-iteration
                    if execution.status != ExecutionStatus.RUNNING:
                        self._add_log(execution, LogLevel.INFO, "Execution stopped by user")
                        break
                    
                    # Update progress (consider iteration in progress calculation)
                    execution.currentStep = node.id
                    iteration_progress = (i / len(execution_order)) * 100
                    execution.progress = iteration_progress
                    
                    # Get logical type for persistence check
                    logical_type = self._get_logical_node_type(node)
                    
                    # Execute node
                    result = await self._execute_node(
                        execution,
                        node,
                        node_results,
                        workflow.edges,
                        user_id,
                        portfolio_id,
                        broker
                    )
                    
                    # Store result - use result.data if available, otherwise use the full result
                    if result.success and result.data is not None:
                        node_results[node.id] = result.data
                        logger.debug(f"Stored result for node {node.id}: {type(result.data).__name__}")
                        
                        # Persist orders to database if this is a trading node
                        if logical_type in ['buy-order', 'sell-order', 'order-placement'] and isinstance(result.data, dict) and result.data.get("order_id"):
                            try:
                                db = next(get_db())
                                order_repo = OrderRepository(db)

                                # Enrich payload with user/portfolio for persistence consistency
                                order_payload = dict(result.data)
                                order_payload["user_id"] = order_payload.get("user_id") or user_id
                                order_payload["portfolio_id"] = order_payload.get("portfolio_id") or portfolio_id

                                # Also update positions and attach realized PnL if order is filled
                                order_status = (order_payload.get("status") or "").lower()
                                if order_status == "filled" and order_payload.get("execution_price"):
                                    from app.api.portfolio import apply_order_to_position
                                    position_update = apply_order_to_position(
                                        db=db,
                                        user_id=user_id,
                                        portfolio_id=portfolio_id,
                                        trading_mode=trading_mode,
                                        symbol=order_payload.get("symbol", ""),
                                        side=order_payload.get("side", "BUY"),
                                        quantity=order_payload.get("quantity", 0),
                                        execution_price=order_payload.get("execution_price", 0)
                                    )
                                    if position_update:
                                        order_payload["realized_pnl"] = float(position_update.get("realized_pnl") or 0.0)
                                        order_payload["quantity_executed"] = int(position_update.get("quantity_executed") or order_payload.get("quantity") or 0)
                                        order_payload["filled_at"] = datetime.utcnow().isoformat()
                                    logger.info(f"Position updated for {order_payload.get('symbol')} after {order_payload.get('side')} order")

                                # Persist order (including realized_pnl when available)
                                order_repo.create(order_payload, execution_id, trading_mode=trading_mode)
                                
                                db.close()
                            except Exception as e:
                                logger.warning(f"Failed to persist order/position to database: {str(e)}")
                        
                        # Check if this is a gate node that returned false
                        if logical_type in GATE_NODE_TYPES:
                            if self._is_gate_result_false(result.data):
                                self._add_log(
                                    execution,
                                    LogLevel.INFO,
                                    f"Gate condition '{node.data.label or logical_type}' returned FALSE; looping to start (iteration {iteration}/{max_iterations})",
                                    node.id
                                )
                                gate_blocked = True
                                break  # Exit the node loop, will restart iteration
                    else:
                        # Even if failed, store None so we know the node executed
                        node_results[node.id] = None
                        logger.warning(f"Node {node.id} execution failed, storing None in results")
                    
                    # Handle execution failure
                    if not result.success:
                        error_msg = f"Node execution failed: {node.id} - {result.error}"
                        self._add_log(execution, LogLevel.ERROR, error_msg, node.id)
                        
                        # Check if we should stop on error
                        stop_on_error = True  # Could be configurable
                        if stop_on_error:
                            raise Exception(error_msg)
                
                # Check if we completed all nodes without being blocked by a gate
                if not gate_blocked and execution.status == ExecutionStatus.RUNNING:
                    workflow_completed = True
                    self._add_log(
                        execution,
                        LogLevel.SUCCESS,
                        f"All conditions passed; workflow iteration completed successfully on iteration {iteration}"
                    )
                elif gate_blocked and execution.status == ExecutionStatus.RUNNING:
                    # Add delay before next iteration to prevent tight loops
                    if iteration < max_iterations:
                        await asyncio.sleep(iteration_delay_seconds)
            
            # Check if we hit max iterations without completing
            if not workflow_completed and iteration >= max_iterations:
                self._add_log(
                    execution,
                    LogLevel.WARNING,
                    f"Reached maximum iterations ({max_iterations}) without all conditions passing"
                )
            
            # Execution completed successfully
            execution.status = ExecutionStatus.COMPLETED
            execution.endTime = datetime.now().isoformat()
            execution.progress = 100.0
            execution.results = node_results
            
            # Update execution in database
            try:
                db = next(get_db())
                exec_repo = ExecutionRepository(db)
                exec_repo.update(execution)
                db.close()
            except Exception as e:
                logger.warning(f"Failed to update execution in database: {str(e)}")
            
            self._add_log(execution, LogLevel.SUCCESS, f"Workflow execution completed after {iteration} iteration(s)")
            
        except Exception as e:
            # Execution failed
            execution.status = ExecutionStatus.ERROR
            execution.endTime = datetime.now().isoformat()
            execution.error = str(e)
            
            # Update execution in database
            try:
                db = next(get_db())
                exec_repo = ExecutionRepository(db)
                exec_repo.update(execution)
                db.close()
            except Exception as db_error:
                logger.warning(f"Failed to update execution in database: {str(db_error)}")
            
            self._add_log(
                execution,
                LogLevel.ERROR,
                f"Workflow execution failed: {str(e)}"
            )
            
            logger.error(f"Workflow execution failed: {str(e)}", exc_info=True)
        
        return execution_id
    
    def _is_gate_result_false(self, result_data: Any) -> bool:
        """
        Check if a gate node result indicates a 'false' condition.
        
        Gate nodes can return their result in various formats:
        - Boolean: False
        - Dict with 'result': False
        - Dict with 'conditionMet': False  
        - Dict with 'should_enter': False (entry-condition)
        - Dict with 'should_exit': False (exit-condition)
        - Dict with 'triggered': False (price-trigger, time-trigger)
        - Dict with 'detected': False (pattern-detection)
        
        Returns True if the condition is false and workflow should loop back.
        """
        if result_data is None:
            return True  # No result = treat as false
        
        if isinstance(result_data, bool):
            return not result_data
        
        if isinstance(result_data, dict):
            # Check various keys that indicate condition result
            false_indicators = [
                ('result', False),
                ('conditionMet', False),
                ('condition_met', False),
                ('should_enter', False),
                ('should_exit', False),
                ('triggered', False),
                ('detected', False),
                ('passed', False),
                ('success', False),  # But only if it's explicitly a condition result
            ]
            
            for key, false_value in false_indicators:
                if key in result_data:
                    value = result_data[key]
                    if isinstance(value, bool) and value == false_value:
                        return True
            
            # If the dict has a 'result' key that's truthy/falsy
            if 'result' in result_data:
                return not bool(result_data['result'])
        
        # Default: treat non-falsy values as true (condition passed)
        return False
    
    def _get_logical_node_type(self, node: Node) -> str:
        """
        Get the logical node type for execution.
        
        The frontend may use visual node types (like 'minimalist') for rendering,
        but the actual logical type is stored in node.data.type
        """
        # Node type aliases/mapping for compatibility
        type_aliases = {
            'trigger': 'start-end',
            'condition': 'comparison',
            'action': 'buy-order',  # Default action
            'delay': 'delay-timer',
            'notification': 'alert',
            'minimalist': None,  # Will use node.data.type
        }
        
        # If node.type is a visual type (minimalist), use node.data.type
        if node.type == 'minimalist' and node.data.type:
            return node.data.type
        
        # Check aliases
        if node.type in type_aliases:
            alias = type_aliases[node.type]
            if alias:
                return alias
            elif node.data.type:
                return node.data.type
        
        # If node.type doesn't have an executor, try node.data.type
        if node.type not in self.node_executors and node.data.type:
            return node.data.type
        
        return node.type
    
    async def _execute_node(
        self,
        execution: ExecutionState,
        node: Node,
        node_results: Dict[str, Any],
        edges: List[Edge],
        user_id: str,
        portfolio_id: str,
        broker = None
    ) -> ExecutionResult:
        """Execute a single node"""
        
        node_label = node.data.label or node.type
        self._add_log(
            execution,
            LogLevel.INFO,
            f"Executing node: {node_label}",
            node.id
        )
        
        try:
            # Get the logical node type (handle visual types like 'minimalist')
            logical_type = self._get_logical_node_type(node)
            
            # Get executor for this node type
            executor = self.node_executors.get(logical_type)
            
            if not executor:
                error_msg = f"No executor found for node type: {logical_type}"
                return ExecutionResult(success=False, error=error_msg)
            
            # Get inputs from connected nodes
            inputs = self._get_node_inputs(node.id, edges, node_results)
            
            # Log input information for debugging
            if not inputs:
                logger.warning(f"Node {node.id} ({logical_type}) has no inputs. Available node results: {list(node_results.keys())}")
                # Find incoming edges for debugging
                incoming_edges = [e for e in edges if e.target == node.id]
                if incoming_edges:
                    logger.warning(f"Node {node.id} has {len(incoming_edges)} incoming edges but no inputs found")
                    for edge in incoming_edges:
                        logger.warning(f"  Edge from {edge.source}: result exists = {edge.source in node_results}")
            
            # Create execution context
            context = NodeExecutionContext(
                nodeId=node.id,
                nodeType=logical_type,  # Use logical type instead of visual type
                config=node.data.dict(),
                inputs=inputs,
                outputs={},
                executionId=execution.id,
                workflowId=execution.workflowId,
                userId=user_id,
                portfolioId=portfolio_id
            )
            
            # Add broker to context for trading nodes
            if broker:
                context.broker = broker
            
            # Execute the node
            result = await executor.safe_execute(context)
            
            if result.success:
                self._add_log(
                    execution,
                    LogLevel.SUCCESS,
                    f"Node completed: {node_label}",
                    node.id,
                    result.data
                )
            else:
                self._add_log(
                    execution,
                    LogLevel.ERROR,
                    f"Node failed: {result.error}",
                    node.id
                )
            
            return result
            
        except Exception as e:
            error_msg = f"Error executing node: {str(e)}"
            self._add_log(execution, LogLevel.ERROR, error_msg, node.id)
            return ExecutionResult(success=False, error=error_msg)
    
    def _topological_sort(self, nodes: List[Node], edges: List[Edge]) -> List[Node]:
        """
        Perform topological sort on nodes
        
        Returns nodes in execution order based on dependencies
        """
        # Build adjacency list and in-degree count
        adj_list: Dict[str, List[str]] = {node.id: [] for node in nodes}
        in_degree: Dict[str, int] = {node.id: 0 for node in nodes}
        node_map: Dict[str, Node] = {node.id: node for node in nodes}
        
        for edge in edges:
            if edge.source in adj_list and edge.target in adj_list:
                adj_list[edge.source].append(edge.target)
                in_degree[edge.target] += 1
        
        # Find all nodes with no incoming edges
        queue = [node_id for node_id, degree in in_degree.items() if degree == 0]
        result = []
        
        while queue:
            # Sort to ensure consistent execution order
            queue.sort()
            current = queue.pop(0)
            result.append(node_map[current])
            
            # Reduce in-degree for neighbors
            for neighbor in adj_list[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        # Check for cycles
        if len(result) != len(nodes):
            logger.error("Circular dependency detected in workflow")
            return []
        
        return result
    
    def _get_node_inputs(
        self,
        node_id: str,
        edges: List[Edge],
        node_results: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Get input values for a node from connected nodes"""
        
        inputs: Dict[str, Any] = {}
        
        # Find all edges targeting this node
        incoming_edges = [edge for edge in edges if edge.target == node_id]
        
        logger.debug(f"Getting inputs for node {node_id}: found {len(incoming_edges)} incoming edges")
        logger.debug(f"Available node results: {list(node_results.keys())}")
        
        for edge in incoming_edges:
            source_result = node_results.get(edge.source)
            logger.debug(f"Edge from {edge.source} to {node_id}: result = {source_result is not None}")
            
            if source_result is not None:
                # Use target handle as key, or "default" if not specified
                input_key = edge.targetHandle or "default"
                inputs[input_key] = source_result
                logger.debug(f"Added input '{input_key}' from node {edge.source}")
            else:
                logger.warning(f"No result found for source node {edge.source} when getting inputs for {node_id}")
        
        logger.debug(f"Final inputs for node {node_id}: {list(inputs.keys())}")
        return inputs
    
    def _validate_workflow(self, workflow: Workflow) -> Optional[str]:
        """Validate workflow structure"""
        
        if not workflow.nodes:
            return "Workflow has no nodes"
        
        # Check for invalid node types
        for node in workflow.nodes:
            logical_type = self._get_logical_node_type(node)
            if logical_type not in self.node_executors:
                logger.warning(f"Unknown node type: {logical_type} (original: {node.type})")
                # Don't fail on unknown types, just warn
        
        # Check for invalid edges
        node_ids = {node.id for node in workflow.nodes}
        for edge in workflow.edges:
            if edge.source not in node_ids:
                return f"Edge references non-existent source node: {edge.source}"
            if edge.target not in node_ids:
                return f"Edge references non-existent target node: {edge.target}"
        
        return None
    
    def _add_log(
        self,
        execution: ExecutionState,
        level: LogLevel,
        message: str,
        node_id: Optional[str] = None,
        data: Optional[Any] = None
    ):
        """Add a log entry to execution state"""
        
        log = ExecutionLog(
            id=f"log_{uuid.uuid4().hex[:16]}",
            timestamp=datetime.now().isoformat(),
            level=level,
            message=message,
            nodeId=node_id,
            data=data
        )
        
        execution.logs.append(log)
        
        # Persist log to database
        try:
            db = next(get_db())
            exec_repo = ExecutionRepository(db)
            exec_repo.add_log(execution.id, log)
            db.close()
        except Exception as e:
            logger.warning(f"Failed to persist log to database: {str(e)}")
        
        # Also log to Python logger
        log_msg = f"[{execution.id}] {message}"
        if level == LogLevel.ERROR:
            logger.error(log_msg)
        elif level == LogLevel.WARNING:
            logger.warning(log_msg)
        else:
            logger.info(log_msg)
    
    def get_execution(self, execution_id: str) -> Optional[ExecutionState]:
        """Get execution state by ID"""
        return self.executions.get(execution_id)
    
    def get_execution_logs(self, execution_id: str) -> List[ExecutionLog]:
        """Get logs for an execution"""
        execution = self.executions.get(execution_id)
        return execution.logs if execution else []
    
    async def stop_execution(self, execution_id: str) -> bool:
        """Stop a running execution"""
        execution = self.executions.get(execution_id)
        
        if not execution:
            return False
        
        if execution.status == ExecutionStatus.RUNNING:
            execution.status = ExecutionStatus.STOPPED
            execution.endTime = datetime.now().isoformat()
            self._add_log(execution, LogLevel.INFO, "Execution stopped by user")
            return True
        
        return False
    
    def list_executions(self) -> List[ExecutionState]:
        """List all executions"""
        return list(self.executions.values())


# Global workflow engine instance
workflow_engine = WorkflowEngine()

