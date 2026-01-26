# Quick Start Guide

## Setup

1. **Install Python 3.9+**
   ```bash
   python --version  # Should be 3.9 or higher
   ```

2. **Create and activate virtual environment**
   
   On Linux/Mac:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
   
   On Windows:
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   ```

## Running the Server

### Option 1: Using startup script

On Linux/Mac:
```bash
chmod +x start.sh
./start.sh
```

On Windows:
```bash
start.bat
```

### Option 2: Manual start

```bash
# Activate virtual environment first
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# Start server
uvicorn main:app --reload --app-dir backend


 
```

The server will start at `http://localhost:8000`

## Testing the API

1. **Check health**
   ```bash
   curl http://localhost:8000/health
   ```

2. **View API documentation**
   Open in browser: `http://localhost:8000/docs`

3. **Execute a workflow**
   ```bash
   curl -X POST http://localhost:8000/api/workflows/execute \
     -H "Content-Type: application/json" \
     -d '{
       "workflow": {
         "id": "test_workflow",
         "name": "Test Workflow",
         "nodes": [
           {
             "id": "node1",
             "type": "market-data",
             "position": {"x": 0, "y": 0},
             "data": {"symbol": "AAPL"}
           }
         ],
         "edges": []
       }
     }'
   ```

## Frontend Integration

1. **Update frontend environment**
   
   Add to your frontend `.env.local`:
   ```
   NEXT_PUBLIC_WORKFLOW_API_URL=http://localhost:8000
   ```

2. **Use in your React components**
   ```typescript
   import { executeWorkflow } from '@/lib/api/workflow-execution-api';
   
   const response = await executeWorkflow(workflow);
   console.log('Execution started:', response.executionId);
   ```

## Common Issues

### Port already in use
Change the port in `.env`:
```
PORT=8001
```

### CORS errors
Add your frontend URL to CORS_ORIGINS in `.env`:
```
CORS_ORIGINS=http://localhost:9002,http://localhost:3000,http://localhost:3001
```

### Import errors
Make sure you're in the virtual environment:
```bash
which python  # Should show path to venv/bin/python
```

### yfinance rate limits
Increase the cache TTL in `.env`:
```
YFINANCE_CACHE_TTL=300  # 5 minutes
```

## Development

### Running tests
```bash
pytest
```

### Checking logs
Logs are printed to console. Adjust log level in `.env`:
```
LOG_LEVEL=DEBUG  # For more detailed logs
```

### Adding new node types
1. Create executor in `app/services/node_executors/`
2. Inherit from `NodeExecutor`
3. Implement `execute()` method
4. Register in `workflow_engine.py`

## Production Deployment

For production, use a production ASGI server:

```bash
pip install gunicorn

gunicorn app.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

Or use Docker:
```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Support

For issues or questions, check:
- API documentation: `http://localhost:8000/docs`
- Logs: Check console output
- README.md: Full documentation

