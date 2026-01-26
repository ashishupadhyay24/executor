"""
Extended condition node executors for pattern detection and custom scripts
"""

from typing import Any, Dict, List, Optional
import logging
import ast
import operator as op

from .base import NodeExecutor
from app.models.execution import ExecutionResult, NodeExecutionContext
from app.services.market_data import market_data_service

logger = logging.getLogger(__name__)


class PatternDetectionExecutor(NodeExecutor):
    """Executor for pattern-detection node - detects candlestick patterns"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Detect candlestick patterns in price data"""
        
        pattern_type = self.get_config(context, "patternType", "engulfing")
        symbol = self.get_config(context, "symbol")
        
        # Get input data (historical OHLCV)
        input_data = self.get_input(context, "default")
        
        # If no input, fetch historical data
        if input_data is None and symbol:
            self.log_info(f"No input data, fetching historical data for {symbol}", context)
            hist_data = market_data_service.get_historical_data(
                symbol=symbol,
                period="3mo",
                interval="1d"
            )
            if hist_data:
                input_data = hist_data
        
        if input_data is None:
            return self.create_result(
                False,
                None,
                "No input data available and no symbol configured"
            )
        
        self.log_info(f"Detecting {pattern_type} pattern", context)
        
        try:
            # Extract OHLCV data
            ohlcv = self._extract_ohlcv(input_data)
            
            if len(ohlcv) < 2:
                return self.create_result(
                    False,
                    None,
                    "Insufficient data for pattern detection (need at least 2 candles)"
                )
            
            # Detect pattern
            pattern_result = self._detect_pattern(ohlcv, pattern_type)
            
            self.log_success(
                f"Pattern detection: {pattern_type} = {pattern_result['detected']}",
                context
            )
            
            return self.create_result(True, pattern_result)
            
        except Exception as e:
            error_msg = f"Error detecting pattern: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)
    
    def _extract_ohlcv(self, data: Any) -> List[Dict[str, float]]:
        """Extract OHLCV data from various formats"""
        ohlcv = []
        
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    candle = {
                        "open": float(item.get("open", item.get("Open", 0))),
                        "high": float(item.get("high", item.get("High", 0))),
                        "low": float(item.get("low", item.get("Low", 0))),
                        "close": float(item.get("close", item.get("Close", 0))),
                        "volume": float(item.get("volume", item.get("Volume", 0)))
                    }
                    ohlcv.append(candle)
        
        return ohlcv
    
    def _detect_pattern(self, ohlcv: List[Dict[str, float]], pattern_type: str) -> Dict[str, Any]:
        """Detect specific candlestick pattern"""
        
        if len(ohlcv) < 2:
            return {"detected": False, "pattern": pattern_type, "message": "Insufficient data"}
        
        # Get last 2 candles for most patterns
        prev = ohlcv[-2]
        curr = ohlcv[-1]
        
        detected = False
        details = {}
        
        if pattern_type == "engulfing":
            # Bullish engulfing: prev bearish, curr bullish and engulfs prev
            prev_bearish = prev["close"] < prev["open"]
            curr_bullish = curr["close"] > curr["open"]
            engulfs = curr["open"] < prev["close"] and curr["close"] > prev["open"]
            detected = prev_bearish and curr_bullish and engulfs
            
            if detected:
                details = {"type": "bullish_engulfing"}
            else:
                # Bearish engulfing
                prev_bullish = prev["close"] > prev["open"]
                curr_bearish = curr["close"] < curr["open"]
                engulfs = curr["open"] > prev["close"] and curr["close"] < prev["open"]
                detected = prev_bullish and curr_bearish and engulfs
                if detected:
                    details = {"type": "bearish_engulfing"}
        
        elif pattern_type == "breakout":
            # Price breaks above recent high
            if len(ohlcv) >= 20:
                recent_high = max([c["high"] for c in ohlcv[-20:]])
                detected = curr["close"] > recent_high
                if detected:
                    details = {"type": "breakout", "resistance": recent_high, "breakout_price": curr["close"]}
        
        elif pattern_type == "breakdown":
            # Price breaks below recent low
            if len(ohlcv) >= 20:
                recent_low = min([c["low"] for c in ohlcv[-20:]])
                detected = curr["close"] < recent_low
                if detected:
                    details = {"type": "breakdown", "support": recent_low, "breakdown_price": curr["close"]}
        
        elif pattern_type == "doji":
            # Doji: open and close are very close
            body_size = abs(curr["close"] - curr["open"])
            candle_range = curr["high"] - curr["low"]
            detected = body_size < (candle_range * 0.1) if candle_range > 0 else False
            if detected:
                details = {"type": "doji", "body_size": body_size}
        
        elif pattern_type == "hammer":
            # Hammer: small body, long lower wick
            body_size = abs(curr["close"] - curr["open"])
            lower_wick = min(curr["open"], curr["close"]) - curr["low"]
            upper_wick = curr["high"] - max(curr["open"], curr["close"])
            detected = lower_wick > (body_size * 2) and upper_wick < body_size
            if detected:
                details = {"type": "hammer", "lower_wick": lower_wick}
        
        else:
            return {
                "detected": False,
                "pattern": pattern_type,
                "message": f"Unsupported pattern type: {pattern_type}"
            }
        
        return {
            "detected": detected,
            "pattern": pattern_type,
            "details": details,
            "current_price": curr["close"],
            "previous_price": prev["close"]
        }


class CustomScriptExecutor(NodeExecutor):
    """Executor for custom-script node - safely evaluates custom expressions"""
    
    # Safe operators for expression evaluation
    SAFE_OPERATORS = {
        ast.Add: op.add,
        ast.Sub: op.sub,
        ast.Mult: op.mul,
        ast.Div: op.truediv,
        ast.FloorDiv: op.floordiv,
        ast.Mod: op.mod,
        ast.Pow: op.pow,
        ast.LShift: op.lshift,
        ast.RShift: op.rshift,
        ast.BitOr: op.or_,
        ast.BitXor: op.xor,
        ast.BitAnd: op.and_,
        ast.Lt: op.lt,
        ast.LtE: op.le,
        ast.Gt: op.gt,
        ast.GtE: op.ge,
        ast.Eq: op.eq,
        ast.NotEq: op.ne,
        ast.And: lambda a, b: a and b,
        ast.Or: lambda a, b: a or b,
        ast.Not: op.not_,
        ast.USub: op.neg,
        ast.UAdd: op.pos,
    }
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Safely evaluate custom script/expression"""
        
        script = self.get_config(context, "script")
        if not script:
            return self.create_result(False, None, "Script/expression required")
        
        # Get input variables
        input_data = self.get_input(context, "default")
        variables = {}
        
        if isinstance(input_data, dict):
            variables = input_data
        elif input_data is not None:
            variables = {"value": input_data}
        
        # Add any additional variables from config
        custom_vars = self.get_config(context, "variables", {})
        if isinstance(custom_vars, dict):
            variables.update(custom_vars)
        
        self.log_info(f"Evaluating custom script with variables: {list(variables.keys())}", context)
        
        try:
            # Parse and evaluate expression safely
            result = self._safe_eval(script, variables)
            
            self.log_success(f"Script evaluated successfully: {result}", context)
            
            return self.create_result(True, {
                "result": result,
                "script": script,
                "variables": variables
            })
            
        except Exception as e:
            error_msg = f"Error evaluating script: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)
    
    def _safe_eval(self, expr: str, variables: Dict[str, Any]) -> Any:
        """Safely evaluate a Python expression"""
        
        # Parse expression
        try:
            tree = ast.parse(expr, mode='eval')
        except SyntaxError as e:
            raise ValueError(f"Invalid expression syntax: {str(e)}")
        
        # Check for unsafe operations
        for node in ast.walk(tree):
            if isinstance(node, (ast.Call, ast.Import, ast.ImportFrom)):
                raise ValueError("Function calls and imports are not allowed")
            if isinstance(node, ast.Attribute):
                # Only allow access to safe attributes
                if node.attr not in ['keys', 'values', 'items', 'get']:
                    raise ValueError(f"Unsafe attribute access: {node.attr}")
        
        # Evaluate safely
        def eval_node(node):
            if isinstance(node, ast.Expression):
                return eval_node(node.body)
            elif isinstance(node, ast.Constant):
                return node.value
            elif isinstance(node, ast.Name):
                if node.id in variables:
                    return variables[node.id]
                raise NameError(f"Variable '{node.id}' not found")
            elif isinstance(node, ast.BinOp):
                return self.SAFE_OPERATORS[type(node.op)](
                    eval_node(node.left),
                    eval_node(node.right)
                )
            elif isinstance(node, ast.UnaryOp):
                return self.SAFE_OPERATORS[type(node.op)](eval_node(node.operand))
            elif isinstance(node, ast.Compare):
                left = eval_node(node.left)
                for op, comparator in zip(node.ops, node.comparators):
                    right = eval_node(comparator)
                    if not self.SAFE_OPERATORS[type(op)](left, right):
                        return False
                    left = right
                return True
            elif isinstance(node, ast.BoolOp):
                values = [eval_node(v) for v in node.values]
                if isinstance(node.op, ast.And):
                    return all(values)
                else:  # ast.Or
                    return any(values)
            else:
                raise ValueError(f"Unsupported AST node: {type(node)}")
        
        return eval_node(tree)






