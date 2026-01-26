"""
Broker service factory - creates appropriate broker based on trading mode
"""

from typing import Optional
import logging
import os

from .base import BrokerService
from .paper import PaperBrokerService
from .kite import KiteBrokerService

logger = logging.getLogger(__name__)


class BrokerFactory:
    """Factory for creating broker services"""
    
    @staticmethod
    def create_broker(
        trading_mode: str,
        user_id: str,
        portfolio_id: str,
        **kwargs
    ) -> BrokerService:
        """
        Create a broker service based on trading mode
        
        Args:
            trading_mode: "paper" or "kite"
            user_id: User ID
            portfolio_id: Portfolio ID
            **kwargs: Additional broker-specific parameters
                - For paper: initial_capital (optional, default 100000)
                - For kite: access_token, api_key (required)
        
        Returns:
            BrokerService instance
        """
        
        if trading_mode == "paper":
            initial_capital = kwargs.get("initial_capital", 100000.0)
            return PaperBrokerService(
                user_id=user_id,
                portfolio_id=portfolio_id,
                initial_capital=initial_capital
            )
        
        elif trading_mode == "kite":
            access_token = kwargs.get("access_token")
            api_key = kwargs.get("api_key") or os.getenv("KITE_API_KEY")
            
            if not access_token:
                raise ValueError("access_token required for Kite broker")
            if not api_key:
                raise ValueError("KITE_API_KEY environment variable or api_key parameter required")
            
            return KiteBrokerService(
                user_id=user_id,
                portfolio_id=portfolio_id,
                access_token=access_token,
                api_key=api_key
            )
        
        else:
            raise ValueError(f"Unsupported trading mode: {trading_mode}")






