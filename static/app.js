const $ = (id) => document.getElementById(id);
let state = null;
let selectedTimeframe = '5m';
const money = (value) => `$${Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

async function load() {
  const response = await fetch('/api/status');
  state = await response.json();
  render();
}

async function configure(values) {
  await fetch('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(values) });
  await load();
}

function render() {
  $('price').textContent = money(state.price);
  $('priceChange').textContent = state.data_source;
  $('balance').textContent = money(state.balance);
  $('pnl').textContent = `${state.pnl >= 0 ? '+' : ''}${money(state.pnl)} total P&L`;
  $('winRate').textContent = `${state.win_rate}%`;
  const closed = state.trades.filter((trade) => trade.status === 'closed').length;
  $('tradeCount').textContent = `${closed} closed trade${closed === 1 ? '' : 's'}`;
  $('riskValue').textContent = Number(state.risk_per_trade || 1).toFixed(1);
  $('statusText').textContent = state.running ? 'Engine running' : 'Engine paused';
  $('statusDot').style.background = state.running ? 'var(--green)' : 'var(--yellow)';
  $('toggleButton').textContent = state.running ? 'Pause engine' : 'Resume engine';
  $('signal').textContent = state.last_signal;
  $('updated').textContent = `updated ${new Date(state.last_update).toLocaleTimeString()}`;
  const open = state.open_trade;
  $('position').textContent = open ? `${open.side.toUpperCase()} ${money(open.entry)}` : 'Flat';
  $('positionDetail').textContent = open ? `stop ${money(open.stop)} · target ${money(open.target)}` : 'No active setup';
  const selectedZones = state.zones_by_timeframe[selectedTimeframe] || state.zones;
  $('zones').innerHTML = selectedZones.slice().reverse().map((zone) => `<div class="zone ${zone.kind}"><div><strong>${zone.kind.toUpperCase()}</strong><small>${money(zone.low)} — ${money(zone.high)}</small></div><em>${zone.strength}% strength · ${zone.touches} tap</em></div>`).join('') || '<p class="eyebrow">Scanning for structure...</p>';
  $('trades').innerHTML = state.trades.map((trade) => `<tr><td class="${trade.side}">${trade.side}</td><td>${money(trade.entry)}</td><td>${money(trade.stop)}</td><td>${money(trade.target)}</td><td class="${trade.pnl >= 0 ? 'long' : 'short'}">${trade.status === 'open' ? '—' : `${trade.pnl >= 0 ? '+' : ''}${money(trade.pnl)}`}</td><td class="${trade.status}">${trade.status}</td></tr>`).join('') || '<tr><td colspan="6">No trades yet. Waiting for a zone retest.</td></tr>';
  drawChart();
}

function drawChart() {
  const canvas = $('chart');
  const rect = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  canvas.width = rect.width * ratio; canvas.height = rect.height * ratio;
  const ctx = canvas.getContext('2d'); ctx.scale(ratio, ratio);
  const width = rect.width, height = rect.height, candles = (state.charts[selectedTimeframe] || state.candles);
  const values = candles.flatMap((candle) => [candle.high, candle.low]);
  const min = Math.min(...values), max = Math.max(...values), pad = 18;
  const x = (index) => pad + index * (width - pad * 2) / (candles.length - 1);
  const y = (value) => height - pad - (value - min) / (max - min) * (height - pad * 2);
  ctx.clearRect(0, 0, width, height);
  ctx.strokeStyle = '#e6ebe3'; ctx.lineWidth = 1;
  for (let i = 1; i < 5; i++) { const gy = i * height / 5; ctx.beginPath(); ctx.moveTo(0, gy); ctx.lineTo(width, gy); ctx.stroke(); }
  const selectedZones = state.zones_by_timeframe[selectedTimeframe] || state.zones;
  selectedZones.forEach((zone) => { const top = y(zone.high), bottom = y(zone.low); ctx.fillStyle = zone.kind === 'demand' ? 'rgba(168,219,189,.28)' : 'rgba(231,174,163,.25)'; ctx.fillRect(0, top, width, bottom - top); });
  candles.forEach((candle, index) => { const px = x(index), bodyTop = y(Math.max(candle.open, candle.close)), bodyBottom = y(Math.min(candle.open, candle.close)); ctx.strokeStyle = candle.close >= candle.open ? '#39826b' : '#c76c5f'; ctx.fillStyle = ctx.strokeStyle; ctx.beginPath(); ctx.moveTo(px, y(candle.high)); ctx.lineTo(px, y(candle.low)); ctx.stroke(); ctx.fillRect(px - 2, bodyTop, 4, Math.max(2, bodyBottom - bodyTop)); });
  ctx.strokeStyle = '#172321'; ctx.lineWidth = 1.5; ctx.beginPath(); candles.forEach((candle, index) => { const px = x(index), py = y(candle.close); index ? ctx.lineTo(px, py) : ctx.moveTo(px, py); }); ctx.stroke();
}

$('toggleButton').addEventListener('click', () => configure({ running: !state.running }));
$('riskSlider').addEventListener('change', (event) => configure({ risk_per_trade: event.target.value }));
document.querySelectorAll('.timeframe').forEach((button) => button.addEventListener('click', () => {
  selectedTimeframe = button.dataset.timeframe;
  document.querySelectorAll('.timeframe').forEach((item) => item.classList.toggle('active', item === button));
  render();
}));
window.addEventListener('resize', () => state && drawChart());
load().catch(() => { $('statusText').textContent = 'Offline'; $('statusDot').style.background = 'var(--red)'; });
setInterval(load, 4000);
