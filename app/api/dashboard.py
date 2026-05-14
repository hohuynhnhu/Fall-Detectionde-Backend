"""
backend/app/api/dashboard.py
Serve HTML dashboard cho web browser
"""
from __future__ import annotations
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
import time

from ..db.database import get_db
from ..db.models import FallEventDB, PoseEventDB

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard(db: AsyncSession = Depends(get_db)):
    # Recent falls
    q = await db.execute(
        select(FallEventDB).order_by(desc(FallEventDB.timestamp)).limit(20))
    falls = q.scalars().all()

    # Stats
    total_q = await db.execute(select(func.count()).select_from(FallEventDB))
    total_falls = total_q.scalar() or 0

    rows_html = ""
    for f in falls:
        t = time.strftime("%H:%M:%S", time.localtime(f.timestamp))
        rows_html += f"""
        <tr>
          <td>{t}</td>
          <td>{f.camera_id}</td>
          <td>{f.state_before or '—'}</td>
          <td class="vel">{f.max_velocity:.0f} px/s</td>
          <td>{f.body_angle:.1f}°</td>
          <td>{f.confidence:.0%}</td>
        </tr>"""

    return HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fall Detection Dashboard</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg: #0c0c1a; --panel: #151525; --card: #1c1c30;
    --border: #28284a; --accent: #4a9eff; --danger: #ff3b3b;
    --ok: #3bff8a; --warn: #ffaa22; --text: #e0e0f0; --sub: #6868a0;
  }}
  body {{ background: var(--bg); color: var(--text);
          font-family: 'Courier New', monospace; padding: 20px; }}

  h1 {{ color: var(--accent); font-size: 1.4rem; margin-bottom: 4px; }}
  .subtitle {{ color: var(--sub); font-size: 0.75rem; margin-bottom: 24px; }}

  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px,1fr));
            gap: 12px; margin-bottom: 24px; }}
  .stat-card {{ background: var(--card); border: 1px solid var(--border);
                border-radius: 12px; padding: 20px; }}
  .stat-card .val {{ font-size: 2rem; font-weight: bold; color: var(--danger); }}
  .stat-card .lbl {{ font-size: 0.7rem; color: var(--sub); margin-top: 4px; }}
  #live-status .val {{ color: var(--ok); font-size: 1rem; }}

  .section {{ background: var(--card); border: 1px solid var(--border);
              border-radius: 12px; padding: 20px; margin-bottom: 20px; }}
  .section h2 {{ font-size: 0.8rem; color: var(--sub); margin-bottom: 14px;
                 text-transform: uppercase; letter-spacing: 1px; }}

  table {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; }}
  th {{ text-align: left; color: var(--sub); font-size: 0.7rem;
        padding: 6px 10px; border-bottom: 1px solid var(--border); }}
  td {{ padding: 8px 10px; border-bottom: 1px solid var(--border); }}
  tr:hover td {{ background: var(--panel); }}
  .vel {{ color: var(--danger); font-weight: bold; }}

  .config-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
  .field {{ display: flex; flex-direction: column; gap: 4px; }}
  .field label {{ font-size: 0.7rem; color: var(--sub); }}
  .field input {{ background: var(--panel); border: 1px solid var(--border);
                  border-radius: 6px; color: var(--text); padding: 6px 10px;
                  font-family: monospace; font-size: 0.85rem; }}
  .field input:focus {{ outline: none; border-color: var(--accent); }}

  button {{ background: var(--accent); color: #000; border: none;
            border-radius: 8px; padding: 10px 20px;
            font-family: monospace; font-size: 0.85rem;
            font-weight: bold; cursor: pointer; margin-top: 12px; }}
  button:hover {{ opacity: 0.85; }}
  .btn-danger {{ background: var(--danger); color: #fff; }}
  .btn-secondary {{ background: var(--border); color: var(--text); }}

  #alert-banner {{ display: none; background: var(--danger);
                   border-radius: 8px; padding: 12px 20px;
                   margin-bottom: 16px; font-weight: bold;
                   animation: pulse 1s ease-in-out infinite; }}
  @keyframes pulse {{ 0%,100%{{opacity:1}} 50%{{opacity:.7}} }}

  #log-box {{ background: var(--panel); border: 1px solid var(--border);
              border-radius: 8px; padding: 12px; height: 160px;
              overflow-y: auto; font-size: 0.75rem; line-height: 1.6; }}
  .log-fall {{ color: var(--danger); }}
  .log-info {{ color: var(--sub); }}
</style>
</head>
<body>

<div id="alert-banner">⚠ TÉ NGÃ PHÁT HIỆN!</div>

<h1>⚠ Fall Detection Dashboard</h1>
<p class="subtitle">MediaPipe Pose · YOLO · FastAPI Backend · Real-time WebSocket</p>

<div class="grid">
  <div class="stat-card">
    <div class="val" id="total-falls">{total_falls}</div>
    <div class="lbl">Tổng số lần té</div>
  </div>
  <div class="stat-card" id="live-status">
    <div class="val" id="live-state">---</div>
    <div class="lbl">Trạng thái hiện tại</div>
  </div>
  <div class="stat-card">
    <div class="val" id="live-vel" style="color:var(--warn)">— px/s</div>
    <div class="lbl">Vận tốc</div>
  </div>
  <div class="stat-card">
    <div class="val" id="live-angle" style="color:var(--text)">—°</div>
    <div class="lbl">Góc cơ thể</div>
  </div>
</div>

<!-- Config section -->
<div class="section">
  <h2>Điều chỉnh ngưỡng phát hiện</h2>
  <div class="config-grid">
    <div class="field">
      <label>Fall velocity threshold (px/s)</label>
      <input type="number" id="cfg-fall-vel" value="80" step="5">
    </div>
    <div class="field">
      <label>Góc nằm (°)</label>
      <input type="number" id="cfg-angle-lying" value="65" step="1">
    </div>
    <div class="field">
      <label>H/W ratio nằm</label>
      <input type="number" id="cfg-ratio-lying" value="0.55" step="0.05">
    </div>
    <div class="field">
      <label>Fall confirm frames</label>
      <input type="number" id="cfg-confirm" value="5" step="1">
    </div>
    <div class="field">
      <label>Walk velocity threshold (px/s)</label>
      <input type="number" id="cfg-walk-vel" value="20" step="5">
    </div>
    <div class="field">
      <label>Fall history window (frames)</label>
      <input type="number" id="cfg-history" value="30" step="5">
    </div>
  </div>
  <div style="display:flex;gap:10px">
    <button onclick="applyConfig()">↑ APPLY CONFIG</button>
    <button class="btn-secondary" onclick="loadConfig()">↓ LOAD FROM DB</button>
    <button class="btn-danger" onclick="resetConfig()">↺ RESET DEFAULTS</button>
  </div>
  <div id="cfg-status" style="margin-top:8px;font-size:0.75rem;color:var(--sub)"></div>
</div>

<!-- Event log -->
<div class="section">
  <h2>Live event log (WebSocket)</h2>
  <div id="log-box"></div>
</div>

<!-- Fall history table -->
<div class="section">
  <h2>Lịch sử té ngã gần đây</h2>
  <table>
    <thead>
      <tr>
        <th>Thời gian</th><th>Camera</th><th>Trước khi té</th>
        <th>Tốc độ max</th><th>Góc</th><th>Confidence</th>
      </tr>
    </thead>
    <tbody id="falls-tbody">{rows_html}</tbody>
  </table>
</div>

<script>
const CAMERA_ID = 'cam_0';

// ── WebSocket live feed ──────────────────────────────────────────────────
let ws;
function connectWS() {{
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${{proto}}://${{location.host}}/ws/live`);

  ws.onmessage = (e) => {{
    const d = JSON.parse(e.data);
    addLog(JSON.stringify(d), d.type === 'fall_alert' ? 'fall' : 'info');

    if (d.type === 'fall_alert') {{
      document.getElementById('alert-banner').style.display = 'block';
      document.getElementById('total-falls').textContent =
        parseInt(document.getElementById('total-falls').textContent || '0') + 1;
      setTimeout(() => document.getElementById('alert-banner').style.display='none', 5000);
      // Refresh table row
      const row = `<tr>
        <td>${{new Date(d.timestamp*1000).toLocaleTimeString()}}</td>
        <td>${{d.camera_id}}</td><td>—</td>
        <td class="vel">${{d.velocity?.toFixed(0)}} px/s</td>
        <td>${{d.angle?.toFixed(1)}}°</td><td>—</td>
      </tr>`;
      document.getElementById('falls-tbody').insertAdjacentHTML('afterbegin', row);
    }}
    if (d.state) document.getElementById('live-state').textContent = d.state;
    if (d.velocity !== undefined) document.getElementById('live-vel').textContent = Math.abs(d.velocity).toFixed(0) + ' px/s';
    if (d.body_angle !== undefined) document.getElementById('live-angle').textContent = d.body_angle.toFixed(1) + '°';
  }};

  ws.onclose = () => setTimeout(connectWS, 3000);
  ws.onerror = () => ws.close();
}}

function addLog(msg, type='info') {{
  const box = document.getElementById('log-box');
  const line = document.createElement('div');
  line.className = `log-${{type}}`;
  line.textContent = `${{new Date().toLocaleTimeString()}}  ${{msg}}`;
  box.insertBefore(line, box.firstChild);
  if (box.children.length > 100) box.lastChild.remove();
}}

// ── Config ────────────────────────────────────────────────────────────────
async function loadConfig() {{
  const r = await fetch(`/config/thresholds?camera_id=${{CAMERA_ID}}`);
  if (!r.ok) {{ setStatus('Lỗi load config'); return; }}
  const cfg = await r.json();
  document.getElementById('cfg-fall-vel').value   = cfg.fall_velocity_threshold;
  document.getElementById('cfg-angle-lying').value = cfg.body_angle_lying;
  document.getElementById('cfg-ratio-lying').value = cfg.aspect_ratio_lying;
  document.getElementById('cfg-confirm').value     = cfg.fall_confirm_frames;
  document.getElementById('cfg-walk-vel').value    = cfg.walk_velocity_threshold;
  document.getElementById('cfg-history').value     = cfg.fall_history_window;
  setStatus('✓ Config đã load');
}}

async function applyConfig() {{
  const body = {{
    fall_velocity_threshold : parseFloat(document.getElementById('cfg-fall-vel').value),
    body_angle_lying        : parseFloat(document.getElementById('cfg-angle-lying').value),
    aspect_ratio_lying      : parseFloat(document.getElementById('cfg-ratio-lying').value),
    fall_confirm_frames     : parseInt(document.getElementById('cfg-confirm').value),
    walk_velocity_threshold : parseFloat(document.getElementById('cfg-walk-vel').value),
    fall_history_window     : parseInt(document.getElementById('cfg-history').value),
    body_angle_sitting: 45, walk_knee_lift_threshold: 0.08,
    walk_alternating_window: 15, camera_index: 0,
    flip_horizontal: true, model_complexity: 1,
  }};
  const r = await fetch(`/config/thresholds?camera_id=${{CAMERA_ID}}`, {{
    method: 'PUT', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify(body),
  }});
  setStatus(r.ok ? '✓ Config đã apply — desktop sẽ sync sau 5s' : '✗ Lỗi apply');
}}

async function resetConfig() {{
  const r = await fetch(`/config/thresholds/reset?camera_id=${{CAMERA_ID}}`, {{method:'POST'}});
  if (r.ok) {{ await loadConfig(); setStatus('↺ Reset xong'); }}
}}

function setStatus(msg) {{
  const el = document.getElementById('cfg-status');
  el.textContent = msg;
  setTimeout(() => el.textContent = '', 4000);
}}

// Init
loadConfig();
connectWS();
</script>
</body>
</html>""")
