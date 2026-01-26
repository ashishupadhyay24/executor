"""
Node executors for output and monitoring nodes
"""

from typing import Any, Dict, List, Optional
import logging
from datetime import datetime

from .base import NodeExecutor
from app.models.execution import ExecutionResult, NodeExecutionContext

logger = logging.getLogger(__name__)


class DashboardExecutor(NodeExecutor):
    """Executor for dashboard node - generates dashboard/metrics summary"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Generate dashboard summary"""
        
        # Get input data (portfolio, trades, etc.)
        input_data = self.get_input(context, "default")
        
        self.log_info("Generating dashboard summary", context)
        
        try:
            # Aggregate metrics from input
            dashboard_data = {
                "timestamp": datetime.now().isoformat(),
                "metrics": {}
            }
            
            if isinstance(input_data, dict):
                # Extract common metrics
                dashboard_data["metrics"] = {
                    "total_pnl": input_data.get("total_pnl", 0),
                    "unrealized_pnl": input_data.get("unrealized_pnl", 0),
                    "realized_pnl": input_data.get("realized_pnl", 0),
                    "total_trades": input_data.get("total_trades", 0),
                    "winning_trades": input_data.get("winning_trades", 0),
                    "losing_trades": input_data.get("losing_trades", 0),
                    "win_rate": (input_data.get("winning_trades", 0) / input_data.get("total_trades", 1) * 100) if input_data.get("total_trades", 0) > 0 else 0,
                    "portfolio_value": input_data.get("portfolio_value") or input_data.get("current_value", 0),
                    "positions_count": input_data.get("positions_count", 0)
                }
                
                # Include original data
                dashboard_data["data"] = input_data
            else:
                dashboard_data["data"] = input_data
            
            self.log_success("Dashboard summary generated", context)
            
            return self.create_result(True, dashboard_data)
            
        except Exception as e:
            error_msg = f"Error generating dashboard: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)


class ReportExecutor(NodeExecutor):
    """Executor for report node - generates execution reports"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Generate execution report"""
        
        report_type = self.get_config(context, "reportType", "summary")
        format_type = self.get_config(context, "format", "json")
        
        # Get execution data from input
        input_data = self.get_input(context, "default")
        
        self.log_info(f"Generating {report_type} report", context)
        
        try:
            report = {
                "report_id": f"report_{datetime.now().timestamp()}",
                "type": report_type,
                "format": format_type,
                "timestamp": datetime.now().isoformat(),
                "execution_id": context.executionId,
                "workflow_id": context.workflowId
            }
            
            if report_type == "summary":
                # Summary report
                if isinstance(input_data, dict):
                    report["summary"] = {
                        "status": input_data.get("status", "unknown"),
                        "total_pnl": input_data.get("total_pnl", 0),
                        "trades_executed": input_data.get("total_trades", 0),
                        "execution_time": input_data.get("execution_time"),
                        "start_time": input_data.get("start_time"),
                        "end_time": input_data.get("end_time")
                    }
                else:
                    report["summary"] = {"status": "completed"}
            
            elif report_type == "detailed":
                # Detailed report with all data
                report["data"] = input_data
                report["details"] = {
                    "all_trades": input_data.get("trades", []) if isinstance(input_data, dict) else [],
                    "all_positions": input_data.get("positions", []) if isinstance(input_data, dict) else [],
                    "all_logs": input_data.get("logs", []) if isinstance(input_data, dict) else []
                }
            
            elif report_type == "performance":
                # Performance metrics report
                if isinstance(input_data, dict):
                    report["performance"] = {
                        "total_return": input_data.get("total_return", 0),
                        "sharpe_ratio": input_data.get("sharpe_ratio"),
                        "max_drawdown": input_data.get("max_drawdown", 0),
                        "win_rate": input_data.get("win_rate", 0),
                        "average_win": input_data.get("average_win", 0),
                        "average_loss": input_data.get("average_loss", 0),
                        "profit_factor": input_data.get("profit_factor")
                    }
            
            self.log_success(f"{report_type} report generated", context)
            
            return self.create_result(True, report)
            
        except Exception as e:
            error_msg = f"Error generating report: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)






