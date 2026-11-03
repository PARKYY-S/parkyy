// PARKYY roams: when he has nothing to do he walks along the top of your windows (or the bottom of
// the screen), hops/flies between them, reads with glasses when a document is open, sleeps when you're away.
// The moment you talk to him (listening / thinking / speaking) he flies to his normal spot, big again.
// ONE character: this drives the same #bot face as always - no second pet window.
// Off: tray menu "Roam on desktop", or start with PARKYY_PET=0.  Uses globals of index.html: bot, mode, pinned, bf, GS, place.
(function () {
  'use strict';
  const pk = window.pk || {};
  const NS = 'http://www.w3.org/2000/svg';
  let enabled = true, fg = null, sysIdle = 0;
  let dragging = false, down = null;
  const R = { s: 'sit', px: 0, py: 0, tx: 0, ty: 0, until: 0, next: 0, fy: -1, fid: '', lean: 0, t: 0, face: 'idle', say: 0 };
  const FEET = 0.944;                                  // feet sit at 94% of the face picture's height
  const rs = () => Math.round(150 * GS());              // roaming size (baby is small, adult is big)
  const rnd = (a, b) => a + Math.random() * (b - a);
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const pick = a => a[(Math.random() * a.length) | 0];
  const now = () => performance.now();

  // ---------- extra drawing on PARKYY's body: feet, wings, jet, reading glasses + book ----------
  const css = document.createElement('style');
  css.textContent = `
  #bot.roam{transition:width .6s ease}
  #bot.roam #bubble{position:absolute;bottom:100%;left:50%;transform:translateX(-50%);display:none;white-space:normal;max-width:240px;width:max-content;margin-bottom:6px}
  #bot.roam.talk #bubble{display:block}
  #bot.roam svg{filter:drop-shadow(0 6px 10px rgba(0,0,0,.4))}
  #bot.roam .float{animation:none}
  .pf,.pw,.pj,.pg{display:none}
  #bot.roam .pf{display:inline}
  #bot.flying .pw,#bot.flying .pj{display:inline}
  #bot.reading .pg{display:inline}
  .pwl{transform-box:fill-box;transform-origin:100% 60%;animation:wlf .16s ease-in-out infinite alternate}
  .pwr{transform-box:fill-box;transform-origin:0% 60%;animation:wrf .16s ease-in-out infinite alternate}
  @keyframes wlf{from{transform:rotate(-14deg)}to{transform:rotate(18deg)}}
  @keyframes wrf{from{transform:rotate(14deg)}to{transform:rotate(-18deg)}}
  .pj{transform-box:fill-box;transform-origin:50% 0;animation:jt .12s ease-in-out infinite alternate}
  @keyframes jt{from{transform:scaleY(.7);opacity:.7}to{transform:scaleY(1.2);opacity:1}}
  #bot.walk .pfl{animation:ftl .42s ease-in-out infinite}
  #bot.walk .pfr{animation:ftl .42s ease-in-out infinite .21s}
  #bot.walk .pf{display:inline}
  .pfl,.pfr{transform-box:fill-box;transform-origin:50% 0}
  @keyframes ftl{50%{transform:translateY(-7px)}}
  #bot.walk svg{animation:wd .42s ease-in-out infinite;transform-origin:50% 100%}
  @keyframes wd{0%,100%{transform:rotate(-3deg)}50%{transform:rotate(3deg) translateY(-3px)}}
  #bot.flying.hover svg{animation:hv 1.6s ease-in-out infinite}
  @keyframes hv{50%{transform:translateY(-7px)}}
  .rheart{position:fixed;z-index:8;pointer-events:none;font-size:20px;animation:rh 1.3s ease-out forwards}
  @keyframes rh{0%{opacity:0;transform:translate(0,0) scale(.6)}15%{opacity:1}100%{opacity:0;transform:translate(var(--dx),-70px) scale(1.2)}}
  `;
  document.head.appendChild(css);

  function g(cls, html) { const e = document.createElementNS(NS, 'g'); e.setAttribute('class', cls); e.innerHTML = html; return e; }
  function decorate() {
    const fl = bf && bf.querySelector('.float'); if (!fl || fl.dataset.roam) return; fl.dataset.roam = '1';
    const first = fl.firstChild ? fl.firstChild.nextSibling : null;           // right after the ground shadow
    const back = [
      g('pj', '<ellipse cx="160" cy="306" rx="11" ry="16" fill="#FFB547" opacity=".85"/><ellipse cx="160" cy="302" rx="5" ry="9" fill="#FFF3C4"/>'),
      g('pw', '<path class="pwl" d="M118 206 Q56 170 30 218 Q64 232 118 244Z" fill="#9CC4FF" stroke="#3D7BFF" stroke-width="3"/><path class="pwr" d="M202 206 Q264 170 290 218 Q256 232 202 244Z" fill="#9CC4FF" stroke="#3D7BFF" stroke-width="3"/>'),
      g('pf', '<rect class="pfl" x="118" y="282" width="32" height="20" rx="10" fill="#1B3F8F" stroke="#3D7BFF"/><rect class="pfr" x="170" y="282" width="32" height="20" rx="10" fill="#1B3F8F" stroke="#3D7BFF"/>')
    ];
    back.forEach(n => fl.insertBefore(n, first));
    fl.appendChild(g('pg', '<circle cx="128" cy="139" r="27" fill="none" stroke="#FFB547" stroke-width="5"/><circle cx="192" cy="139" r="27" fill="none" stroke="#FFB547" stroke-width="5"/><path d="M155 137 Q160 131 165 137" fill="none" stroke="#FFB547" stroke-width="5"/>' +
      '<path d="M104 250 L104 238 Q132 230 160 242 Q188 230 216 238 L216 252 Q188 244 160 256 Q132 244 104 252Z" fill="#FFB6CF" stroke="#FF5C93" stroke-width="4" stroke-linejoin="round"/><path d="M160 242 L160 256" stroke="#FF5C93" stroke-width="3"/>'));
  }

  // ---------- where can he stand? ----------
  function floorOf() {
    const w = innerWidth, h = innerHeight;
    const desk = { id: 'desk', y: h - 8, x1: 70, x2: w - 70, win: false, reading: false };
    if (!fg || fg.none || fg.max || fg.min) return desk;
    if (fg.w > 340 && fg.y > 60 && fg.y < h - 140 && fg.x + fg.w > 100 && fg.x < w - 100) {
      const x1 = Math.max(fg.x + 40, 40), x2 = Math.min(fg.x + fg.w - 40, w - 40);
      if (x2 - x1 >= 200) return { id: 'w' + fg.id, y: fg.y, x1, x2, win: true, reading: !!fg.reading };
    }
    return desk;
  }

  function active() { return enabled && !dragging && mode === 'idle' && !bot.classList.contains('hidden'); }
  function setCls(c, on) { bot.classList.toggle(c, !!on); }
  function talk(text, ms) {
    document.getElementById('bT').textContent = text; document.getElementById('bS').textContent = '';
    setCls('talk', true); clearTimeout(R.say); R.say = setTimeout(() => setCls('talk', false), ms || 3000);
  }
  function hearts(n) {
    const r = bot.getBoundingClientRect();
    for (let i = 0; i < n; i++) setTimeout(() => {
      const h = document.createElement('div'); h.className = 'rheart'; h.textContent = pick(['💙', '💗', '✨']);
      h.style.left = (r.left + r.width / 2 + rnd(-24, 24)) + 'px'; h.style.top = (r.top + r.height * .2) + 'px';
      h.style.setProperty('--dx', rnd(-30, 30) + 'px'); document.body.appendChild(h); setTimeout(() => h.remove(), 1500);
    }, i * 120);
  }
  const HELLO = ['Hi Saud!', 'Need something?', 'Boop!', 'I\'m here!', 'Ask me anything'];
  const CHAT = ['Stretch your legs?', 'Water break?', 'You\'re doing great.', 'Want me to look something up?', 'I could draft that email…'];

  // ---------- going between roaming and the normal "hero" spot ----------
  let was = false;
  function enter() {
    const r = bot.getBoundingClientRect();
    R.px = r.left + r.width / 2; R.py = r.top + r.height * 0.5; R.s = 'sit'; R.fy = -1; R.fid = '';
    bot.classList.add('roam'); decorate(); R.next = now() + 1500;
  }
  function leave() {
    ['roam', 'walk', 'flying', 'hover', 'reading', 'talk'].forEach(c => bot.classList.remove(c));
    bot.style.transform = ''; R.s = 'sit';
    if (bf.dataset.m === 'sleeping') bf.dataset.m = 'idle';
    place();
  }
  function flyTo(x, y, hoverMs) { R.s = 'fly'; R.tx = x; R.ty = y; R.hold = hoverMs || 0; }

  function step(dt, t) {
    const f = floorOf(), s = rs();
    bot.style.width = s + 'px';
    // floor changed (you switched windows) -> fly there; same window moving -> ride along
    if (f.id !== R.fid) {
      R.fid = f.id; R.fy = f.y;
      if (R.s === 'fly' && !R.hold) { R.tx = clamp(R.tx, f.x1, f.x2); R.ty = f.y; }
      else flyTo(clamp(R.px, f.x1, f.x2), f.y, 0);
    }
    else if (R.s === 'sit' || R.s === 'walk') { R.py += (f.y - R.py) * Math.min(1, dt * 14); R.fy = f.y; }
    else R.fy = f.y;

    if (window.__roamHold && R.s === 'walk') R.s = 'sit';
    const asleep = sysIdle > 150 && (R.s === 'sit') && !window.__roamHold;
    if (asleep) { if (bf.dataset.m !== 'sleeping') bf.dataset.m = 'sleeping'; }
    else if (bf.dataset.m === 'sleeping') bf.dataset.m = 'idle';

    setCls('reading', R.s === 'sit' && f.win && f.reading && !asleep);
    setCls('walk', R.s === 'walk');
    setCls('flying', R.s === 'fly' || R.s === 'hover');
    setCls('hover', R.s === 'hover');
    let lean = 0;

    if (R.s === 'sit') {
      if (t > R.next && !asleep && !window.__roamHold && !(f.win && f.reading)) {
        const r = Math.random();
        if (r < 0.5 && f.x2 - f.x1 > 160) { R.tx = rnd(f.x1, f.x2); if (Math.abs(R.tx - R.px) > 50) R.s = 'walk'; }
        else if (r < 0.68) flyTo(rnd(120, innerWidth - 120), rnd(innerHeight * 0.18, Math.max(innerHeight * 0.18 + 10, f.y - s * 1.3)), rnd(2500, 6000));
        else if (r < 0.8 && sysIdle < 60) talk(pick(CHAT), 4200);
        R.next = t + rnd(2500, 7000);
      }
    } else if (R.s === 'walk') {
      const dir = Math.sign(R.tx - R.px) || 1; lean = dir * 5;
      R.px += dir * 85 * dt;
      if (R.px < f.x1) { R.px = f.x1; R.s = 'sit'; } else if (R.px > f.x2) { R.px = f.x2; R.s = 'sit'; }
      else if (Math.abs(R.tx - R.px) < 5) { R.s = 'sit'; R.next = t + rnd(2000, 5000); }
    } else if (R.s === 'fly') {
      const dx = R.tx - R.px, dy = R.ty - R.py, dist = Math.hypot(dx, dy);
      const sp = Math.min(dist * 5 + 60, 340) * dt;
      if (dist <= sp + 1) { R.px = R.tx; R.py = R.ty; if (R.hold > 0) { R.s = 'hover'; R.until = t + R.hold; } else { R.s = 'sit'; R.next = t + rnd(1500, 4000); } }
      else { R.px += dx / dist * sp; R.py += dy / dist * sp; }
      lean = clamp(dx / 40, -12, 12);
    } else if (R.s === 'hover') {
      if (t > R.until) { const f2 = floorOf(); flyTo(clamp(R.px + rnd(-200, 200), f2.x1, f2.x2), f2.y, 0); }
    }
    R.lean += (lean - R.lean) * Math.min(1, dt * 8);
    bot.style.left = (R.px - s / 2) + 'px';
    bot.style.top = (R.py - s * FEET) + 'px';
    bot.style.transform = 'rotate(' + R.lean.toFixed(1) + 'deg)';
    bot.style.transformOrigin = '50% 90%';
  }

  let last = now();
  function loop(t) {
    requestAnimationFrame(loop);
    const dt = Math.min(0.05, (t - last) / 1000); last = t;
    const on = active();
    if (on !== was) { was = on; if (on) enter(); else leave(); }
    if (on) { try { step(dt, t); } catch (e) { console.error('roam', e); } }
  }

  // ---------- poke / drag & drop ----------
  bot.addEventListener('pointerdown', e => { down = { x: e.clientX, y: e.clientY, t: now() }; });
  let lastMove = 0;
  bot.addEventListener('pointermove', e => {
    lastMove = now();
    if (dragging && e.buttons === 0) { drop(); return; }      // button was released somewhere we didn't hear about
    if (down && !dragging && enabled && bot.classList.contains('roam') && Math.hypot(e.clientX - down.x, e.clientY - down.y) > 6) {
      dragging = true; leaveDrag();
    }
  });
  function leaveDrag() { ['walk', 'flying', 'hover', 'reading'].forEach(c => bot.classList.remove(c)); }
  bot.addEventListener('pointerup', e => {
    const wasDrag = dragging; const isClick = down && !dragging && Math.hypot(e.clientX - down.x, e.clientY - down.y) < 6 && now() - down.t < 500;
    down = null;
    if (wasDrag) drop();
    else if (isClick && bot.classList.contains('roam')) { hearts(4); talk(pick(HELLO), 2500); }
  });
  // let go anywhere = he drops/flies down to the nearest floor
  function drop() {
    if (!dragging) return;
    const r = bot.getBoundingClientRect(); const cx = r.left + r.width / 2, cy = r.top + r.height * FEET;
    dragging = false; down = null; pinned = null; bot.classList.add('roam');
    R.px = cx; R.py = cy; R.fid = ''; R.s = 'sit'; was = true;
  }
  // never get stuck "being carried": the mouse can be released outside his window, or focus can move away
  ['pointercancel', 'lostpointercapture'].forEach(ev => bot.addEventListener(ev, () => setTimeout(drop, 0)));
  addEventListener('blur', drop);
  setInterval(() => { if (dragging && now() - lastMove > 4000) drop(); }, 1000);
  bot.addEventListener('dblclick', () => { pinned = null; });

  // ---------- hooks ----------
  function hook() {
    if (pk.onFg) pk.onFg(d => { fg = d; });
    if (pk.onIdle) pk.onIdle(s => { sysIdle = +s || 0; });
    if (pk.onRoam) pk.onRoam(on => { enabled = !!on; });
    if (pk.roamGet) pk.roamGet().then(v => { enabled = v !== false; }).catch(() => {});
  }
  // the page's own place() must leave the position alone while he's roaming
  const origPlace = place;
  window.place = function () { if (bot.classList.contains('roam') && enabled && mode === 'idle') return; return origPlace(); };
  try { place = window.place; } catch (_) {}
  hook();
  window.__roam = { R, get dragging() { return dragging; },
    hello() { hearts(4); talk(pick(HELLO), 2500); },
    mood(f, sub) { if (f === 'listening') talk('Listening…', 90000); else if (f === 'thinking') talk(sub || 'Thinking…', 90000); else if (f === 'idle') setCls('talk', false); },
    say(t) { if (!t) return; talk(String(t), Math.min(9000, 2500 + String(t).length * 60)); }, get enabled() { return enabled; }, set enabled(v) { enabled = v; }, floorOf, setFg: d => { fg = d; }, setIdle: s => { sysIdle = s; }, flyTo };
  requestAnimationFrame(loop);
})();
