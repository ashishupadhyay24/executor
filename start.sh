#!/bin/bash

# Workflow Execution Backend Startup Script

echo "Starting Workflow Execution Backend..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Create .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo "Creating .env file from .env.example..."
    cp .env.example .env
    echo "Please configure your .env file before running the server"
    exit 1
fi

# Start the server
echo "Starting FastAPI server..."
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

