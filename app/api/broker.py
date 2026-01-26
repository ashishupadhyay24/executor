"""
API routes for broker authentication and management
"""

from fastapi import APIRouter, HTTPException, status, Request, Query
from typing import Optional
from pydantic import BaseModel
import logging
import os

from app.storage.db import get_db
from app.storage.repositories import BrokerSessionRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/broker", tags=["broker"])


class KiteConfigRequest(BaseModel):
    """Request to save Kite API credentials"""
    userId: str
    apiKey: str
    apiSecret: str


class KiteAccessTokenRequest(BaseModel):
    """Request to exchange request_token for access_token"""
    userId: str
    requestToken: str


@router.post("/kite/config")
async def save_kite_config(request: KiteConfigRequest):
    """
    Store Kite API credentials for a user
    
    Request body:
        {
            "userId": "user_id",
            "apiKey": "kite_api_key",
            "apiSecret": "kite_api_secret"
        }
    
    Returns:
        Success message
    """
    try:
        db = next(get_db())
        try:
            broker_repo = BrokerSessionRepository(db)
            broker_repo.upsert(
                user_id=request.userId,
                broker_type="kite",
                api_key=request.apiKey,
                api_secret=request.apiSecret
            )
            
            return {
                "success": True,
                "message": "Kite credentials saved successfully"
            }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error saving Kite config: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save credentials: {str(e)}"
        )


@router.get("/kite/login-url")
async def get_kite_login_url(userId: str = Query(..., description="User ID")):
    """
    Get Kite login URL for OAuth flow using stored API key
    
    Args:
        userId: User ID to get stored API key for
    
    Returns:
        Login URL
    """
    try:
        db = next(get_db())
        try:
            broker_repo = BrokerSessionRepository(db)
            session = broker_repo.get(user_id=userId, broker_type="kite")
            
            if not session or not session.api_key:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Kite API key not found. Please save your credentials first."
                )
            
            api_key = session.api_key
            
            try:
                from kiteconnect import KiteConnect
                kite = KiteConnect(api_key=api_key)
                login_url = kite.login_url()
                
                return {
                    "login_url": login_url,
                    "api_key": api_key,
                    "message": "Visit login_url to authenticate and get request_token"
                }
            except ImportError:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="kiteconnect package not installed"
                )
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating Kite login URL: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate login URL: {str(e)}"
        )


@router.post("/kite/access-token")
async def exchange_kite_token(request: KiteAccessTokenRequest):
    """
    Exchange request_token for access_token using stored credentials
    
    Request body:
        {
            "userId": "user_id",
            "requestToken": "request_token_from_kite"
        }
    
    Returns:
        Access token and user details
    """
    try:
        db = next(get_db())
        try:
            broker_repo = BrokerSessionRepository(db)
            session = broker_repo.get(user_id=request.userId, broker_type="kite")
            
            if not session or not session.api_key or not session.api_secret:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Kite credentials not found. Please save your API key and secret first."
                )
            
            api_key = session.api_key
            api_secret = session.api_secret
            
            try:
                from kiteconnect import KiteConnect
                kite = KiteConnect(api_key=api_key, api_secret=api_secret)
                data = kite.generate_session(request.requestToken, api_secret=api_secret)
                
                access_token = data.get("access_token")
                refresh_token = data.get("refresh_token")
                user_data = data.get("user_data", {})
                
                # Store access token and refresh token
                broker_repo.upsert(
                    user_id=request.userId,
                    broker_type="kite",
                    access_token=access_token,
                    refresh_token=refresh_token
                )
                
                return {
                    "access_token": access_token,
                    "user_id": user_data.get("user_id"),
                    "user_name": user_data.get("user_name"),
                    "user_shortname": user_data.get("user_shortname"),
                    "email": user_data.get("email"),
                    "message": "Access token stored successfully"
                }
            except ImportError:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="kiteconnect package not installed"
                )
            except Exception as e:
                logger.error(f"Error exchanging token: {str(e)}", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to exchange token: {str(e)}"
                )
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in token exchange: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to exchange token: {str(e)}"
        )


@router.get("/kite/status")
async def get_kite_status(userId: str = Query(..., description="User ID")):
    """
    Get Kite connection status for a user
    
    Args:
        userId: User ID to check status for
    
    Returns:
        Connection status and user info if connected
    """
    try:
        db = next(get_db())
        try:
            broker_repo = BrokerSessionRepository(db)
            session = broker_repo.get(user_id=userId, broker_type="kite")
            
            if not session or not session.access_token or not session.api_key:
                return {
                    "connected": False,
                    "has_credentials": session is not None and session.api_key is not None,
                    "has_access_token": session is not None and session.access_token is not None
                }
            
            # Try to validate the token
            try:
                from kiteconnect import KiteConnect
                kite = KiteConnect(api_key=session.api_key)
                kite.set_access_token(session.access_token)
                
                # Try to get user profile to validate token
                profile = kite.profile()
                
                return {
                    "connected": True,
                    "has_credentials": True,
                    "has_access_token": True,
                    "user_id": profile.get("user_id"),
                    "user_name": profile.get("user_name"),
                    "email": profile.get("email")
                }
            except ImportError:
                return {
                    "connected": False,
                    "has_credentials": True,
                    "has_access_token": True,
                    "error": "kiteconnect package not installed"
                }
            except Exception as e:
                logger.warning(f"Token validation failed: {str(e)}")
                return {
                    "connected": False,
                    "has_credentials": True,
                    "has_access_token": True,
                    "error": str(e)
                }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error checking Kite status: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check status: {str(e)}"
        )


@router.get("/kite/session")
async def get_kite_session(userId: str = Query(..., description="User ID")):
    """
    Get stored Kite session (access token and API key) for a user
    
    Args:
        userId: User ID to get session for
    
    Returns:
        Session info (without sensitive data)
    """
    try:
        db = next(get_db())
        try:
            broker_repo = BrokerSessionRepository(db)
            session = broker_repo.get(user_id=userId, broker_type="kite")
            
            if not session:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No Kite session found for this user"
                )
            
            return {
                "user_id": session.user_id,
                "broker_type": session.broker_type,
                "has_api_key": session.api_key is not None,
                "has_access_token": session.access_token is not None,
                "has_refresh_token": session.refresh_token is not None,
                "created_at": session.created_at.isoformat() if session.created_at else None,
                "updated_at": session.updated_at.isoformat() if session.updated_at else None
            }
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting Kite session: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get session: {str(e)}"
        )

