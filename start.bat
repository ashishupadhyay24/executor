@echo off
REM Workflow Execution Backend Startup Script for Windows

echo Starting Workflow Execution Backend...

REM Check if virtual environment exists
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Install dependencies
echo Installing dependencies...
pip install -r requirements.txt

REM Create .env if it doesn't exist
if not exist ".env" (
    echo Creating .env file from .env.example...
    copy .env.example .env
    echo Please configure your .env file before running the server
    pause
    exit /b 1
)

REM Start the server
echo Starting FastAPI server...
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8008

