# Workflow Execution Backend

Python FastAPI backend service for executing trading workflows with real-time market data.

## Features

- **Complete node type coverage** - All 40+ frontend node types supported
- **Paper trading** - Safe testing with virtual money and full PnL tracking
- **Live trading** - Zerodha Kite integration for real order placement
- **Real-time market data** - Via yfinance with caching
- **Technical indicators** - RSI, SMA, EMA, MACD, Bollinger Bands, and more
- **Advanced features** - Pattern detection, custom scripts, risk management
- **SQLite persistence** - All executions, logs, orders, and positions stored
- **Comprehensive logging** - Detailed execution logs for debugging

## Setup

### Prerequisites

- Python 3.9+
- pip or pipenv

### Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Create `.env` file from example:
```bash
cp .env.example .env
```

3. Configure environment variables in `.env`

### Running the Server

Development mode:
```bash
uvicorn app.main:app --reload --port 8000
```

Production mode:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## API Endpoints

### Execute Workflow
```
POST /api/workflows/execute
```
Execute a workflow graph.

Request body:
```json
{
  "workflow": {
    "id": "workflow_123",
    "name": "My Strategy",
    "nodes": [...],
    "edges": [...]
  }
}
```

### Get Execution Status
```
GET /api/workflows/executions/{execution_id}
```
Get the current status of a workflow execution.

### Stop Execution
```
POST /api/workflows/executions/{execution_id}/stop
```
Stop a running workflow execution.

### Get Execution Logs
```
GET /api/workflows/executions/{execution_id}/logs
```
Get detailed execution logs.

## Supported Node Types

### Data Nodes
- `market-data`: Real-time market data
- `historical-data`: Historical OHLCV data
- `technical-indicator`: Calculate technical indicators

### Condition Nodes
- `comparison`: Comparison operators (>, <, =, etc.)
- `boolean-logic`: AND, OR, NOT, XOR operations
- `threshold`: Price/volume thresholds

### Technical Nodes
- `rsi-condition`: RSI-based conditions
- `ma-condition`: Moving average conditions

### Trading Nodes
- `buy-order`: Place buy orders
- `sell-order`: Place sell orders
- `stop-loss`: Stop loss management

### Utility Nodes
- `delay-timer`: Delay execution
- `logging`: Log messages
- `alert`: Send alerts

## Architecture

- **FastAPI**: Modern Python web framework
- **Pydantic**: Data validation and serialization
- **yfinance**: Market data provider
- **pandas/numpy**: Data processing and calculations

## Development

### Project Structure
```
backend/
├── app/
│   ├── main.py                    # FastAPI application
│   ├── models/                    # Pydantic models
│   ├── services/                  # Business logic
│   │   ├── workflow_engine.py    # Workflow execution engine
│   │   ├── market_data.py        # Market data service
│   │   └── node_executors/       # Node execution handlers
│   └── api/                       # API routes
├── requirements.txt
└── .env.example
```

### Adding New Node Types

1. Create executor class in appropriate file under `node_executors/`
2. Inherit from `NodeExecutor` base class
3. Implement `execute()` method
4. Register in `workflow_engine.py`

## Error Handling

The service includes comprehensive error handling:
- Node execution errors are logged but don't stop the workflow
- Invalid node types return error results
- Network errors are retried with exponential backoff
- All errors are logged with full context

## Performance

- Market data caching to reduce API calls
- Async execution where possible
- Efficient topological sort for node ordering
- Memory-efficient data processing

## License

MIT

