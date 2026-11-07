/*
 * Tiny data runtime for the GCC Health System Tracker.
 * Loads the JSON files in /data, runs the page's calculations, and redraws
 * every element marked data-draw="<name>" when data, filters or width change.
 * Filters (focus country, language) live in the URL, so any view can be shared:
 *   ?lang=ar&focus=QAT
 */
(function () {
  const SOURCES = {
    wb: 'data/gcc_worldbank.json',
    obesity: 'data/gcc_obesity_who.json',
    hale: 'data/gcc_hale_who.json',
    le_who: 'data/gcc_le_who.json',
    nursemid: 'data/gcc_nurse_midwife_who.json',
    national: 'data/national.json',
    proj: 'data/gcc_population_projections.json',
    outlook: 'data/outlook.json',
    meta: 'data/meta.json',
  };
  const DEFAULTS = { focus: 'SAU', lang: 'en', tab: 'snapshot', ob: '4', em: 'AE' };
  const ALLOWED = {
    tab: ['snapshot', 'outcomes', 'risk', 'financing', 'workforce', 'goals', 'outlook', 'official'],
    ob: ['0', '2', '4', '6', '8', '10'],
    em: ['AE', 'AE-AZ', 'AE-DU', 'AE-SH', 'AE-AJ', 'AE-UQ', 'AE-RK', 'AE-FJ'],
    focus: ['SAU', 'ARE', 'QAT', 'KWT', 'OMN', 'BHR'],
    lang: ['en', 'ar'],
  };

  const store = {}; // id -> {status, data, message}
  const calcs = {}; // id -> {inputs, fn}
  const calcCache = {};
  const draws = []; // [name, fn]
  const watchers = [];

  const fromUrl = () => {
    const q = new URLSearchParams(location.search);
    const p = { ...DEFAULTS };
    Object.keys(ALLOWED).forEach((k) => {
      const v = q.get(k);
      if (v && ALLOWED[k].includes(v)) p[k] = v;
    });
    return p;
  };
  let params = fromUrl();

  Object.keys(SOURCES).forEach((id) => (store[id] = { status: 'loading', data: [] }));

  function data(id) {
    if (store[id]) return store[id];
    const c = calcs[id];
    if (!c) return { status: 'missing', data: [] };
    const ins = c.inputs.map(data);
    if (ins.some((d) => d.status === 'error' || d.status === 'missing')) return { status: 'error', data: [] };
    if (ins.some((d) => d.status !== 'ok')) return { status: 'loading', data: [] };
    if (!calcCache[id]) {
      try {
        calcCache[id] = { status: 'ok', data: c.fn(...ins.map((d) => d.data)) };
      } catch (e) {
        console.error('Calculation failed:', id, e);
        calcCache[id] = { status: 'error', data: [], message: String(e) };
      }
    }
    return calcCache[id];
  }

  function redraw() {
    watchers.forEach((fn) => {
      try { fn(); } catch (e) { console.error(e); }
    });
    draws.forEach(([name, fn]) => {
      document.querySelectorAll(`[data-draw="${name}"]`).forEach((el) => {
        if (el.parentElement && el.parentElement.closest('[hidden]')) return;
        try { fn(el); } catch (e) { console.error('Draw failed:', name, e); }
      });
    });
  }

  let pending = false;
  const schedule = () => {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => { pending = false; redraw(); });
  };

  window.dash = {
    data,
    calc(id, def) { calcs[id] = def; },
    loader() {},
    draw(name, fn) { draws.push([name, fn]); },
    onData(fn) { watchers.push(fn); },
    params: () => ({ ...params }),
    setParams(next) {
      Object.entries(next).forEach(([k, v]) => {
        if (v == null) params[k] = DEFAULTS[k];
        else if (!ALLOWED[k] || ALLOWED[k].includes(v)) params[k] = v;
      });
      const q = new URLSearchParams();
      Object.keys(DEFAULTS).forEach((k) => { if (params[k] !== DEFAULTS[k]) q.set(k, params[k]); });
      const qs = q.toString();
      history.replaceState(null, '', location.pathname + (qs ? '?' + qs : '') + location.hash);
      schedule();
    },
    resetParams() { params = { ...DEFAULTS }; this.setParams({}); },
    setLink() {},
    refresh() {},
    colors: ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)',
             'var(--chart-5)', 'var(--chart-6)', 'var(--chart-7)', 'var(--chart-8)'],
  };

  // Load every source, then redraw. A cache-busting stamp keeps monthly refreshes visible.
  const stamp = new Date().toISOString().slice(0, 10);
  Object.entries(SOURCES).forEach(([id, url]) => {
    fetch(`${url}?v=${stamp}`)
      .then((r) => { if (!r.ok) throw new Error(r.status + ' ' + r.statusText); return r.json(); })
      .then((rows) => { store[id] = { status: 'ok', data: rows }; Object.keys(calcCache).forEach((k) => delete calcCache[k]); schedule(); })
      .catch((e) => { console.error('Failed to load', url, e); store[id] = { status: 'error', data: [], message: String(e) }; schedule(); });
  });

  let lastW = 0;
  window.addEventListener('resize', () => {
    const w = document.documentElement.clientWidth;
    if (Math.abs(w - lastW) > 4) { lastW = w; schedule(); }
  });
  window.addEventListener('DOMContentLoaded', () => { lastW = document.documentElement.clientWidth; schedule(); });
})();
