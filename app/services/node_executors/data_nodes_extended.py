"""
Extended data node executors for fundamental data
"""

from typing import Any, Dict, List, Optional
import logging

from .base import NodeExecutor
from app.models.execution import ExecutionResult, NodeExecutionContext
from app.services.market_data import market_data_service

logger = logging.getLogger(__name__)


class FundamentalDataExecutor(NodeExecutor):
    """Executor for fundamental-data node - fetches fundamental financial data"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Fetch fundamental data for a symbol"""
        
        error = self.validate_required_config(context, "symbol")
        if error:
            return self.create_result(False, None, error)
        
        symbol = self.get_config(context, "symbol")
        data_type = self.get_config(context, "dataType", "earnings")
        period = self.get_config(context, "period", "quarterly")
        
        self.log_info(f"Fetching fundamental data for {symbol}, type={data_type}", context)
        
        try:
            import yfinance as yf
            
            ticker = yf.Ticker(symbol)
            fundamental_data = {}
            
            if data_type == "earnings":
                earnings = ticker.earnings
                if earnings is not None and not earnings.empty:
                    fundamental_data = {
                        "earnings": earnings.to_dict(),
                        "earnings_dates": ticker.earnings_dates.to_dict() if hasattr(ticker, 'earnings_dates') and ticker.earnings_dates is not None else {}
                    }
                else:
                    fundamental_data = {"earnings": {}, "message": "No earnings data available"}
            
            elif data_type == "financials":
                if period == "quarterly":
                    financials = ticker.quarterly_financials
                else:
                    financials = ticker.financials
                
                if financials is not None and not financials.empty:
                    fundamental_data = {"financials": financials.to_dict()}
                else:
                    fundamental_data = {"financials": {}, "message": "No financials data available"}
            
            elif data_type == "ratios":
                info = ticker.info
                ratios = {
                    "pe_ratio": info.get("trailingPE"),
                    "forward_pe": info.get("forwardPE"),
                    "peg_ratio": info.get("pegRatio"),
                    "price_to_book": info.get("priceToBook"),
                    "debt_to_equity": info.get("debtToEquity"),
                    "current_ratio": info.get("currentRatio"),
                    "quick_ratio": info.get("quickRatio"),
                    "return_on_equity": info.get("returnOnEquity"),
                    "return_on_assets": info.get("returnOnAssets"),
                }
                fundamental_data = {"ratios": ratios, "info": info}
            
            elif data_type in ["balance_sheet", "cash_flow", "income_statement"]:
                if period == "quarterly":
                    if data_type == "balance_sheet":
                        data = ticker.quarterly_balance_sheet
                    elif data_type == "cash_flow":
                        data = ticker.quarterly_cashflow
                    else:
                        data = ticker.quarterly_income_stmt
                else:
                    if data_type == "balance_sheet":
                        data = ticker.balance_sheet
                    elif data_type == "cash_flow":
                        data = ticker.cashflow
                    else:
                        data = ticker.income_stmt
                
                if data is not None and not data.empty:
                    fundamental_data = {data_type: data.to_dict()}
                else:
                    fundamental_data = {data_type: {}, "message": f"No {data_type} data available"}
            
            else:
                return self.create_result(
                    False,
                    None,
                    f"Unsupported fundamental data type: {data_type}"
                )
            
            self.log_success(
                f"Fundamental data fetched for {symbol}: {data_type}",
                context
            )
            
            return self.create_result(True, fundamental_data)
            
        except Exception as e:
            error_msg = f"Error fetching fundamental data: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)


