"""
Node executor for time-trigger node
"""

from typing import Any, Dict, Optional
import logging
from datetime import datetime, time
import pytz

from .base import NodeExecutor
from app.models.execution import ExecutionResult, NodeExecutionContext

logger = logging.getLogger(__name__)


class TimeTriggerExecutor(NodeExecutor):
    """Executor for time-trigger node - triggers based on time conditions"""
    
    async def execute(self, context: NodeExecutionContext) -> ExecutionResult:
        """Check if time trigger condition is met"""
        
        trigger_time = self.get_config(context, "triggerTime", "09:30")
        timezone = self.get_config(context, "timezone", "EST")
        days = self.get_config(context, "days", ["monday", "tuesday", "wednesday", "thursday", "friday"])
        trigger_type = self.get_config(context, "triggerType", "schedule")
        
        self.log_info(f"Checking time trigger: {trigger_time} {timezone}", context)
        
        try:
            # Parse trigger time
            try:
                hour, minute = map(int, trigger_time.split(":"))
                trigger_time_obj = time(hour, minute)
            except:
                return self.create_result(False, None, f"Invalid time format: {trigger_time}")
            
            # Get current time in specified timezone
            tz_map = {
                "EST": pytz.timezone("US/Eastern"),
                "PST": pytz.timezone("US/Pacific"),
                "UTC": pytz.UTC,
                "IST": pytz.timezone("Asia/Kolkata")
            }
            
            tz = tz_map.get(timezone.upper(), pytz.UTC)
            current_time = datetime.now(tz)
            current_time_obj = current_time.time()
            current_day = current_time.strftime("%A").lower()
            
            # Check if current day is in allowed days
            day_allowed = current_day in [d.lower() for d in days]
            
            # Check if time condition is met
            if trigger_type == "schedule":
                # Check if current time matches trigger time (within 1 minute tolerance)
                time_diff = abs(
                    (current_time_obj.hour * 60 + current_time_obj.minute) -
                    (trigger_time_obj.hour * 60 + trigger_time_obj.minute)
                )
                triggered = day_allowed and time_diff <= 1
            elif trigger_type == "before":
                triggered = day_allowed and current_time_obj < trigger_time_obj
            elif trigger_type == "after":
                triggered = day_allowed and current_time_obj >= trigger_time_obj
            else:
                triggered = day_allowed
            
            result = {
                "triggered": triggered,
                "current_time": current_time.isoformat(),
                "trigger_time": trigger_time,
                "timezone": timezone,
                "current_day": current_day,
                "day_allowed": day_allowed,
                "trigger_type": trigger_type
            }
            
            if triggered:
                self.log_success(
                    f"Time trigger ACTIVATED: {current_time_obj} matches {trigger_time}",
                    context
                )
            else:
                self.log_info(
                    f"Time trigger not activated: {current_time_obj} (target: {trigger_time}, day: {current_day})",
                    context
                )
            
            return self.create_result(True, result)
            
        except Exception as e:
            error_msg = f"Error checking time trigger: {str(e)}"
            self.log_error(error_msg, context)
            return self.create_result(False, None, error_msg)






