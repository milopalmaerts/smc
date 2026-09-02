from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import os
import random
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen
from typing import Any
import json


@dataclass
class Candle:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Zone:
    kind: str
    low: float
    high: float
    strength: int
    created_at: int
    touches: int = 0
    active: bool = True

    @property
    def midpoint(self) -> float:
        return (self.low + self.high) / 2


@dataclass
class Trade:
    side: str
    entry: float
    stop: float
    target: float
    size: float
    status: str
    pnl: float = 0.0
    opened_at: int = 0
    closed_at: int | None = None


class SupplyDemandBot:
    def __init__(self, start_worker: bool = True) -> None:
        self.lock = threading.RLock()
        self.random = random.Random(42)
        self.symbol = "BTC/USDT"
        self.timeframe = "5m"
        self.running = True
        self.paper_trading = True
        self.data_source = "Binance public feed"
        self.risk_per_trade = 1.0
        self.balance = 10_000.0
        self.start_balance = self.balance
        self.price = 67_420.0
        self.timeframes = ("5m", "15m", "1h")
        self.candles_by_timeframe: dict[str, list[Candle]] = {}
        self.last_candle_fetch = 0.0
        self.candles: list[Candle] = []
        self.zones: list[Zone] = []
        self.zones_by_timeframe: dict[str, list[Zone]] = {}
        self.trades: list[Trade] = []
        self.last_signal = "Waiting for a fresh zone retest"
        self.last_update = int(time.time())
        self.data_dir = Path(os.environ.get("DATA_DIR", "data"))
        self.state_file = self.data_dir / "bot_state.json"
        self._seed_market()
        self._refresh_zones()
        self._load_state()
        if start_worker:
            self.worker = threading.Thread(target=self._market_loop, daemon=True)
            self.worker.start()

    def _load_state(self) -> None:
        try:
            saved = json.loads(self.state_file.read_text())
        except (OSError, ValueError, json.JSONDecodeError):
            return
        self.symbol = saved.get("symbol", self.symbol)
        self.running = saved.get("running", self.running)
        self.risk_per_trade = saved.get("risk_per_trade", self.risk_per_trade)
        self.balance = saved.get("balance", self.balance)
        self.start_balance = saved.get("start_balance", self.start_balance)
        self.last_signal = saved.get("last_signal", self.last_signal)
        self.trades = [Trade(**trade) for trade in saved.get("trades", [])]

    def _save_state(self) -> None:
        payload = {
            "symbol": self.symbol,
            "running": self.running,
            "risk_per_trade": self.risk_per_trade,
            "balance": self.balance,
            "start_balance": self.start_balance,
            "last_signal": self.last_signal,
            "trades": [asdict(trade) for trade in self.trades],
        }
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = self.state_file.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(payload))
            tmp_path.replace(self.state_file)
        except OSError:
            pass

    def _seed_market(self) -> None:
        try:
            for timeframe in self.timeframes:
                self.candles_by_timeframe[timeframe] = self._fetch_klines(timeframe)
            self.candles = self.candles_by_timeframe["5m"]
            self.price = self.candles[-1].close
            self.last_candle_fetch = time.time()
            return
        except (OSError, ValueError, KeyError, IndexError, json.JSONDecodeError):
            self.data_source = "Fallback simulation - Binance feed unavailable"
        timestamp = int(time.time()) - 120 * 300
        price = self.price
        for index in range(120):
            wave = ((index % 30) - 15) * 8
            change = self.random.uniform(-90, 90) + wave
            candle_open = price
            candle_close = max(100, price + change)
            candle_high = max(candle_open, candle_close) + self.random.uniform(25, 100)
            candle_low = min(candle_open, candle_close) - self.random.uniform(25, 100)
            self.candles.append(Candle(timestamp, candle_open, candle_high, candle_low, candle_close, self.random.uniform(80, 220)))
            price = candle_close
            timestamp += 300
        self.price = self.candles[-1].close
        self.candles_by_timeframe = {timeframe: self.candles for timeframe in self.timeframes}

    def _fetch_klines(self, timeframe: str) -> list[Candle]:
        request = Request(
            f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval={timeframe}&limit=180",
            headers={"User-Agent": "SupplyDemandBot/1.0"},
        )
        with urlopen(request, timeout=8) as response:
            rows = json.loads(response.read())
        return [
            Candle(int(row[0] / 1000), float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5]))
            for row in rows
        ]

    def _market_loop(self) -> None:
        while True:
            time.sleep(4)
            with self.lock:
                if self.running:
                    self._tick()

    def _tick(self) -> None:
        try:
            request = Request(
                "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
                headers={"User-Agent": "SupplyDemandBot/1.0"},
            )
            with urlopen(request, timeout=5) as response:
                self.price = float(json.loads(response.read())["price"])
            self.data_source = "Binance public feed"
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            self.data_source = "Fallback simulation - Binance feed unavailable"
            self.price = max(100, self.price + self.random.uniform(-115, 115))
        if time.time() - self.last_candle_fetch >= 15 and self.data_source == "Binance public feed":
            try:
                for timeframe in self.timeframes:
                    self.candles_by_timeframe[timeframe] = self._fetch_klines(timeframe)
                self.candles = self.candles_by_timeframe["5m"]
                self.last_candle_fetch = time.time()
            except (OSError, ValueError, KeyError, IndexError, json.JSONDecodeError):
                self.data_source = "Live ticker only - candle refresh failed"
        candle = self.candles[-1]
        self._refresh_zones()
        self._manage_trade(candle)
        self._look_for_entry()
        self.last_update = candle.timestamp
        self._save_state()

    def _refresh_zones(self) -> None:
        self.zones_by_timeframe = {
            timeframe: self._discover_zones(candles)
            for timeframe, candles in self.candles_by_timeframe.items()
        }
        self.zones = self.zones_by_timeframe.get(self.timeframe, [])

    def _discover_zones(self, candles: list[Candle]) -> list[Zone]:
        if len(candles) < 7:
            return []
        discovered: list[Zone] = []
        for index in range(2, len(candles) - 2):
            current = candles[index]
            window = candles[index - 2:index + 3]
            if current.low == min(item.low for item in window):
                width = max(35, (current.high - current.low) * 0.65)
                strength = min(96, 58 + int(current.volume / 10))
                discovered.append(Zone("demand", current.low, current.low + width, strength, current.timestamp))
            if current.high == max(item.high for item in window):
                width = max(35, (current.high - current.low) * 0.65)
                strength = min(96, 58 + int(current.volume / 10))
                discovered.append(Zone("supply", current.high - width, current.high, strength, current.timestamp))
        zones = self._merge_zones(discovered)
        for zone in zones:
            zone.touches = self._count_retests(zone, candles)
        return [zone for zone in zones if zone.touches <= 1][-4:]

    def _count_retests(self, zone: Zone, candles: list[Candle]) -> int:
        """Count separate candle visits to a zone after its pivot formed."""
        retests = 0
        was_inside = False
        for candle in candles:
            inside = candle.high >= zone.low and candle.low <= zone.high
            if candle.timestamp > zone.created_at and inside and not was_inside:
                retests += 1
            was_inside = inside
        return retests

    def _merge_zones(self, zones: list[Zone]) -> list[Zone]:
        result: list[Zone] = []
        for zone in zones:
            if any(existing.kind == zone.kind and abs(existing.midpoint - zone.midpoint) < 100 for existing in result):
                continue
            result.append(zone)
        return result

    MIN_REWARD_RISK = 1.5

    def _liquidity_target(self, side: str, entry: float, risk: float) -> float | None:
        """Aim for the nearest opposing zone (the first resting liquidity), falling
        back to a plain 2R target when there is nothing ahead of price yet."""
        if side == "long":
            pool = [zone.high for zone in self.zones if zone.kind == "supply" and zone.high > entry]
            target = min(pool) if pool else entry + risk * 2
        else:
            pool = [zone.low for zone in self.zones if zone.kind == "demand" and zone.low < entry]
            target = max(pool) if pool else entry - risk * 2
        if abs(target - entry) < risk * self.MIN_REWARD_RISK:
            return None
        return target

    def _look_for_entry(self) -> None:
        if any(trade.status == "open" for trade in self.trades):
            return
        for zone in reversed(self.zones):
            if not zone.active or not (zone.low <= self.price <= zone.high):
                continue
            width = zone.high - zone.low
            buffer = max(10, width * 0.15)
            if zone.kind == "demand":
                stop = zone.low - buffer
                risk = self.price - stop
                target = self._liquidity_target("long", self.price, risk)
                if target is None:
                    continue
                self._open_trade("long", self.price, stop, target)
                self.last_signal = f"Demand retest at ${self.price:,.0f}"
            else:
                stop = zone.high + buffer
                risk = stop - self.price
                target = self._liquidity_target("short", self.price, risk)
                if target is None:
                    continue
                self._open_trade("short", self.price, stop, target)
                self.last_signal = f"Supply retest at ${self.price:,.0f}"
            return

    def _open_trade(self, side: str, entry: float, stop: float, target: float) -> None:
        risk_cash = self.balance * self.risk_per_trade / 100
        size = risk_cash / abs(entry - stop)
        self.trades.insert(0, Trade(side, entry, stop, target, size, "open", opened_at=int(time.time())))

    def _manage_trade(self, candle: Candle) -> None:
        for trade in self.trades:
            if trade.status != "open":
                continue
            stopped = candle.low <= trade.stop if trade.side == "long" else candle.high >= trade.stop
            targeted = candle.high >= trade.target if trade.side == "long" else candle.low <= trade.target
            if stopped or targeted:
                exit_price = trade.stop if stopped else trade.target
                direction = 1 if trade.side == "long" else -1
                trade.pnl = (exit_price - trade.entry) * trade.size * direction
                trade.status = "closed"
                trade.closed_at = int(time.time())
                self.balance += trade.pnl

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            open_trade = next((trade for trade in self.trades if trade.status == "open"), None)
            closed = [trade for trade in self.trades if trade.status == "closed"]
            wins = len([trade for trade in closed if trade.pnl > 0])
            return {
                "symbol": self.symbol,
                "timeframe": self.timeframe,
                "timeframes": list(self.timeframes),
                "running": self.running,
                "paper_trading": self.paper_trading,
                "data_source": self.data_source,
                "price": round(self.price, 2),
                "balance": round(self.balance, 2),
                "pnl": round(self.balance - self.start_balance, 2),
                "risk_per_trade": self.risk_per_trade,
                "win_rate": round((wins / len(closed)) * 100, 1) if closed else 0,
                "trades": [asdict(trade) for trade in self.trades[:12]],
                "open_trade": asdict(open_trade) if open_trade else None,
                "zones": [asdict(zone) | {"midpoint": round(zone.midpoint, 2)} for zone in self.zones],
                "zones_by_timeframe": {
                    timeframe: [asdict(zone) | {"midpoint": round(zone.midpoint, 2)} for zone in zones]
                    for timeframe, zones in self.zones_by_timeframe.items()
                },
                "candles": [asdict(candle) for candle in self.candles[-40:]],
                "charts": {
                    timeframe: [asdict(candle) for candle in candles[-60:]]
                    for timeframe, candles in self.candles_by_timeframe.items()
                },
                "last_signal": self.last_signal,
                "last_update": datetime.fromtimestamp(self.last_update, timezone.utc).isoformat(),
            }

    def update_config(self, values: dict[str, Any]) -> None:
        with self.lock:
            if "running" in values:
                self.running = bool(values["running"])
            if "risk_per_trade" in values:
                self.risk_per_trade = min(5.0, max(0.1, float(values["risk_per_trade"])))
            if "symbol" in values and str(values["symbol"]).strip():
                self.symbol = str(values["symbol"]).upper().strip()
            self._save_state()


bot = SupplyDemandBot()
