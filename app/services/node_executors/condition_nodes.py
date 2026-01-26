"""
Node executors for condition and logic nodes
"""

from typing import Any, List, Optional, Union
import logging
import re

from .base import NodeExecutor
from app.models.execution import ExecutionResult, NodeExecutionContext

logger = logging.getLogger(__name__)


def parse_percent(value: Any) -> float:
    """
    Parse a percentage value from various formats.
    
    Accepts:
    - "5%" -> 5.0
    - "-2.5%" -> -2.5
    - "5" -> 5.0
    - 5 -> 5.0
    - 5.0 -> 5.0
    - "+10%" -> 10.0
    
    Args:
        value: The value to parse (string or number)
        
    Returns:
        Float representing the percentage as points (e.g., 5 for "5%")
        
    Raises:
        ValueError: If value cannot be parsed as a percentage
    """
    if value is None:
        raise ValueError("Cannot parse None as percentage")
    
    # If already a number, return as float
    if isinstance(value, (int, float)):
        return float(value)
    
    # Convert to string and clean up
    str_value = str(value).strip()
    
    # Remove percent sign if present
    if str_value.endswith("%"):
        str_value = str_value[:-1].strip()
    
    # Handle + prefix
    if str_value.startswith("+"):
        str_value = str_value[1:].strip()
    
    # Try to parse as float
    try:
        return float(str_value)
    except ValueError:
        raise ValueError(f"Cannot parse '{value}' as percentage")


def extract_percent_from_dict(data: dict) -> Optional[float]:
    """
    Extract a percentage value from a dictionary (e.g., market data).
    
    Args:
        data: Dictionary that may contain percent change fields
        
    Returns:
        Percentage value as float, or None if not found
    """
    # Try common percent keys
    percent_keys = [
        "regularMarketChangePercent",
        "changePercent", 
        "percentChange",
        "change_percent",
        "pctChange",
        "percent",
        "pnlPercent",
        "totalPnLPercent",
        "unrealizedPnLPercent"
    ]
    
    for key in percent_keys:
        if key in data and data[key] is not None:
            try:
                return parse_percent(data[key])
            except ValueError:
                continue
    
    return None


class ComparisonExecutor(NodeExecutor):
    """Executor for comparison node - performs comparison operations"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Perform comparison operation"""
        
        # Validate required config
        error = self.validate_required_config(context, "operator", "value")
        if error:
            return self.create_result(False, None, error)
        
        operator = self.get_config(context, "operator")
        compare_value = self.get_config(context, "value")
        input_type = self.get_config(context, "inputType", "number")
        
        # Get input value - try multiple keys
        input_value = self.get_input(context, "default")
        
        # If no input with "default" key, try to get any input
        if input_value is None and context.inputs:
            # Get the first available input value
            input_value = next(iter(context.inputs.values()), None)
            self.log_info(f"No 'default' input found, using first available input: {list(context.inputs.keys())}", context)
        
        if input_value is None:
            error_msg = f"No input value provided. Available inputs: {list(context.inputs.keys()) if context.inputs else 'none'}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)
        
        # Extract value based on input type and data format
        original_input = input_value
        
        if isinstance(input_value, dict):
            if input_type == "percentage":
                # For percentage type, try to extract percent change from dict
                extracted = extract_percent_from_dict(input_value)
                if extracted is not None:
                    input_value = extracted
                else:
                    # Fall back to generic extraction
                    input_value = self._extract_value_from_dict(input_value, input_type)
            else:
                input_value = self._extract_value_from_dict(input_value, input_type)
        
        self.log_info(
            f"Comparing: {input_value} {operator} {compare_value} (type: {input_type})",
            context
        )
        
        try:
            # Convert values to appropriate types with percentage parsing
            if input_type == "percentage":
                # Parse both values as percentages (handles "5%", "-2.5%", etc.)
                input_value = parse_percent(input_value)
                compare_value = parse_percent(compare_value)
                self.log_info(f"Parsed as percentages: input={input_value}%, compare={compare_value}%", context)
            else:
                # Default number conversion
                input_value = float(input_value)
                compare_value = float(compare_value)
            
            # Perform comparison
            result = False
            
            if operator == ">":
                result = input_value > compare_value
            elif operator == "<":
                result = input_value < compare_value
            elif operator == ">=":
                result = input_value >= compare_value
            elif operator == "<=":
                result = input_value <= compare_value
            elif operator == "==":
                result = input_value == compare_value
            elif operator == "!=":
                result = input_value != compare_value
            else:
                return self.create_result(
                    False,
                    None,
                    f"Unsupported operator: {operator}"
                )
            
            # Build detailed result
            result_data = {
                "result": result,
                "conditionMet": result,
                "input_value": input_value,
                "compare_value": compare_value,
                "operator": operator,
                "input_type": input_type
            }
            
            self.log_success(
                f"Comparison result: {input_value} {operator} {compare_value} = {result}",
                context
            )
            
            return self.create_result(True, result_data)
            
        except ValueError as ve:
            error_msg = f"Error parsing values: {str(ve)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)
        except Exception as e:
            error_msg = f"Error performing comparison: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)
    
    def _extract_value_from_dict(self, data: dict, input_type: str = "number") -> Any:
        """Extract a numeric value from a dictionary based on input type"""
        
        # For percentage type, prioritize percent fields
        if input_type == "percentage":
            percent_val = extract_percent_from_dict(data)
            if percent_val is not None:
                return percent_val
        
        # Try common keys for price/value data
        value_keys = [
            "price", "regularMarketPrice", "current", "value", "close",
            "result", "rsi", "sma", "ema", "current_macd"
        ]
        
        for key in value_keys:
            if key in data and data[key] is not None:
                return data[key]
        
        # If no known key, return the first numeric value
        for value in data.values():
            if isinstance(value, (int, float)):
                return value
        
        return data


class BooleanLogicExecutor(NodeExecutor):
    """Executor for boolean-logic node - performs AND, OR, NOT, XOR operations"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Perform boolean logic operation"""
        
        # Validate required config
        error = self.validate_required_config(context, "operator")
        if error:
            return self.create_result(False, None, error)
        
        operator = self.get_config(context, "operator", "AND")
        num_inputs = self.get_config(context, "inputs", 2)
        
        # Get all input values
        input_values = []
        for i in range(num_inputs):
            input_key = f"input-{i}" if i > 0 else "default"
            value = self.get_input(context, input_key)
            
            # Convert to boolean
            if value is not None:
                input_values.append(bool(value))
        
        if not input_values:
            return self.create_result(False, None, "No input values provided")
        
        self.log_info(
            f"Boolean logic {operator} on {len(input_values)} inputs: {input_values}",
            context
        )
        
        try:
            result = False
            
            if operator == "AND":
                result = all(input_values)
            elif operator == "OR":
                result = any(input_values)
            elif operator == "NOT":
                result = not input_values[0]
            elif operator == "XOR":
                # XOR: exactly one input should be true
                result = sum(input_values) == 1
            else:
                return self.create_result(
                    False,
                    None,
                    f"Unsupported operator: {operator}"
                )
            
            self.log_success(
                f"Boolean {operator} result: {result}",
                context
            )
            
            return self.create_result(True, result)
            
        except Exception as e:
            error_msg = f"Error performing boolean logic: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)


class ThresholdExecutor(NodeExecutor):
    """Executor for threshold node - checks if values cross thresholds"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Check threshold condition"""
        
        # Validate required config
        error = self.validate_required_config(context, "thresholdType", "value")
        if error:
            return self.create_result(False, None, error)
        
        threshold_type = self.get_config(context, "thresholdType")
        threshold_value = self.get_config(context, "value")
        operator = self.get_config(context, "operator", "above")
        symbol = self.get_config(context, "symbol")
        
        # Get input value or fetch market data
        input_value = self.get_input(context, "default")
        
        # If no input and we have a symbol, fetch market data
        if input_value is None and symbol:
            from app.services.market_data import market_data_service
            quote_data = market_data_service.get_quote(symbol)
            
            if quote_data:
                if threshold_type == "price":
                    input_value = quote_data.get("price")
                elif threshold_type == "volume":
                    input_value = quote_data.get("regularMarketVolume")
                elif threshold_type == "percentage":
                    # Get percent change from quote
                    percent_val = extract_percent_from_dict(quote_data)
                    if percent_val is not None:
                        input_value = percent_val
        
        if input_value is None:
            return self.create_result(
                False,
                None,
                f"No input value and could not fetch market data for threshold type '{threshold_type}'"
            )
        
        # Extract value from dict if needed
        if isinstance(input_value, dict):
            input_value = self._extract_threshold_value(input_value, threshold_type)
        
        self.log_info(
            f"Threshold check: {threshold_type} {input_value} {operator} {threshold_value}",
            context
        )
        
        try:
            # Parse values with percentage support
            if threshold_type == "percentage":
                # Parse both as percentages (handles "5%", "-2.5%", etc.)
                input_value = parse_percent(input_value)
                threshold_value = parse_percent(threshold_value)
                self.log_info(f"Parsed as percentages: input={input_value}%, threshold={threshold_value}%", context)
            else:
                input_value = float(input_value)
                threshold_value = float(threshold_value)
            
            result = False
            
            if operator == "above":
                result = input_value > threshold_value
            elif operator == "below":
                result = input_value < threshold_value
            elif operator == "crosses_above":
                # For crossing, we'd need previous value
                # For now, just check if above
                result = input_value > threshold_value
            elif operator == "crosses_below":
                # For crossing, we'd need previous value
                # For now, just check if below
                result = input_value < threshold_value
            elif operator == "equals" or operator == "==":
                # Allow small tolerance for floating point comparison
                result = abs(input_value - threshold_value) < 0.0001
            else:
                return self.create_result(
                    False,
                    None,
                    f"Unsupported operator: {operator}"
                )
            
            # Build detailed result
            result_data = {
                "result": result,
                "conditionMet": result,
                "threshold_type": threshold_type,
                "input_value": input_value,
                "threshold_value": threshold_value,
                "operator": operator,
                "symbol": symbol
            }
            
            self.log_success(
                f"Threshold check: {threshold_type} {input_value} {operator} {threshold_value} = {result}",
                context
            )
            
            return self.create_result(True, result_data)
            
        except ValueError as ve:
            error_msg = f"Error parsing threshold values: {str(ve)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)
        except Exception as e:
            error_msg = f"Error checking threshold: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)
    
    def _extract_threshold_value(self, data: dict, threshold_type: str) -> Any:
        """Extract the appropriate value based on threshold type"""
        
        if threshold_type == "price":
            for key in ["price", "regularMarketPrice", "close", "current"]:
                if key in data and data[key] is not None:
                    return data[key]
        
        elif threshold_type == "volume":
            for key in ["volume", "regularMarketVolume"]:
                if key in data and data[key] is not None:
                    return data[key]
        
        elif threshold_type == "rsi":
            if "current" in data and data["current"] is not None:
                return data["current"]
            elif "rsi" in data and data["rsi"] is not None:
                return data["rsi"]
            elif "values" in data and data["values"]:
                # Get last non-None value
                for val in reversed(data["values"]):
                    if val is not None:
                        return val
        
        elif threshold_type == "percentage":
            # Use the helper function for percentage extraction
            percent_val = extract_percent_from_dict(data)
            if percent_val is not None:
                return percent_val
        
        elif threshold_type in ("sma", "ema", "macd"):
            # Technical indicator thresholds
            if "current" in data and data["current"] is not None:
                return data["current"]
            if threshold_type in data and data[threshold_type] is not None:
                return data[threshold_type]
            if "current_" + threshold_type in data:
                return data["current_" + threshold_type]
        
        # Default: return first numeric value
        for value in data.values():
            if isinstance(value, (int, float)) and value is not None:
                return value
        
        return data

