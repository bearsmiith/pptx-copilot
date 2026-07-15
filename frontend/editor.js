/* WP10 — free canvas editor (shared by 단면도/슬라이드 탭).
   Edits are an override diff over engine geometry (inch units). The server
   re-renders authoritatively on save; here we do live client-side preview.
   Editor.open({container, toolbar, api, onSaved}) mounts into a modal. */
(function () {
  const PX = 96;
  let S = null; // active session state

  function h(tag, attrs, txt) {
    const e = document.createElement(tag);
    for (const k in (attrs || {})) e.setAttribute(k, attrs[k]);
    if (txt != null) e.textContent = txt;
    return e;
  }
  const clone = (o) => JSON.parse(JSON.stringify(o));

  async function open(opts) {
    const r = await fetch(`${opts.api}/node/${opts.nodeId}/editable_svg`);
    if (!r.ok) { alert('편집 SVG 로드 실패'); return; }
    const j = await r.json();
    S = {
      api: opts.api, nodeId: opts.nodeId, onSaved: opts.onSaved,
      container: opts.container, toolbar: opts.toolbar,
      ov: j.overrides && j.overrides.items ? clone(j.overrides)
        : { v: 1, items: {}, added: [] },
      sel: null, mode: 'select', undo: [], addSeq: 0,
    };
    S.ov.items = S.ov.items || {}; S.ov.added = S.ov.added || [];
    opts.container.innerHTML = j.svg;
    S.svg = opts.container.querySelector('svg');
    S.svg.style.userSelect = 'none';
    buildToolbar();
    wire();
  }

  function buildToolbar() {
    const tb = S.toolbar; tb.innerHTML = '';
    const btn = (label, fn, primary) => {
      const b = h('button', { class: primary ? '' : 'sec' }, label);
      b.style.cssText = 'font-size:12px;padding:4px 9px;margin-right:5px';
      b.onclick = fn; tb.appendChild(b); return b;
    };
    btn('＋텍스트', () => addElement('text'));
    btn('＋박스', () => addElement('rect'));
    btn('＋화살표', () => addElement('arrow'));
    btn('삭제', () => del());
    btn('되돌리기', () => undo());
    const grow = h('span'); grow.style.flex = '1'; tb.appendChild(grow);
    btn('저장 ▶', () => save(), true);
    const c = btn('취소', () => close());
    c.style.marginLeft = '4px';
    tb.style.display = 'flex';
  }

  function pushUndo() { S.undo.push(clone(S.ov)); if (S.undo.length > 40) S.undo.shift(); }
  function undo() { if (!S.undo.length) return; S.ov = S.undo.pop(); rerenderLocal(); }

  function eidOf(node) {
    while (node && node !== S.svg) {
      if (node.getAttribute && node.getAttribute('data-eid')) return node;
      node = node.parentNode;
    }
    return null;
  }

  function select(g) {
    if (S.sel) S.sel.classList.remove('__sel');
    S.sel = g;
    if (g) {
      g.classList.add('__sel');
      addSelStyle();
    }
  }
  function addSelStyle() {
    if (document.getElementById('__esel')) return;
    const st = h('style'); st.id = '__esel';
    st.textContent = '.__sel{outline:2px dashed #2f6fed;outline-offset:1px}';
    document.head.appendChild(st);
  }

  function wire() {
    let drag = null;
    S.svg.addEventListener('mousedown', (ev) => {
      const g = eidOf(ev.target);
      if (!g) { select(null); return; }
      select(g);
      drag = { x: ev.clientX, y: ev.clientY, moved: false,
               base: curDelta(g.getAttribute('data-eid')) };
      ev.preventDefault();
    });
    window.addEventListener('mousemove', (ev) => {
      if (!drag || !S.sel) return;
      const dxpx = ev.clientX - drag.x, dypx = ev.clientY - drag.y;
      if (Math.abs(dxpx) + Math.abs(dypx) > 2) drag.moved = true;
      const sc = S.svg.getBoundingClientRect().width / 1280;
      const dx = drag.base.dx + dxpx / (PX * sc);
      const dy = drag.base.dy + dypx / (PX * sc);
      S.sel.setAttribute('transform', `translate(${dx * PX},${dy * PX})`);
      S._pending = { eid: S.sel.getAttribute('data-eid'), dx, dy };
    });
    window.addEventListener('mouseup', () => {
      if (drag && drag.moved && S._pending) {
        pushUndo();
        const it = S.ov.items[S._pending.eid] || {};
        it.dx = S._pending.dx; it.dy = S._pending.dy;
        S.ov.items[S._pending.eid] = it;
      }
      drag = null; S._pending = null;
    });
    S.svg.addEventListener('dblclick', (ev) => {
      const g = eidOf(ev.target); if (!g) return;
      const eid = g.getAttribute('data-eid');
      const cur = g.textContent || '';
      const nv = prompt('텍스트', cur);
      if (nv == null) return;
      pushUndo();
      (S.ov.items[eid] = S.ov.items[eid] || {}).text = nv;
      const t = g.querySelector('div') || g.querySelector('text');
      if (t) t.textContent = nv;
    });
    window.addEventListener('keydown', S._key = (ev) => {
      if (S && (ev.key === 'Delete' || ev.key === 'Backspace') && S.sel &&
          document.activeElement.tagName !== 'INPUT') { ev.preventDefault(); del(); }
    });
  }

  function curDelta(eid) {
    const it = S.ov.items[eid] || {}; return { dx: it.dx || 0, dy: it.dy || 0 };
  }

  function del() {
    if (!S.sel) return;
    const eid = S.sel.getAttribute('data-eid');
    pushUndo();
    (S.ov.items[eid] = S.ov.items[eid] || {}).hidden = true;
    S.sel.style.display = 'none'; select(null);
  }

  function addElement(type) {
    pushUndo();
    const cx = 6.5, cy = 2.5 + S.addSeq * 0.1; S.addSeq++;
    let a;
    if (type === 'text') {
      const t = prompt('추가할 텍스트', '주석'); if (t == null) return;
      a = { type: 'text', x: cx, y: cy, w: 2.4, text: t, size: 15 };
    } else if (type === 'rect') {
      a = { type: 'rect', x: cx, y: cy, w: 1.4, h: 0.6, role: 'accent1', label: '' };
    } else {
      a = { type: 'arrow', x1: cx, y1: cy + 0.4, x2: cx + 1.4, y2: cy };
    }
    S.ov.added.push(a);
    drawAdded(a, S.ov.added.length - 1);
  }

  // minimal client-side preview of added elements (server render is authoritative)
  function drawAdded(a, idx) {
    const NS = 'http://www.w3.org/2000/svg';
    const g = document.createElementNS(NS, 'g');
    g.setAttribute('data-added', idx);
    if (a.type === 'text') {
      const t = document.createElementNS(NS, 'text');
      t.setAttribute('x', a.x * PX); t.setAttribute('y', a.y * PX);
      t.setAttribute('font-size', a.size || 15); t.setAttribute('fill', '#1f2a44');
      t.textContent = a.text; g.appendChild(t);
    } else if (a.type === 'rect') {
      const r = document.createElementNS(NS, 'rect');
      r.setAttribute('x', a.x * PX); r.setAttribute('y', a.y * PX);
      r.setAttribute('width', a.w * PX); r.setAttribute('height', a.h * PX);
      r.setAttribute('rx', 6); r.setAttribute('fill', '#dbe7fd');
      r.setAttribute('stroke', '#2f6fed'); g.appendChild(r);
    } else {
      const l = document.createElementNS(NS, 'line');
      l.setAttribute('x1', a.x1 * PX); l.setAttribute('y1', a.y1 * PX);
      l.setAttribute('x2', a.x2 * PX); l.setAttribute('y2', a.y2 * PX);
      l.setAttribute('stroke', '#2f6fed'); l.setAttribute('stroke-width', 2.5);
      l.setAttribute('marker-end', 'url(#arrow)'); g.appendChild(l);
    }
    S.svg.appendChild(g);
  }

  function rerenderLocal() {
    // reload the base editable svg + reapply from ov (simplest: refetch)
    open({ api: S.api, nodeId: S.nodeId, container: S.container,
           toolbar: S.toolbar, onSaved: S.onSaved });
  }

  async function save() {
    const r = await fetch(`${S.api}/edit_node`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ node_id: S.nodeId, overrides: S.ov }),
    });
    if (!r.ok) { alert('저장 실패'); return; }
    const payload = await r.json();
    const cb = S.onSaved; close();
    if (cb) cb(payload);
  }

  function close() {
    if (S && S._key) window.removeEventListener('keydown', S._key);
    if (S) S.toolbar.style.display = 'none';
    S = null;
  }

  window.Editor = { open, close };
})();
