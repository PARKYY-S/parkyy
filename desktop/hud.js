// PARKYY HUD - a JARVIS-style live panel: system, context, mission, sentinel, security.
// Toggle with the ◉ button in the top bar or Ctrl+J. Also: a context-aware greeting when PARKYY wakes.
(function () {
  const $$ = id => document.getElementById(id);
  const H = () => ({ Authorization: 'Bearer ' + PK.token });

  const css = document.createElement('style');
  css.textContent = `
  #hud{position:fixed;right:16px;top:72px;bottom:16px;width:300px;border-radius:18px;padding:14px 14px 12px;z-index:3;overflow:auto;
    display:flex;flex-direction:column;gap:12px;font-size:12.5px;transition:transform .35s cubic-bezier(.2,.8,.2,1),opacity .35s}
  #hud.off{transform:translateX(330px);opacity:0;pointer-events:none}
  #hud h4{margin:0 0 6px;font:600 11px 'Chakra Petch',sans-serif;letter-spacing:.2em;color:var(--ice);opacity:.85}
  #hud .core{display:flex;align-items:center;gap:12px}
  #hud .ring{width:86px;height:86px;flex:none}
  #hud .ring .spin{transform-origin:50% 50%;animation:hudspin 9s linear infinite}
  #hud .ring .spin2{transform-origin:50% 50%;animation:hudspin 14s linear infinite reverse}
  @keyframes hudspin{to{transform:rotate(360deg)}}
  #hud .bar{height:6px;border-radius:3px;background:rgba(156,196,255,.15);overflow:hidden;margin:3px 0 7px}
  #hud .bar i{display:block;height:100%;background:linear-gradient(90deg,#3D7BFF,#9CC4FF);border-radius:3px;transition:width .6s}
  #hud .bar i.hot{background:linear-gradient(90deg,#FFB547,#FF5C93)}
  #hud .row{display:flex;justify-content:space-between;gap:8px}
  #hud .mono{font-family:'JetBrains Mono',monospace}
  #hud .step{display:flex;gap:6px;opacity:.9;margin:2px 0}
  #hud .step.doing{color:#FFB547;opacity:1}
  #hud .step.done{opacity:.6}
  #hud .sec{display:grid;grid-template-columns:1fr 1fr;gap:4px 8px}
  #hud .sec span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  #hud .pill{display:inline-block;padding:1px 8px;border-radius:9px;border:1px solid var(--line);font-size:11px;margin-right:4px}
  #hud .pill.warn{border-color:#FFB547;color:#FFB547}
  #hud .card{border-top:1px solid rgba(61,123,255,.25);padding-top:10px}
  #hud .dim{opacity:.65}`;
  document.head.appendChild(css);

  const hud = document.createElement('div');
  hud.id = 'hud'; hud.className = 'g off';
  hud.innerHTML = `
  <div class="core">
    <svg class="ring" viewBox="0 0 100 100" aria-hidden="true">
      <circle cx="50" cy="50" r="46" fill="none" stroke="rgba(61,123,255,.25)" stroke-width="1"/>
      <circle class="spin" cx="50" cy="50" r="40" fill="none" stroke="#3D7BFF" stroke-width="2" stroke-dasharray="18 8 4 8"/>
      <circle class="spin2" cx="50" cy="50" r="33" fill="none" stroke="#9CC4FF" stroke-width="1.2" stroke-dasharray="2 5"/>
      <circle id="hudArc" cx="50" cy="50" r="27" fill="none" stroke="#FFB547" stroke-width="4" stroke-linecap="round"
        stroke-dasharray="0 170" transform="rotate(-90 50 50)"/>
      <text id="hudPct" x="50" y="54" text-anchor="middle" font-family="Chakra Petch" font-size="14" fill="#EEF3FF">--</text>
    </svg>
    <div>
      <div class="disp" style="font-size:15px;font-weight:700;letter-spacing:.14em">PARKYY <span id="hudOn" style="color:#3DDC97">ONLINE</span></div>
      <div class="dim" id="hudTime"></div>
      <div id="hudModes" style="margin-top:5px"></div>
    </div>
  </div>
  <div><h4>SYSTEM</h4><div id="hudSys"></div></div>
  <div class="card"><h4>CONTEXT</h4><div id="hudCtx" class="dim">…</div></div>
  <div class="card"><h4>MISSION</h4><div id="hudMis" class="dim">No active mission</div></div>
  <div class="card"><h4>SECURITY</h4><div id="hudSec" class="sec"></div></div>`;
  document.body.appendChild(hud);

  const btn = document.createElement('button');
  btn.className = 'tbtn'; btn.id = 'bHud'; btn.title = 'HUD (Ctrl+J)'; btn.setAttribute('aria-label', 'Show HUD');
  btn.innerHTML = '<svg viewBox="0 0 24 24" width="20" height="20"><circle class="ic" cx="12" cy="12" r="8"/><circle class="ic" cx="12" cy="12" r="3"/><path class="ic" d="M12 2v3M12 19v3M2 12h3M19 12h3"/></svg>';
  const lockB = $$('lockBtn'); lockB && lockB.parentNode.insertBefore(btn, lockB);

  let on = false, timer = null;
  function show(v) {
    on = v; hud.classList.toggle('off', !v); btn.classList.toggle('on', v);
    try { localStorage.setItem('pkHud', v ? '1' : '0'); } catch (e) {}
    clearInterval(timer); if (v) { load(); timer = setInterval(load, 4000); }
  }
  btn.onclick = () => show(!on);
  document.addEventListener('keydown', e => { if (e.ctrlKey && (e.key === 'j' || e.key === 'J')) { e.preventDefault(); show(!on); } });

  const bar = (label, val, txt, hot) => `<div class="row"><span>${label}</span><span class="mono">${txt}</span></div>` +
    `<div class="bar"><i class="${hot ? 'hot' : ''}" style="width:${Math.max(2, Math.min(100, val || 0))}%"></i></div>`;
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  async function load() {
    let d;
    try { const r = await fetch(PK.api + '/hud', { headers: H() }); if (!r.ok) throw 0; d = await r.json(); }
    catch (e) { $$('hudOn').textContent = 'OFFLINE'; $$('hudOn').style.color = '#FF5C93'; return; }
    $$('hudOn').textContent = d.online === false ? 'NO INTERNET' : 'ONLINE';
    $$('hudOn').style.color = d.online === false ? '#FFB547' : '#3DDC97';
    $$('hudTime').textContent = d.time + (d.active_min ? ` · active ${Math.floor(d.active_min / 60)}h ${d.active_min % 60}m` : '');
    const cpu = d.cpu || 0;
    $$('hudArc').setAttribute('stroke-dasharray', `${(cpu / 100) * 170} 170`);
    $$('hudPct').textContent = cpu + '%';
    let s = bar('CPU', cpu, cpu + '%', cpu > 85) + bar('RAM', d.ram, (d.ram ?? '--') + '%', d.ram > 90);
    if (d.battery != null) s += bar('BATTERY', d.battery, d.battery + '%' + (d.charging ? ' ⚡' : ''), d.battery < 20 && !d.charging);
    if (d.disk_free_gb != null) s += `<div class="row"><span>DRIVE C FREE</span><span class="mono" style="color:${d.disk_free_gb < 5 ? '#FFB547' : 'inherit'}">${d.disk_free_gb} GB</span></div>`;
    $$('hudSys').innerHTML = s;
    const m = d.modes || {};
    $$('hudModes').innerHTML = (d.presence && d.presence !== 'normal' ? `<span class="pill">${esc(d.presence)}</span>` : '') +
      (m.style && m.style !== 'normal' ? `<span class="pill">${esc(m.style)}</span>` : '') +
      (m.safe ? '<span class="pill warn">SAFE</span>' : '') + (m.dry ? '<span class="pill warn">SIMULATION</span>' : '') + (m.guest ? '<span class="pill warn">GUEST</span>' : '') +
      (d.sentinel ? `<span class="pill">🧿 ${d.sentinel}</span>` : '');
    $$('hudCtx').innerHTML = `${esc(d.app || '—')}${d.project ? ` · <b>${esc(d.project)}</b>` : ''}` +
      (d.goals || []).map(g => `<div class="row" style="margin-top:6px"><span>🎯 ${esc(g.outcome)}</span><span class="mono">${g.pct}%</span></div>` +
        `<div class="bar"><i style="width:${Math.max(2, g.pct)}%"></i></div>`).join('');
    const mi = d.mission;
    if (mi) {
      const ic = { done: '✓', doing: '◐', todo: '○', failed: '✗', skipped: '–' };
      $$('hudMis').innerHTML = `<div style="color:#EEF3FF;margin-bottom:4px">${esc(mi.objective)}</div>` +
        `<div class="row"><span>${esc(mi.status.toUpperCase())}</span><span class="mono">${mi.pct}%</span></div>` +
        `<div class="bar"><i style="width:${mi.pct}%"></i></div>` +
        mi.steps.map(st => `<div class="step ${st.status}"><span class="mono">${ic[st.status] || '?'}</span><span>${esc(st.name)}</span></div>`).join('');
      $$('hudMis').classList.remove('dim');
    } else { $$('hudMis').textContent = 'No active mission'; $$('hudMis').classList.add('dim'); }
    $$('hudSec').innerHTML = (d.access || []).map(a => `<span title="${esc(a.name)}">${a.on ? '🟢' : '🔒'} ${esc(a.name)}</span>`).join('');
  }

  // slide over when the dashboard drawer is open on the right, and hide while PARKYY is locked
  const right = $$('right'), appEl = $$('app');
  const place = () => {
    hud.style.right = right && !right.classList.contains('shut') ? '392px' : '16px';
    hud.style.display = appEl && appEl.classList.contains('hidden') ? 'none' : '';
  };
  [right, appEl].forEach(el => el && new MutationObserver(place).observe(el, { attributes: true, attributeFilter: ['class'] }));
  place();

  try { if (localStorage.getItem('pkHud') === '1') setTimeout(() => show(true), 1500); } catch (e) {}

  // context-aware greeting when PARKYY wakes up (backend limits it to once every few hours)
  const lockEl = $$('lock');
  if (lockEl) {
    let wasLocked = !lockEl.classList.contains('hidden');
    new MutationObserver(async () => {
      const locked = !lockEl.classList.contains('hidden');
      if (wasLocked && !locked) {
        try {
          const r = await fetch(PK.api + '/greet', { headers: H() });
          const j = await r.json();
          if (j.text) setTimeout(() => { try { say(j.text, 'pk'); speak(j.text); } catch (e) {} }, 2600);
        } catch (e) {}
      }
      wasLocked = locked;
    }).observe(lockEl, { attributes: true, attributeFilter: ['class'] });
  }
})();
