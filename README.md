# SupplyDemand Bot

A small, dependency-free supply and demand zone trading bot with a live paper-trading dashboard.

## Run

```powershell
python server.py
```

Open http://127.0.0.1:8000.

## Deploy to Railway

Push this repo to Railway (via the CLI or by connecting the GitHub repo). It runs as a
regular long-lived process (`server.py`), started via `railway.json` / `Procfile`.

- Railway sets `PORT` automatically; `server.py` binds to `0.0.0.0:$PORT`.
- To persist the paper-trading account (balance, trades, risk setting) across deploys and
  restarts, attach a Railway **volume** and mount it at `/data`, then set the env var:

  ```
  DATA_DIR=/data
  ```

  The bot writes `bot_state.json` to that directory after every tick and config change, and
  reloads it on startup. Without a mounted volume, state resets on every redeploy/restart.

## Deploy to Vercel

```powershell
vercel --prod
```

The Vercel deployment serves the dashboard statically and runs the Binance status/config API as a serverless Python function. Pin the function region away from the US in `vercel.json` (`"regions": ["fra1"]`) — Binance's public API returns 451 for US-region requests. Note: serverless instances are ephemeral, so `DATA_DIR` persistence does not survive cold starts there; use Railway with a volume for a durable account.

The bot simulates candles, identifies local pivot zones, enters on zone retests, and manages a stop/target using 1% risk per paper trade. It is intentionally paper-only. Before using real funds, connect a vetted exchange adapter, add authentication and order safeguards, and backtest the strategy against historical data.

## API

- `GET /api/status` returns candles, zones, account metrics, and trades.
- `POST /api/config` accepts `{"running": true|false, "risk_per_trade": 1.0, "symbol": "BTC/USDT"}`.
