# Workflow Execution Backend API Documentation

## Overview

This Python FastAPI backend provides a complete workflow execution engine for algorithmic trading workflows. It supports both **paper trading** (for testing) and **live trading via Zerodha Kite**.

## Base URL

- Development: `http://127.0.0.1:8000`
- Production: Configure via `HOST` and `PORT` environment variables

## Trading Modes

### Paper Trading (Default)
- Safe testing mode with virtual money
- Tracks positions, orders, and PnL
- No real money at risk
- Default initial capital: $100,000

### Kite Live Trading
- Real trading via Zerodha Kite
- Requires Kite API credentials and OAuth authentication
- Places actual orders on the exchange

## API Endpoints

### Workflow Execution

#### Execute Workflow
```http
POST /api/workflows/execute
```

Execute a workflow with specified trading mode.

**Request Body:**
```json
{
  "workflow": {
    "id": "workflow_123",
    "name": "My Strategy",
    "nodes": [...],
    "edges": [...]
  },
  "userId": "user_123",
  "portfolioId": "portfolio_123",
  "tradingMode": "paper",
  "brokerConfig": {
    "access_token": "kite_access_token_here"  // Required for Kite mode
  }
}
```

**Response:**
```json
{
  "executionId": "exec_abc123",
  "status": "started",
  "message": "Workflow execution started successfully"
}
```

**Trading Modes:**
- `"paper"` - Paper trading (default)
- `"kite"` - Live trading via Zerodha Kite

**Broker Config (for Kite mode):**
- `access_token` (required) - Kite access token from OAuth flow
- `api_key` (optional) - Override default KITE_API_KEY

#### Get Execution Status
```http
GET /api/workflows/executions/{execution_id}
```

Get current status of a workflow execution.

**Response:**
```json
{
  "execution": {
    "id": "exec_abc123",
    "workflowId": "workflow_123",
    "status": "running",
    "startTime": "2024-01-01T10:00:00",
    "progress": 50.0,
    "currentStep": "node_2",
    "logs": [...],
    "results": {...}
  }
}
```

#### Get Execution Logs
```http
GET /api/workflows/executions/{execution_id}/logs
```

Get detailed logs for an execution.

**Response:**
```json
{
  "executionId": "exec_abc123",
  "logs": [
    {
      "id": "log_1",
      "timestamp": "2024-01-01T10:00:00",
      "level": "info",
      "message": "Starting workflow execution",
      "nodeId": null
    }
  ]
}
```

#### Stop Execution
```http
POST /api/workflows/executions/{execution_id}/stop
```

Stop a running execution.

**Response:**
```json
{
  "success": true,
  "message": "Execution stopped successfully",
  "executionId": "exec_abc123"
}
```

#### List Executions
```http
GET /api/workflows/executions
```

List all executions.

**Response:**
```json
[
  {
    "id": "exec_abc123",
    "workflowId": "workflow_123",
    "status": "completed",
    ...
  }
]
```

### Broker Authentication (Kite)

#### Get Kite Login URL
```http
GET /api/broker/kite/login-url
```

Get OAuth login URL for Kite authentication.

**Response:**
```json
{
  "login_url": "https://kite.trade/connect/login?api_key=...",
  "api_key": "your_api_key",
  "message": "Visit login_url to authenticate and get request_token"
}
```

#### Exchange Request Token
```http
POST /api/broker/kite/access-token
```

Exchange request_token (from Kite OAuth callback) for access_token.

**Request Body:**
```json
{
  "request_token": "request_token_from_kite_callback",
  "api_secret": "optional_override"
}
```

**Response:**
```json
{
  "access_token": "kite_access_token",
  "user_id": "AB1234",
  "user_name": "John Doe",
  "email": "john@example.com"
}
```

#### Validate Access Token
```http
GET /api/broker/kite/validate?access_token=your_token
```

Validate a Kite access token.

**Response:**
```json
{
  "valid": true,
  "user_id": "AB1234",
  "user_name": "John Doe"
}
```

## Supported Node Types

### Data & Input Nodes
- `market-data` - Real-time market data
- `historical-data` - Historical OHLCV data
- `technical-indicator` - Technical indicators (RSI, MACD, SMA, etc.)
- `fundamental-data` - Fundamental financial data
- `news-sentiment` - News and sentiment data (stub)
- `custom-data` - Custom data input (CSV, API, manual)

### Condition & Logic Nodes
- `comparison` - Comparison operations (>, <, =, etc.)
- `boolean-logic` - Boolean operations (AND, OR, NOT, XOR)
- `threshold` - Threshold checks
- `pattern-detection` - Candlestick pattern detection
- `custom-script` - Safe expression evaluation

### Strategy Nodes
- `signal-generator` - Generate buy/sell/hold signals
- `entry-condition` - Entry condition checks
- `exit-condition` - Exit condition checks
- `stop-take-profit` - Stop loss and take profit management
- `trailing-stop` - Trailing stop loss

### Trading Nodes
- `buy-order` - Place buy orders
- `sell-order` - Place sell orders
- `stop-loss` - Stop loss management
- `order-placement` - Order placement (alias for buy-order)
- `order-management` - Manage existing orders

### Order & Portfolio Nodes
- `position-management` - Track and manage positions
- `portfolio-allocation` - Portfolio allocation calculations

### Risk Management Nodes
- `max-loss-drawdown` - Maximum loss/drawdown limits
- `position-sizing` - Position size calculations
- `leverage-control` - Leverage limit enforcement
- `daily-limits` - Daily profit/loss limits

### Utility & Control Flow Nodes
- `start-end` - Workflow start/end markers
- `delay-timer` - Delay execution
- `loop` - Loop iterations
- `parallel-execution` - Parallel branch coordination
- `error-handling` - Error handling and recovery

### Output & Monitoring Nodes
- `logging` - Log messages
- `alert` - Send alerts/notifications
- `dashboard` - Generate dashboard summaries
- `report` - Generate execution reports

### Technical Nodes
- `price-trigger` - Price-based triggers
- `time-trigger` - Time-based triggers
- `rsi-condition` - RSI condition checks
- `ma-condition` - Moving average condition checks

## Environment Variables

Create a `.env` file in the `backend/` directory:

```env
# Server
HOST=0.0.0.0
PORT=8000
ENV=development

# CORS
CORS_ORIGINS=http://localhost:9002,http://localhost:3000

# Database
DATABASE_URL=sqlite:///./workflow_executions.db

# Kite (for live trading)
KITE_API_KEY=your_kite_api_key
KITE_API_SECRET=your_kite_api_secret

# Paper Trading
PAPER_TRADING_INITIAL_CAPITAL=100000.0
```

## Usage Examples

### Paper Trading Example

```python
import requests

response = requests.post("http://127.0.0.1:8000/api/workflows/execute", json={
    "workflow": {
        "id": "test_workflow",
        "name": "Test Strategy",
        "nodes": [
            {
                "id": "node1",
                "type": "market-data",
                "data": {"symbol": "AAPL"}
            },
            {
                "id": "node2",
                "type": "buy-order",
                "data": {"symbol": "AAPL", "quantity": 10}
            }
        ],
        "edges": [{"id": "e1", "source": "node1", "target": "node2"}]
    },
    "tradingMode": "paper",
    "userId": "user_123",
    "portfolioId": "portfolio_123"
})

execution_id = response.json()["executionId"]
```

### Kite Live Trading Example

```python
# 1. Get login URL
login_response = requests.get("http://127.0.0.1:8000/api/broker/kite/login-url")
login_url = login_response.json()["login_url"]

# 2. User visits login_url and authorizes
# 3. Get request_token from callback URL

# 4. Exchange for access_token
token_response = requests.post("http://127.0.0.1:8000/api/broker/kite/access-token", json={
    "request_token": "request_token_from_callback"
})
access_token = token_response.json()["access_token"]

# 5. Execute workflow with Kite
response = requests.post("http://127.0.0.1:8000/api/workflows/execute", json={
    "workflow": {...},
    "tradingMode": "kite",
    "brokerConfig": {
        "access_token": access_token
    }
})
```

## Database Schema

The backend uses SQLite (default) or PostgreSQL for persistence:

- **executions** - Workflow execution records
- **execution_logs** - Execution log entries
- **orders** - Order records (paper + live)
- **positions** - Position tracking
- **broker_sessions** - Broker authentication tokens

## Error Handling

All endpoints return standard HTTP status codes:
- `200` - Success
- `400` - Bad Request (invalid input)
- `404` - Not Found
- `500` - Internal Server Error

Error responses include a `detail` field with error message:

```json
{
  "detail": "Error message here"
}
```

## Notes

- Paper trading is the default and safest mode for testing
- Kite integration requires valid API credentials
- All orders and positions are persisted to the database
- Execution logs are stored for debugging and auditing
- The backend supports all node types defined in the frontend workflow builder






