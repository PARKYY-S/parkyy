// PARKYY hand-tracking (webcam gestures) - runs 100% on the laptop with Google's MediaPipe.
// The camera picture never leaves the laptop. Toggle with the ✋ button (top bar) or Ctrl+H.
//
//   ✋ open palm, hold still    -> PARKYY listens - just talk (stops when you stop)
//   👈👉 swipe open palm        -> swipe left: dashboard · swipe right: menu (again closes)
//   ☝️ point + 🤏 pinch          -> move a pink cursor over PARKYY and click (inside PARKYY only)
//   👍 thumbs up (hold)          -> "Yes" on PARKYY's question      👎 thumbs down -> "No"
//   ✊ fist (hold)               -> stop talking + close panels
//   🤟 love-you sign             -> PARKYY loves you back
(() => {
  const VER = '0.10.14';
  const CDN = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${VER}`;
  const MODEL = 'https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task';
  const $$ = id => document.getElementById(id);
  let rec = null, video = null, stream = null, on = false, lastT = -1, lastRun = 0;
  let held = { name: '', since: 0, fired: false }, cool = 0, pinchDown = false, swipeCool = 0;
  const trail = [];

  // ---- UI bits ----
  const css = document.createElement('style');
  css.textContent = `
  #handCam{position:fixed;left:14px;bottom:14px;cursor:grab;touch-action:none;user-select:none;width:176px;height:132px;border-radius:14px;overflow:hidden;z-index:40;
    border:1px solid rgba(255,143,196,.6);box-shadow:0 0 18px rgba(255,95,168,.35);display:none;background:#000}
  #handCam.drag{cursor:grabbing;opacity:.9}
  #handCam video{pointer-events:none;width:100%;height:100%;object-fit:cover;transform:scaleX(-1);opacity:.85}
  #handCam b{position:absolute;left:8px;bottom:6px;font:600 12px 'IBM Plex Sans',sans-serif;color:#fff;text-shadow:0 1px 3px #000}
  /* small mode: just a 40px bubble showing the gesture status - tracking keeps working */
  #handCam.mini{width:40px!important;height:40px!important;border-radius:50%;cursor:pointer}
  #handCam.mini video{opacity:0}
  #handCam.mini b{left:0;right:0;bottom:auto;top:9px;text-align:center;font-size:16px}
  #handCam i{position:absolute;right:6px;top:4px;width:20px;height:20px;border-radius:50%;background:rgba(0,0,0,.55);color:#fff;
    font:700 14px/19px sans-serif;text-align:center;font-style:normal;cursor:pointer}
  #handCam.mini i{display:none}
  #handCam.asleep{visibility:hidden}
  #handDot{position:fixed;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;z-index:60;pointer-events:none;display:none;
    background:radial-gradient(circle,#fff 0 25%,#ff5fa8 30% 60%,transparent 62%);box-shadow:0 0 16px #ff5fa8;transition:transform .08s}
  #handDot.pinch{transform:scale(.6)}`;
  document.head.appendChild(css);
  const cam = document.createElement('div'); cam.id = 'handCam'; cam.innerHTML = '<video autoplay muted playsinline></video><b>✋ starting…</b><i title="Make small">–</i>';
  let mini = true;
  try { mini = localStorage.getItem('pkCamMini') !== '0'; } catch (e) {}
  cam.classList.toggle('mini', mini);
  const dot = document.createElement('div'); dot.id = 'handDot';
  document.body.append(cam, dot);
  video = cam.querySelector('video');
  let lastLabel = '';
  const label = t => { lastLabel = t; cam.title = t; cam.querySelector('b').textContent = mini ? (Array.from(t)[0] || '✋') : t; };
  function setMini(v) {
    mini = v; cam.classList.toggle('mini', v);
    try { localStorage.setItem('pkCamMini', v ? '1' : '0'); } catch (e) {}
    label(lastLabel || '✋');
  }
  // hide the bubble completely while PARKYY is asleep (gestures still work)
  const lockEl = $$('lock');
  if (lockEl) {
    const sync = () => cam.classList.toggle('asleep', !lockEl.classList.contains('hidden'));
    new MutationObserver(sync).observe(lockEl, { attributes: true, attributeFilter: ['class'] }); sync();
  }

  const btn = document.createElement('button');
  btn.className = 'tbtn'; btn.id = 'bHands'; btn.title = 'Hand gestures (Ctrl+H)'; btn.setAttribute('aria-label', 'Hand gestures');
  btn.innerHTML = '<span style="font-size:17px;line-height:1">✋</span>';
  const lockB = $$('lockBtn'); lockB && lockB.parentNode.insertBefore(btn, lockB);
  btn.onclick = () => toggle();
  document.addEventListener('keydown', e => { if (e.ctrlKey && (e.key === 'h' || e.key === 'H')) { e.preventDefault(); toggle(); } });

  function note(t) { try { say(t, 'pk note'); } catch (e) {} }
  function mood(m, t) { try { setMode(m, t); setTimeout(() => { if (mode === m) setMode('idle'); }, 2200); } catch (e) {} }

  // ---- start / stop ----
  async function start() {
    label('✋ loading…'); cam.style.display = 'block';
    try {
      if (!rec) {
        const vision = await import(`${CDN}/vision_bundle.mjs`);
        const files = await vision.FilesetResolver.forVisionTasks(`${CDN}/wasm`);
        rec = await vision.GestureRecognizer.createFromOptions(files, {
          baseOptions: { modelAssetPath: MODEL, delegate: 'GPU' }, runningMode: 'VIDEO', numHands: 1,
          minHandDetectionConfidence: 0.35, minHandPresenceConfidence: 0.35, minTrackingConfidence: 0.35 });
      }
      stream = await openCam();
      video.srcObject = stream; await video.play();
      on = true; btn.classList.add('on'); label('✋ ready');
      note('✋ Hand-tracking on (' + camName + (camCount > 1 ? ' - click the preview to switch camera' : '') +
        '). Hold your hand up: ✋ wake · 👍/👎 yes/no · ☝️+🤏 click · swipe ✋ for panels · ✊ quiet.');
      try { localStorage.setItem('pkHands', '1'); } catch (e) {}
      requestAnimationFrame(loop);
    } catch (e) {
      stop(); note('Hand-tracking couldn\'t start: ' + (e && e.message ? e.message : e) +
        ' (needs the webcam and internet the first time).');
    }
  }
  let camIdx = null;
  async function openCam() {
    let cams = [];
    try { cams = (await navigator.mediaDevices.enumerateDevices()).filter(d => d.kind === 'videoinput'); } catch (e) {}
    if (camIdx === null) {
      try { const saved = localStorage.getItem('pkCam'); camIdx = cams.findIndex(c => c.deviceId === saved); } catch (e) { camIdx = -1; }
      if (camIdx < 0) camIdx = cams.findIndex(c => /usb|lapcare|external|webcam|hd pro|c9\d\d/i.test(c.label) && !/integrated/i.test(c.label));
      if (camIdx < 0) camIdx = 0;
    }
    const cam = cams[camIdx % Math.max(1, cams.length)];
    const s = await navigator.mediaDevices.getUserMedia({ audio: false,
      video: { width: 640, height: 480, frameRate: { ideal: 15, max: 20 }, ...(cam && cam.deviceId ? { deviceId: { exact: cam.deviceId } } : {}) } });
    try { if (cam) localStorage.setItem('pkCam', cam.deviceId); } catch (e) {}
    camName = cam && cam.label ? cam.label.replace(/\(.*?\)/g, '').trim().slice(0, 18) : 'camera';
    camCount = cams.length;
    return s;
  }
  let camName = '', camCount = 1;
  // ---- drag the preview anywhere (position is remembered); scroll on it to resize ----
  let dragged = false;
  (function () {
    try {
      const p = JSON.parse(localStorage.getItem('pkCamPos') || 'null');
      if (p) { cam.style.left = p.x + 'px'; cam.style.top = p.y + 'px'; cam.style.bottom = 'auto'; if (p.w) { cam.style.width = p.w + 'px'; cam.style.height = Math.round(p.w * .75) + 'px'; } }
    } catch (e) {}
    const save = () => { try { const r = cam.getBoundingClientRect();
      localStorage.setItem('pkCamPos', JSON.stringify({ x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width) })); } catch (e) {} };
    const keepIn = () => { const r = cam.getBoundingClientRect();
      cam.style.left = Math.max(0, Math.min(innerWidth - r.width, r.left)) + 'px';
      cam.style.top = Math.max(0, Math.min(innerHeight - r.height, r.top)) + 'px'; cam.style.bottom = 'auto'; };
    let sx = 0, sy = 0, ox = 0, oy = 0, down = false;
    cam.addEventListener('pointerdown', e => {
      const r = cam.getBoundingClientRect(); down = true; dragged = false;
      sx = e.clientX; sy = e.clientY; ox = r.left; oy = r.top; cam.setPointerCapture(e.pointerId);
    });
    cam.addEventListener('pointermove', e => {
      if (!down) return;
      const dx = e.clientX - sx, dy = e.clientY - sy;
      if (!dragged && Math.hypot(dx, dy) < 5) return;
      dragged = true; cam.classList.add('drag');
      cam.style.left = (ox + dx) + 'px'; cam.style.top = (oy + dy) + 'px'; cam.style.bottom = 'auto'; keepIn();
    });
    const end = () => { if (!down) return; down = false; cam.classList.remove('drag'); if (dragged) save(); };
    cam.addEventListener('pointerup', end); cam.addEventListener('pointercancel', end);
    cam.addEventListener('wheel', e => {
      e.preventDefault();
      const w = Math.max(120, Math.min(480, cam.getBoundingClientRect().width * (e.deltaY < 0 ? 1.1 : 0.9)));
      cam.style.width = w + 'px'; cam.style.height = Math.round(w * .75) + 'px'; keepIn(); save();
    }, { passive: false });
    addEventListener('resize', () => { if (cam.style.display !== 'none') keepIn(); });
  })();
  cam.onclick = async e => {                // click the bubble = big preview · "–" = small again · click big preview = next camera
    if (dragged) { dragged = false; return; }
    if (mini) { setMini(false); return; }
    if (e.target && e.target.tagName === 'I') { setMini(true); return; }
    if (!on || camCount < 2) return;
    camIdx = (camIdx + 1) % camCount;
    if (stream) stream.getTracks().forEach(t => t.stop());
    try { stream = await openCam(); video.srcObject = stream; await video.play(); note('📷 Using ' + camName + ' for hand-tracking.'); }
    catch (e) { note('That camera didn\'t work - click the preview again for the next one.'); }
  };
  function stop() {
    on = false; btn.classList.remove('on'); cam.style.display = 'none'; dot.style.display = 'none';
    if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
    try { localStorage.setItem('pkHands', '0'); } catch (e) {}
  }
  function toggle() { on ? stop() : start(); }

  // ---- actions ----
  const locked = () => { const l = $$('lock'); return l && !l.classList.contains('hidden'); };
  function clickAsk(yes) {
    const btns = [...document.querySelectorAll('#chat .askbtn')].reverse();
    const b = btns.find(x => yes ? /^(yes|yes, go!)/i.test(x.textContent) : /^(no|no thanks)/i.test(x.textContent));
    if (b) { b.click(); return true; }
    return false;
  }
  function act(g) {
    const now = performance.now();
    if (now < cool) return;
    cool = now + 1500;
    if (g === 'Open_Palm') {
      if (locked()) { try { unlock(); } catch (e) {} }
      else { try { listenNow(); } catch (e) { mood('listening', '✋ I see you!'); } }   // palm = talk to PARKYY
    } else if (g === 'Thumb_Up') { if (!clickAsk(true)) mood('happy', '👍'); }
    else if (g === 'Thumb_Down') { if (!clickAsk(false)) mood('idle', '👎'); }
    else if (g === 'Closed_Fist') {
      try { speechSynthesis.cancel(); if (curAudio) curAudio.pause(); } catch (e) {}
      try { setL(false); setR(false); } catch (e) {}
      mood('idle', '✊ Quiet mode');
    } else if (g === 'ILoveYou') { mood('happy', '🤟 Love you too, Saud!'); }
  }
  function swipe(dir) {
    cool = performance.now() + 800;                 // don't also fire "wake" right after a swipe
    try {
      if (dir === 'left') setR(R.classList.contains('shut'));
      else setL(L.classList.contains('shut'));
    } catch (e) {}
  }

  // ---- dark room? brighten the picture before looking for hands ----
  const cv = document.createElement('canvas'), cx2 = cv.getContext('2d', { willReadFrequently: true });
  let boost = 1, lastLum = 0;
  const tiny = document.createElement('canvas'); tiny.width = 32; tiny.height = 24;
  const tx = tiny.getContext('2d', { willReadFrequently: true });
  function frame() {
    const w = 320, h = 240;
    if (cv.width !== w) { cv.width = w; cv.height = h; }
    cx2.filter = boost > 1.05 ? `brightness(${boost}) contrast(1.15)` : 'none';
    cx2.drawImage(video, 0, 0, w, h);
    if (performance.now() - lastLum > 1000) {             // re-check the light once a second
      lastLum = performance.now();
      tx.drawImage(video, 0, 0, 32, 24);                  // tiny unfiltered copy to measure the light
      const d = tx.getImageData(0, 0, 32, 24).data; let sum = 0;
      for (let i = 0; i < d.length; i += 4) sum += d[i] * 0.3 + d[i + 1] * 0.59 + d[i + 2] * 0.11;
      const lum = sum / (d.length / 4);                   // 0 = black, 255 = white
      boost = Math.max(1, Math.min(3, 110 / Math.max(20, lum)));
      dark = lum < 45;
    }
    return cv;
  }
  let dark = false;

  // ---- the loop ----
  function loop() {
    if (!on) return;
    const t = performance.now();
    if (video.readyState >= 2 && video.currentTime !== lastT && t - lastRun > 80) {
      lastT = video.currentTime; lastRun = t;
      let res = null;
      try { res = rec.recognizeForVideo(frame(), performance.now()); } catch (e) {}
      handle(res);
    }
    requestAnimationFrame(loop);
  }
  // gesture smoothing: the model flickers frame to frame, so vote over the last ~0.6 s
  const votes = [];
  let quietUntil = 0;
  function stableGesture(name, now) {
    votes.push({ t: now, n: name }); while (votes.length && now - votes[0].t > 600) votes.shift();
    const c = {}; votes.forEach(v => { c[v.n] = (c[v.n] || 0) + 1; });
    let best = 'None', bn = 0; for (const k in c) if (c[k] > bn) { best = k; bn = c[k]; }
    return (votes.length >= 4 && bn / votes.length >= 0.6) ? best : (held.name || 'None');
  }
  function handle(res) {
    const lm = res && res.landmarks && res.landmarks[0];
    if (!lm) { label(dark ? '💡 too dark - turn a light on' : '🙈 no hand - raise it'); dot.style.display = 'none'; held = { name: '', since: 0, fired: false }; trail.length = 0; votes.length = 0; return; }
    const g = (res.gestures[0] && res.gestures[0][0]) || { categoryName: 'None', score: 0 };
    const raw = g.score > 0.4 ? g.categoryName : 'None';
    const now = performance.now();
    const name = stableGesture(raw, now);
    const tip = lm[8], thumb = lm[4];
    const x = 1 - tip.x, y = tip.y;                         // mirror like a selfie

    // swipe = quick, mostly-sideways move of the whole hand (not pointing / fist)
    const cx = 1 - (lm[0].x + lm[9].x) / 2, cy = (lm[0].y + lm[9].y) / 2;   // palm centre, mirrored
    trail.push({ t: now, x: cx, y: cy }); while (trail.length && now - trail[0].t > 450) trail.shift();
    if (trail.length >= 3 && raw !== 'Pointing_Up' && raw !== 'Closed_Fist' && now > swipeCool) {
      const f = trail[0], l = trail[trail.length - 1];
      const dx = l.x - f.x, dy = l.y - f.y;
      if (Math.abs(dx) > 0.16 && Math.abs(dx) > 2 * Math.abs(dy)) {
        swipeCool = now + 1000; quietUntil = now + 900; trail.length = 0; votes.length = 0;
        held = { name: '', since: now, fired: true };
        swipe(dx < 0 ? 'left' : 'right'); label(dx < 0 ? '👈 swipe' : '👉 swipe'); return;
      }
    }
    // a moving hand isn't "holding" a gesture
    const moving = trail.length > 1 && Math.hypot(trail[trail.length - 1].x - trail[0].x, trail[trail.length - 1].y - trail[0].y) > 0.05;

    // pointer + pinch-click (only inside PARKYY's own window)
    const pinch = Math.hypot(tip.x - thumb.x, tip.y - thumb.y) < 0.05;
    if (raw === 'Pointing_Up' || name === 'Pointing_Up' || pinch) {
      const px = Math.min(innerWidth - 2, Math.max(2, (x - 0.15) / 0.7 * innerWidth));
      const py = Math.min(innerHeight - 2, Math.max(2, (y - 0.15) / 0.6 * innerHeight));
      dot.style.display = 'block'; dot.style.left = px + 'px'; dot.style.top = py + 'px';
      dot.classList.toggle('pinch', pinch);
      if (pinch && !pinchDown) {
        dot.style.display = 'none';
        const el = document.elementFromPoint(px, py);
        dot.style.display = 'block';
        if (el && el.closest && !el.closest('#handCam')) { (el.closest('button,a,input,label,[onclick]') || el).click(); }
      }
      pinchDown = pinch;
      label(pinch ? '🤏 click' : '☝️ pointing');
      return;
    }
    pinchDown = false; dot.style.display = 'none';

    // hold a steady gesture ~0.7 s to trigger it (ignored right after a swipe)
    if (name !== held.name) held = { name, since: now, fired: false };
    if (moving) held.since = now;
    const icons = { Open_Palm: '✋', Thumb_Up: '👍', Thumb_Down: '👎', Closed_Fist: '✊', ILoveYou: '🤟', Victory: '✌️', None: '🖐' };
    const words = { Open_Palm: 'open hand - hold still', Thumb_Up: 'thumbs up', Thumb_Down: 'thumbs down', Closed_Fist: 'fist',
                    ILoveYou: 'love you', Victory: 'peace', None: 'hand seen - try a gesture' };
    const left = Math.max(0, 700 - (now - held.since));
    label((icons[name] || '🖐') + ' ' + (words[name] || name) + (!held.fired && name !== 'None' && name !== 'Victory' && left > 0 && left < 700 ? ' ' + '●'.repeat(1 + Math.floor((700 - left) / 175)) : ''));
    if (!held.fired && now > quietUntil && name !== 'None' && name !== 'Victory' && now - held.since > 700) {
      held.fired = true; act(name);
    }
  }

  try { if (localStorage.getItem('pkHands') === '1') setTimeout(start, 2500); } catch (e) {}
})();
