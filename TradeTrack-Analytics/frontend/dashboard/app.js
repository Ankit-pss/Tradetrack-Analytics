/* ==========================================================================
   TradeTrack Analytics — dashboard application
   --------------------------------------------------------------------------
   Zero dependencies. Charts are hand-rendered SVG, which keeps the dashboard a
   single self-contained folder that opens from the filesystem with no build
   step, no CDN and no network access.

   Architecture:
     STATE      current filter selections
     filter()   one scan over the columnar arrays -> array of row indices
     agg*()     small aggregation helpers over an index list
     draw*()    pure render functions: (container, data) -> SVG
     render()   recompute everything and repaint

   The columnar payload in data.js means filtering is a single pass over plain
   arrays with integer comparisons, so a full repaint over 10,000+ trades stays
   well inside one animation frame.
   ========================================================================== */

'use strict';

const D = TT_DATA;
const C = D.cols;
const DIMS = D.dims;

/* ---------------------------------------------------------------- theme */
const CO = {
  profit: '#0ca30c',
  loss: '#d03b3b',
  blue: '#3987e5',
  orange: '#d95926',
  aqua: '#199e70',
  yellow: '#c98500',
  magenta: '#d55181',
  violet: '#9085e9',
  text: '#f2f4f7',
  text2: '#a8b0bd',
  text3: '#7c8698',
  grid: '#1e242e',
  axis: '#2a323f',
  surface: '#12161c'
};

/* Fixed hue per asset so an instrument keeps its colour across every chart. */
const SERIES = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#9085e9'];

/* ------------------------------------------------------------ formatting */
const money = (v, dp = 0) => {
  const a = Math.abs(v), s = v < 0 ? '-' : '';
  if (a >= 1e6) return `${s}$${(a / 1e6).toFixed(2)}M`;
  if (a >= 1e3) return `${s}$${(a / 1e3).toFixed(a >= 1e5 ? 0 : 1)}K`;
  return `${s}$${a.toFixed(dp)}`;
};
const signed = (v) => (v >= 0 ? '+' : '') + money(v);
const pct = (v, dp = 1) => `${v.toFixed(dp)}%`;
const num = (v) => v.toLocaleString('en-US');

const dayToDate = (() => {
  const origin = new Date(D.dateOrigin + 'T00:00:00Z');
  return (d) => new Date(origin.getTime() + d * 86400000);
})();
const fmtDate = (dt) => dt.toISOString().slice(0, 10);
const fmtDateShort = (dt) => dt.toLocaleDateString('en-US',
  { day: 'numeric', month: 'short', year: '2-digit', timeZone: 'UTC' });
const monthKey = (dt) => dt.toISOString().slice(0, 7);

const durText = (mins) => {
  if (mins < 60) return `${Math.round(mins)}m`;
  if (mins < 1440) return `${(mins / 60).toFixed(1)}h`;
  return `${(mins / 1440).toFixed(1)}d`;
};

/* ------------------------------------------------------------------ state */
const STATE = {
  from: 0,
  to: Math.max(...C.day),
  asset: new Set(),
  strategy: new Set(),
  trading_session: new Set(),
  trade_type: new Set(),
  data_source: new Set()
};

/* A filter pass: one linear scan, integer comparisons only. */
function filter() {
  const out = [];
  const { from, to, asset, strategy, trading_session, trade_type, data_source } = STATE;
  const aOn = asset.size > 0, sOn = strategy.size > 0;
  const seOn = trading_session.size > 0, tOn = trade_type.size > 0;
  const dsOn = data_source.size > 0;

  for (let i = 0; i < D.n; i++) {
    const d = C.day[i];
    if (d < from || d > to) continue;
    if (aOn && !asset.has(C.asset[i])) continue;
    if (sOn && !strategy.has(C.strategy[i])) continue;
    if (seOn && !trading_session.has(C.trading_session[i])) continue;
    if (tOn && !trade_type.has(C.trade_type[i])) continue;
    if (dsOn && !data_source.has(C.data_source[i])) continue;
    out.push(i);
  }
  return out;
}

/* ------------------------------------------------------------ aggregation */
function summarise(idx) {
  let gross = 0, fees = 0, net = 0, wins = 0, rr = 0, rrn = 0, dur = 0, rsum = 0;
  const durs = [];
  for (const i of idx) {
    gross += C.gross[i];
    fees += C.fees[i];
    net += C.net[i];
    wins += C.win[i];
    rr += C.rr[i]; rrn++;
    // dur === -1 means no exit time was recorded; averaging it in would report
    // a holding time shorter than anything that actually happened.
    if (C.dur[i] >= 0) { dur += C.dur[i]; durs.push(C.dur[i]); }
    rsum += C.r[i];
  }
  const n = idx.length;
  durs.sort((a, b) => a - b);
  return {
    n, gross, fees, net, wins, losses: n - wins,
    winRate: n ? (wins / n) * 100 : 0,
    avgRR: rrn ? rr / rrn : 0,
    avgR: n ? rsum / n : 0,
    durN: durs.length,
    avgDur: durs.length ? dur / durs.length : 0,
    medDur: durs.length ? durs[Math.floor(durs.length / 2)] : 0
  };
}

/** Group an index list by a key function; returns sorted [{key, ...stats}]. */
function groupBy(idx, keyFn) {
  const map = new Map();
  for (const i of idx) {
    const k = keyFn(i);
    let g = map.get(k);
    if (!g) { g = { key: k, n: 0, net: 0, wins: 0, r: 0, risk: 0 }; map.set(k, g); }
    g.n++; g.net += C.net[i]; g.wins += C.win[i]; g.r += C.r[i]; g.risk += C.risk[i];
  }
  return [...map.values()].map(g => ({
    ...g,
    winRate: g.n ? (g.wins / g.n) * 100 : 0,
    avgR: g.n ? g.r / g.n : 0,
    avgRisk: g.n ? g.risk / g.n : 0
  }));
}

/** Daily P&L series over the filtered set, ascending by date. */
function dailySeries(idx) {
  const map = new Map();
  for (const i of idx) {
    const d = C.day[i];
    map.set(d, (map.get(d) || 0) + C.net[i]);
  }
  const days = [...map.keys()].sort((a, b) => a - b);
  let cum = 0;
  return days.map(d => {
    cum += map.get(d);
    return { day: d, pnl: map.get(d), cum };
  });
}

/* Deepest peak-to-trough decline of the daily equity curve, selected on
   PERCENTAGE of the running peak (the scale-free measure) rather than on
   dollars. This matches python/kpi_engine.py and SQL query 16 exactly, so all
   three layers of the project report the same drawdown. */
/* Opening capital for whatever the Source filter currently admits. The two
   books are funded very differently ($430K simulated desk vs a $10K live
   account), so a fixed base would put the real trades on a denominator ~40x
   too large and report their drawdown as 0.00%. */
function activeCapital() {
  const byS = D.capitalBySource;
  if (!byS) return D.startingCapital;
  const chosen = STATE.data_source.size
    ? [...STATE.data_source].map(i => DIMS.data_source[i])
    : Object.keys(byS);
  const total = chosen.reduce((a, k) => a + (byS[k] || 0), 0);
  return total || D.startingCapital;
}

function maxDrawdown(series) {
  let peak = -Infinity, worstPct = 0, worstUsd = 0;
  const base = activeCapital();
  for (const p of series) {
    const eq = base + p.cum;
    if (eq > peak) peak = eq;
    const dd = peak - eq;
    const ddPct = peak > 0 ? (dd / peak) * 100 : 0;
    if (ddPct > worstPct) { worstPct = ddPct; worstUsd = dd; }
  }
  return { usd: worstUsd, pct: worstPct };
}

/* ------------------------------------------------------------------- SVG */
const NS = 'http://www.w3.org/2000/svg';
const el = (tag, attrs = {}) => {
  const n = document.createElementNS(NS, tag);
  for (const k in attrs) n.setAttribute(k, attrs[k]);
  return n;
};

function svgFor(container) {
  container.innerHTML = '';
  const h = +container.dataset.h || 240;
  const w = Math.max(container.clientWidth || 600, 260);
  const svg = el('svg', { viewBox: `0 0 ${w} ${h}`, height: h,
                          preserveAspectRatio: 'none', role: 'img' });
  container.appendChild(svg);
  return { svg, w, h };
}

function niceTicks(min, max, count = 5) {
  if (min === max) { min -= 1; max += 1; }
  const span = max - min;
  const raw = span / count;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  const step = (norm >= 7.5 ? 10 : norm >= 3.5 ? 5 : norm >= 1.5 ? 2 : 1) * mag;
  const out = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(v);
  return out;
}

/* Rounded rect with only the DATA END rounded, so bars meet the zero
   baseline flat instead of floating off it. */
function barPath(x, y, w, h, r, up) {
  r = Math.min(r, w / 2, Math.abs(h));
  if (Math.abs(h) < 0.6) return `M${x} ${y}h${w}v${h}h${-w}Z`;
  return up
    ? `M${x} ${y + h}h${w}v${-h + r}a${r} ${r} 0 0 0 ${-r} ${-r}h${-(w - 2 * r)}a${r} ${r} 0 0 0 ${-r} ${r}v${h - r}Z`
    : `M${x} ${y}h${w}v${h - r}a${r} ${r} 0 0 1 ${-r} ${r}h${-(w - 2 * r)}a${r} ${r} 0 0 1 ${-r} ${-r}v${-(h - r)}Z`;
}

function hBarPath(x, y, w, h, r, right) {
  r = Math.min(r, h / 2, Math.abs(w));
  if (Math.abs(w) < 0.6) return `M${x} ${y}v${h}h${w}v${-h}Z`;
  return right
    ? `M${x} ${y}h${w - r}a${r} ${r} 0 0 1 ${r} ${r}v${h - 2 * r}a${r} ${r} 0 0 1 ${-r} ${r}h${-(w - r)}Z`
    : `M${x} ${y}h${w + r}a${r} ${r} 0 0 0 ${-r} ${r}v${h - 2 * r}a${r} ${r} 0 0 0 ${r} ${r}h${-(w + r)}Z`;
}

/* --------------------------------------------------------------- tooltip */
const TIP = document.getElementById('tooltip');
function showTip(evt, title, rows) {
  TIP.innerHTML = `<div class="t-title">${title}</div>` +
    rows.map(r => `<div class="t-row">${r}</div>`).join('');
  TIP.classList.add('show');
  TIP.setAttribute('aria-hidden', 'false');
  TIP.style.left = evt.clientX + 'px';
  TIP.style.top = evt.clientY + 'px';
}
function hideTip() {
  TIP.classList.remove('show');
  TIP.setAttribute('aria-hidden', 'true');
}
function bindTip(node, title, rows) {
  node.addEventListener('mousemove', e => showTip(e, title, rows));
  node.addEventListener('mouseleave', hideTip);
}

/* ============================================================== CHARTS === */

function drawEquity(container, series) {
  const { svg, w, h } = svgFor(container);
  if (!series.length) return emptyState(svg, w, h);

  const padL = 62, padR = 14, padT = 12, padB = 26;
  const base = activeCapital();
  const xs = series.map(p => p.day);
  const ys = series.map(p => base + p.cum);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  let y0 = Math.min(...ys, base), y1 = Math.max(...ys, base);
  const padY = (y1 - y0) * 0.08 || 1;
  y0 -= padY; y1 += padY;

  const X = d => padL + ((d - x0) / (x1 - x0 || 1)) * (w - padL - padR);
  const Y = v => padT + (1 - (v - y0) / (y1 - y0 || 1)) * (h - padT - padB);

  // money() fixes its own precision, which on a narrow equity range (a small
  // live account moving a few hundred dollars) collapses neighbouring ticks to
  // the same label. Widen the decimals until every tick reads differently.
  const ticks = niceTicks(y0, y1, 5);
  const axisLabel = (() => {
    // extra === 0 reproduces money() exactly, so the usual desk-scale axis is
    // untouched; only a range too tight to label distinctly escalates.
    const at = (extra) => (v) => {
      const a = Math.abs(v), s = v < 0 ? '-' : '';
      if (a >= 1e6) return `${s}$${(a / 1e6).toFixed(2 + extra)}M`;
      if (a >= 1e3) return `${s}$${(a / 1e3).toFixed((a >= 1e5 ? 0 : 1) + extra)}K`;
      return `${s}$${a.toFixed(extra)}`;
    };
    for (const extra of [0, 1, 2]) {
      const fmt = at(extra);
      if (new Set(ticks.map(fmt)).size === ticks.length) return fmt;
    }
    return at(2);
  })();

  for (const t of ticks) {
    svg.appendChild(el('line', { x1: padL, x2: w - padR, y1: Y(t), y2: Y(t),
                                 stroke: CO.grid, 'stroke-width': 1 }));
    const lb = el('text', { x: padL - 9, y: Y(t) + 4, fill: CO.text3,
                            'font-size': 10.5, 'text-anchor': 'end' });
    lb.textContent = axisLabel(t);
    svg.appendChild(lb);
  }

  // Opening-capital reference: the line that says "profitable or not".
  svg.appendChild(el('line', { x1: padL, x2: w - padR, y1: Y(base), y2: Y(base),
                               stroke: CO.text3, 'stroke-width': 1,
                               'stroke-dasharray': '4 4' }));

  const pts = series.map(p => `${X(p.day)},${Y(base + p.cum)}`).join(' L');
  const last = series[series.length - 1];
  const up = base + last.cum >= base;

  const gid = 'eqgrad';
  const defs = el('defs');
  const lg = el('linearGradient', { id: gid, x1: 0, y1: 0, x2: 0, y2: 1 });
  lg.appendChild(el('stop', { offset: '0%', 'stop-color': CO.blue, 'stop-opacity': 0.32 }));
  lg.appendChild(el('stop', { offset: '100%', 'stop-color': CO.blue, 'stop-opacity': 0.01 }));
  defs.appendChild(lg); svg.appendChild(defs);

  svg.appendChild(el('path', {
    d: `M${pts} L${X(last.day)},${Y(y0)} L${X(series[0].day)},${Y(y0)} Z`,
    fill: `url(#${gid})`
  }));
  svg.appendChild(el('path', { d: `M${pts}`, fill: 'none', stroke: CO.blue,
                               'stroke-width': 2, 'stroke-linejoin': 'round' }));

  const dot = el('circle', { cx: X(last.day), cy: Y(base + last.cum), r: 4.5,
                             fill: up ? CO.profit : CO.loss,
                             stroke: CO.surface, 'stroke-width': 2 });
  svg.appendChild(dot);

  for (const d of [x0, x1]) {
    const t = el('text', { x: X(d), y: h - 7, fill: CO.text3, 'font-size': 10.5,
                           'text-anchor': d === x0 ? 'start' : 'end' });
    t.textContent = fmtDateShort(dayToDate(d));
    svg.appendChild(t);
  }

  // Crosshair + tooltip across the whole plot.
  const hit = el('rect', { x: padL, y: padT, width: w - padL - padR,
                           height: h - padT - padB, fill: 'transparent' });
  const cross = el('line', { y1: padT, y2: h - padB, stroke: CO.axis,
                             'stroke-width': 1, opacity: 0 });
  const marker = el('circle', { r: 4, fill: CO.blue, stroke: CO.surface,
                                'stroke-width': 2, opacity: 0 });
  svg.appendChild(cross); svg.appendChild(marker); svg.appendChild(hit);

  hit.addEventListener('mousemove', e => {
    const rect = svg.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * w;
    const target = x0 + ((px - padL) / (w - padL - padR)) * (x1 - x0);
    let best = series[0], bd = Infinity;
    for (const p of series) {
      const dd = Math.abs(p.day - target);
      if (dd < bd) { bd = dd; best = p; }
    }
    cross.setAttribute('x1', X(best.day)); cross.setAttribute('x2', X(best.day));
    cross.setAttribute('opacity', 1);
    marker.setAttribute('cx', X(best.day));
    marker.setAttribute('cy', Y(base + best.cum));
    marker.setAttribute('opacity', 1);
    showTip(e, fmtDateShort(dayToDate(best.day)), [
      `Equity <b>${money(base + best.cum)}</b>`,
      `Cumulative <b>${signed(best.cum)}</b>`,
      `That day <b>${signed(best.pnl)}</b>`
    ]);
  });
  hit.addEventListener('mouseleave', () => {
    cross.setAttribute('opacity', 0);
    marker.setAttribute('opacity', 0);
    hideTip();
  });
}

/** Vertical diverging bars off a zero baseline. */
function drawVBars(container, rows, opts = {}) {
  const { svg, w, h } = svgFor(container);
  if (!rows.length) return emptyState(svg, w, h);

  const padL = opts.padL ?? 58, padR = 10, padT = 10, padB = 30;
  const vals = rows.map(r => r.value);
  let lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
  const pad = (hi - lo) * 0.1 || 1; lo -= pad; hi += pad;

  const plotW = w - padL - padR, plotH = h - padT - padB;
  const step = plotW / rows.length;
  const bw = Math.max(2, Math.min(step * 0.62, 46));
  const Y = v => padT + (1 - (v - lo) / (hi - lo)) * plotH;

  for (const t of niceTicks(lo, hi, 4)) {
    svg.appendChild(el('line', { x1: padL, x2: w - padR, y1: Y(t), y2: Y(t),
                                 stroke: CO.grid, 'stroke-width': 1 }));
    const lb = el('text', { x: padL - 8, y: Y(t) + 4, fill: CO.text3,
                            'font-size': 10, 'text-anchor': 'end' });
    lb.textContent = opts.fmtAxis ? opts.fmtAxis(t) : money(t);
    svg.appendChild(lb);
  }
  svg.appendChild(el('line', { x1: padL, x2: w - padR, y1: Y(0), y2: Y(0),
                               stroke: CO.axis, 'stroke-width': 1 }));

  rows.forEach((r, i) => {
    const cx = padL + step * i + step / 2;
    const up = r.value >= 0;
    const y = up ? Y(r.value) : Y(0);
    const bh = Math.abs(Y(r.value) - Y(0));
    const colour = opts.color ? opts.color(r) : (up ? CO.profit : CO.loss);
    const p = el('path', {
      d: barPath(cx - bw / 2, y, bw, up ? bh : bh, 4, up),
      fill: colour, stroke: CO.surface, 'stroke-width': 1
    });
    // Repaint the down-bars from the baseline downward.
    if (!up) p.setAttribute('d', barPath(cx - bw / 2, Y(0), bw, bh, 4, false));
    svg.appendChild(p);
    bindTip(p, r.label, opts.tip ? opts.tip(r) : [`Net <b>${signed(r.value)}</b>`]);

    if (rows.length <= 34 && (rows.length <= 14 || i % 2 === 0)) {
      const t = el('text', { x: cx, y: h - 10, fill: CO.text3, 'font-size': 9.5,
                             'text-anchor': 'middle' });
      t.textContent = r.short ?? r.label;
      svg.appendChild(t);
    }
  });
}

/** Horizontal bars, sorted, with direct value labels. */
function drawHBars(container, rows, opts = {}) {
  const { svg, w, h } = svgFor(container);
  if (!rows.length) return emptyState(svg, w, h);

  const gutter = opts.padL ?? 108, padR = opts.padR ?? 74, padT = 6, padB = 6;
  const vals = rows.map(r => r.value);
  const lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
  const span = (hi - lo) || 1;
  // When any bar is negative its value label is drawn to the LEFT of the bar
  // end. Without reserving a lane for it, that label lands on top of the
  // category label in the gutter. Push the plot right to make room.
  const valueLane = lo < 0 ? 64 : 0;
  const plotL = gutter + valueLane;
  const plotW = w - plotL - padR;
  const X = v => plotL + ((v - lo) / span) * plotW;
  const step = (h - padT - padB) / rows.length;
  const bh = Math.max(6, Math.min(step * 0.62, 26));

  svg.appendChild(el('line', { x1: X(0), x2: X(0), y1: padT, y2: h - padB,
                               stroke: CO.axis, 'stroke-width': 1 }));

  rows.forEach((r, i) => {
    const cy = padT + step * i + step / 2;
    const right = r.value >= 0;
    const bwidth = X(r.value) - X(0);
    const colour = opts.color ? opts.color(r, i) : (right ? CO.profit : CO.loss);

    const p = el('path', {
      d: hBarPath(X(0), cy - bh / 2, bwidth, bh, 4, right),
      fill: colour, stroke: CO.surface, 'stroke-width': 1
    });
    svg.appendChild(p);
    bindTip(p, r.label, opts.tip ? opts.tip(r) : [`<b>${signed(r.value)}</b>`]);

    const lab = el('text', { x: gutter - 10, y: cy + 4, fill: CO.text2,
                             'font-size': 11.5, 'text-anchor': 'end' });
    lab.textContent = r.label;
    svg.appendChild(lab);

    const vt = el('text', {
      x: X(r.value) + (right ? 8 : -8), y: cy + 4, fill: CO.text,
      'font-size': 11.5, 'font-weight': 600,
      'text-anchor': right ? 'start' : 'end'
    });
    vt.textContent = opts.fmtValue ? opts.fmtValue(r.value) : money(r.value);
    svg.appendChild(vt);
  });
}

function drawHistogram(container, values, opts = {}) {
  const { svg, w, h } = svgFor(container);
  if (!values.length) return emptyState(svg, w, h);

  const lo = Math.min(...values), hi = Math.max(...values);
  const bins = opts.bins || 26;
  const width = (hi - lo) / bins || 1;
  const counts = new Array(bins).fill(0);
  for (const v of values) {
    let b = Math.floor((v - lo) / width);
    if (b >= bins) b = bins - 1;
    if (b < 0) b = 0;
    counts[b]++;
  }

  const padL = 44, padR = 10, padT = 10, padB = 28;
  const plotW = w - padL - padR, plotH = h - padT - padB;
  const maxC = Math.max(...counts);
  const step = plotW / bins;
  const Y = c => padT + (1 - c / maxC) * plotH;

  for (const t of niceTicks(0, maxC, 4)) {
    svg.appendChild(el('line', { x1: padL, x2: w - padR, y1: Y(t), y2: Y(t),
                                 stroke: CO.grid, 'stroke-width': 1 }));
    const lb = el('text', { x: padL - 8, y: Y(t) + 4, fill: CO.text3,
                            'font-size': 10, 'text-anchor': 'end' });
    lb.textContent = num(Math.round(t));
    svg.appendChild(lb);
  }

  counts.forEach((c, i) => {
    const binLo = lo + i * width;
    const x = padL + step * i;
    const bh = plotH - (Y(c) - padT);
    const colour = binLo + width / 2 >= 0 ? CO.profit : CO.loss;
    const p = el('path', {
      d: barPath(x + step * 0.08, Y(c), step * 0.84, bh, 3, true),
      fill: colour, stroke: CO.surface, 'stroke-width': 0.8
    });
    svg.appendChild(p);
    bindTip(p, `${money(binLo)} to ${money(binLo + width)}`,
            [`<b>${num(c)}</b> days`]);
  });

  const zx = padL + ((0 - lo) / (hi - lo || 1)) * plotW;
  if (zx > padL && zx < w - padR) {
    svg.appendChild(el('line', { x1: zx, x2: zx, y1: padT, y2: h - padB,
                                 stroke: CO.text3, 'stroke-width': 1 }));
  }
  [[lo, 'start'], [hi, 'end']].forEach(([v, anchor]) => {
    const t = el('text', {
      x: anchor === 'start' ? padL : w - padR, y: h - 8,
      fill: CO.text3, 'font-size': 10, 'text-anchor': anchor });
    t.textContent = money(v);
    svg.appendChild(t);
  });
}

function drawSparkline(container, series) {
  container.innerHTML = '';
  if (series.length < 2) return;
  const w = 200, h = 26;
  const svg = el('svg', { viewBox: `0 0 ${w} ${h}`, preserveAspectRatio: 'none' });
  const ys = series.map(p => p.cum);
  const lo = Math.min(...ys), hi = Math.max(...ys);
  const X = i => (i / (series.length - 1)) * w;
  const Y = v => h - 2 - ((v - lo) / ((hi - lo) || 1)) * (h - 4);
  const d = series.map((p, i) => `${X(i)},${Y(p.cum)}`).join(' L');
  const up = ys[ys.length - 1] >= 0;
  svg.appendChild(el('path', { d: `M${d}`, fill: 'none',
                               stroke: up ? CO.profit : CO.loss,
                               'stroke-width': 1.6, 'stroke-linejoin': 'round' }));
  container.appendChild(svg);
}

function drawDayTable(container, rows, positive) {
  container.innerHTML = '';
  if (!rows.length) {
    container.innerHTML = '<p style="color:var(--text-3);font-size:12.5px">No trades match the current filters.</p>';
    return;
  }
  const maxAbs = Math.max(...rows.map(r => Math.abs(r.net)));
  const table = document.createElement('table');
  table.className = 'dtable';
  table.innerHTML = `<thead><tr>
      <th>Date</th><th>Trades</th><th style="text-align:right">Win rate</th>
      <th style="text-align:right">Net P&amp;L</th><th class="barcell"></th>
    </tr></thead>`;
  const tb = document.createElement('tbody');
  for (const r of rows) {
    const tr = document.createElement('tr');
    const pctW = (Math.abs(r.net) / maxAbs) * 100;
    tr.innerHTML = `
      <td>${fmtDateShort(dayToDate(r.key))}</td>
      <td class="num">${num(r.n)}</td>
      <td class="num">${pct(r.winRate)}</td>
      <td class="num ${r.net >= 0 ? 'pos' : 'neg'}">${signed(r.net)}</td>
      <td class="barcell"><div class="minibar" style="width:${pctW}%;background:${
        positive ? CO.profit : CO.loss}"></div></td>`;
    tb.appendChild(tr);
  }
  table.appendChild(tb);
  container.appendChild(table);
}

function emptyState(svg, w, h) {
  const t = el('text', { x: w / 2, y: h / 2, fill: CO.text3, 'font-size': 12.5,
                         'text-anchor': 'middle' });
  t.textContent = 'No trades match the current filters';
  svg.appendChild(t);
}

/* ------------------------------------------------------- animated counter */
function animate(node, to, fmt) {
  const from = parseFloat(node.dataset.v || '0');
  node.dataset.v = to;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    node.textContent = fmt(to);
    return;
  }
  const t0 = performance.now(), dur = 620;
  const tick = (now) => {
    const p = Math.min((now - t0) / dur, 1);
    const e = 1 - Math.pow(1 - p, 3);
    node.textContent = fmt(from + (to - from) * e);
    if (p < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);

  // rAF is throttled in background tabs and paused under headless virtual
  // time, either of which would leave a partially-counted number frozen on a
  // KPI card. This guarantees the exact value lands regardless.
  clearTimeout(node._settle);
  node._settle = setTimeout(() => { node.textContent = fmt(to); }, dur + 80);
}

/* ================================================================ RENDER = */
function render() {
  const idx = filter();
  const s = summarise(idx);
  const series = dailySeries(idx);
  const dd = maxDrawdown(series);

  /* ---- status line */
  const status = document.getElementById('filter-status');
  const active = [];
  if (STATE.asset.size) active.push(`${STATE.asset.size} asset(s)`);
  if (STATE.strategy.size) active.push(`${STATE.strategy.size} strategy(ies)`);
  if (STATE.trading_session.size) active.push(`${STATE.trading_session.size} session(s)`);
  if (STATE.trade_type.size) active.push(`${STATE.trade_type.size} side`);
  if (STATE.data_source.size) {
    active.push([...STATE.data_source].map(i => DIMS.data_source[i]).join(' + ')
                + ' trades only');
  }
  status.textContent = `Showing ${num(s.n)} of ${num(D.n)} trades` +
    (active.length ? ` — filtered by ${active.join(', ')}` : ' — no filters applied');

  /* ---- KPI cards */
  animate(document.getElementById('kpi-gross'), s.gross, v => money(v));
  document.getElementById('kpi-gross-sub').textContent =
    `fees ${money(s.fees)} (${s.gross ? pct(Math.abs(s.fees / s.gross) * 100) : '—'} of gross)`;

  const netEl = document.getElementById('kpi-net');
  animate(netEl, s.net, v => signed(v));
  netEl.className = 'kpi-value ' + (s.net >= 0 ? 'pos' : 'neg');
  document.getElementById('kpi-net-sub').textContent =
    `${money(s.n ? s.net / s.n : 0)} per trade · ${s.avgR >= 0 ? '+' : ''}${s.avgR.toFixed(3)}R`;

  animate(document.getElementById('kpi-wr'), s.winRate, v => pct(v, 2));
  document.getElementById('kpi-wr-sub').textContent =
    `${num(s.wins)} wins / ${num(s.losses)} losses`;
  document.getElementById('meter-wr').style.width = Math.min(s.winRate, 100) + '%';

  animate(document.getElementById('kpi-rr'), s.avgRR, v => v.toFixed(2) + ' : 1');
  document.getElementById('kpi-rr-sub').textContent =
    `break-even win rate ${pct(100 / (1 + s.avgRR))}`;

  const ddEl = document.getElementById('kpi-dd');
  animate(ddEl, dd.pct, v => pct(v, 2));
  ddEl.className = 'kpi-value neg';
  document.getElementById('kpi-dd-sub').textContent = `${money(dd.usd)} peak to trough`;

  animate(document.getElementById('kpi-dur'), s.avgDur, v => durText(v));
  document.getElementById('kpi-dur-sub').textContent =
    `median ${durText(s.medDur)}` +
    (s.durN < s.n ? ` · ${num(s.durN)} of ${num(s.n)} record an exit time` : '');

  drawSparkline(document.getElementById('spark-gross'), series);
  drawSparkline(document.getElementById('spark-net'), series);

  /* ---- equity */
  document.getElementById('equity-deck').textContent =
    `${num(s.n)} trades · net ${signed(s.net)} on ${money(activeCapital())} opening capital`;
  document.getElementById('equity-legend').innerHTML =
    `<span class="lg"><i class="sw" style="background:${CO.blue}"></i>Desk equity</span>` +
    `<span class="lg"><i class="sw" style="background:${CO.text3}"></i>Opening capital</span>`;
  drawEquity(document.getElementById('chart-equity'), series);

  /* ---- monthly */
  const months = new Map();
  for (const i of idx) {
    const k = monthKey(dayToDate(C.day[i]));
    const g = months.get(k) || { net: 0, n: 0, wins: 0 };
    g.net += C.net[i]; g.n++; g.wins += C.win[i];
    months.set(k, g);
  }
  const mRows = [...months.entries()].sort((a, b) => a[0].localeCompare(b[0]))
    .map(([k, v]) => ({
      label: k, short: k.slice(2).replace('-', '‑'),
      value: v.net, n: v.n, wins: v.wins
    }));
  const posM = mRows.filter(r => r.value > 0).length;
  document.getElementById('monthly-deck').textContent =
    `${posM} profitable of ${mRows.length} months`;
  drawVBars(document.getElementById('chart-monthly'), mRows, {
    tip: r => [`Net <b>${signed(r.value)}</b>`, `Trades <b>${num(r.n)}</b>`,
               `Win rate <b>${pct(r.n ? (r.wins / r.n) * 100 : 0)}</b>`]
  });

  /* ---- daily distribution */
  drawHistogram(document.getElementById('chart-daily'), series.map(p => p.pnl));

  /* ---- assets */
  const aRows = groupBy(idx, i => C.asset[i])
    .map(g => ({ label: DIMS.asset[g.key], value: g.net, ...g }))
    .sort((a, b) => a.value - b.value);
  drawHBars(document.getElementById('chart-asset'), aRows, {
    tip: r => [`Net <b>${signed(r.value)}</b>`, `Trades <b>${num(r.n)}</b>`,
               `Win rate <b>${pct(r.winRate)}</b>`, `Expectancy <b>${r.avgR.toFixed(3)}R</b>`]
  });

  /* ---- strategies (ranked on expectancy in R, not dollars) */
  const sRows = groupBy(idx, i => C.strategy[i])
    .map(g => ({ label: DIMS.strategy[g.key], value: g.avgR, ...g }))
    .sort((a, b) => a.value - b.value);
  drawHBars(document.getElementById('chart-strategy'), sRows, {
    padL: 130,
    fmtValue: v => (v >= 0 ? '+' : '') + v.toFixed(3) + 'R',
    tip: r => [`Expectancy <b>${r.avgR.toFixed(4)}R</b>`, `Net <b>${signed(r.net)}</b>`,
               `Trades <b>${num(r.n)}</b>`, `Win rate <b>${pct(r.winRate)}</b>`]
  });

  /* ---- sessions */
  const seRows = groupBy(idx, i => C.trading_session[i])
    .map(g => ({ label: DIMS.trading_session[g.key], value: g.net, ...g }))
    .sort((a, b) => a.value - b.value);
  drawHBars(document.getElementById('chart-session'), seRows, {
    padL: 82, padR: 70,
    tip: r => [`Net <b>${signed(r.value)}</b>`, `Trades <b>${num(r.n)}</b>`,
               `Expectancy <b>${r.avgR.toFixed(3)}R</b>`]
  });

  /* ---- risk bands (share of trades — a magnitude, so one hue) */
  const order = ['<0.5%', '0.5-1%', '1-2%', '2-3%', '>3%'];
  const rMap = new Map(groupBy(idx, i => C.risk_bucket[i])
    .map(g => [DIMS.risk_bucket[g.key], g]));
  const rRows = order.filter(k => rMap.has(k)).map(k => {
    const g = rMap.get(k);
    return { label: k, value: s.n ? (g.n / s.n) * 100 : 0, ...g };
  });
  drawVBars(document.getElementById('chart-risk'), rRows, {
    padL: 42,
    fmtAxis: t => t.toFixed(0) + '%',
    color: () => CO.blue,
    tip: r => [`<b>${pct(r.value)}</b> of trades (${num(r.n)})`,
               `Expectancy <b>${r.avgR.toFixed(3)}R</b>`,
               `Net <b>${signed(r.net)}</b>`]
  });

  /* ---- hour of day */
  const hRows = groupBy(idx, i => C.hour[i])
    .map(g => ({ label: String(g.key).padStart(2, '0') + ':00',
                 short: String(g.key).padStart(2, '0'), value: g.net, ...g }))
    .sort((a, b) => a.key - b.key);
  drawVBars(document.getElementById('chart-hour'), hRows, {
    padL: 46,
    tip: r => [`Net <b>${signed(r.value)}</b>`, `Trades <b>${num(r.n)}</b>`,
               `Expectancy <b>${r.avgR.toFixed(3)}R</b>`]
  });

  /* ---- best / worst days */
  const dayRows = groupBy(idx, i => C.day[i]).sort((a, b) => b.net - a.net);
  drawDayTable(document.getElementById('chart-topwin'), dayRows.slice(0, 10), true);
  drawDayTable(document.getElementById('chart-toploss'),
               dayRows.slice(-10).reverse(), false);
}

/* ================================================================= INIT == */
function buildChips(containerId, dim, onChange) {
  const box = document.getElementById(containerId);
  box.innerHTML = '';
  DIMS[dim].forEach((label, i) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'chip';
    b.textContent = label;
    b.setAttribute('aria-pressed', 'false');
    b.addEventListener('click', () => {
      const set = STATE[dim];
      if (set.has(i)) { set.delete(i); b.setAttribute('aria-pressed', 'false'); }
      else { set.add(i); b.setAttribute('aria-pressed', 'true'); }
      if (onChange) onChange();
      render();
    });
    box.appendChild(b);
  });
}

/* The View toggle and the Source chips are two controls over one piece of
   state, so whichever the user touches, both are repainted from STATE. An
   empty selection means "everything", which is the All button. */
function syncSourceControls() {
  const chosen = [...STATE.data_source].map(i => DIMS.data_source[i]);
  document.querySelectorAll('#f-source .chip').forEach((c, i) => {
    c.setAttribute('aria-pressed', STATE.data_source.has(i) ? 'true' : 'false');
  });
  const view = chosen.length === 1 ? chosen[0] : 'both';
  document.querySelectorAll('.view-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.view === view);
  });
}

function init() {
  document.getElementById('meta-trades').textContent = num(D.n) + ' trades';
  document.getElementById('meta-period').textContent =
    `${fmtDateShort(new Date(D.dateMin + 'T00:00:00Z'))} – ${fmtDateShort(new Date(D.dateMax + 'T00:00:00Z'))}`;
  document.getElementById('meta-traders').textContent = DIMS.trader_id.length;
  document.getElementById('foot-rows').textContent = num(D.n);
  document.getElementById('foot-generated').textContent = 'generated ' + D.generated;

  const from = document.getElementById('f-from');
  const to = document.getElementById('f-to');
  from.value = D.dateMin; from.min = D.dateMin; from.max = D.dateMax;
  to.value = D.dateMax;   to.min = D.dateMin;   to.max = D.dateMax;

  const origin = new Date(D.dateOrigin + 'T00:00:00Z');
  const toDay = (v) => Math.round((new Date(v + 'T00:00:00Z') - origin) / 86400000);

  from.addEventListener('change', () => {
    STATE.from = from.value ? toDay(from.value) : 0;
    render();
  });
  to.addEventListener('change', () => {
    STATE.to = to.value ? toDay(to.value) : Math.max(...C.day);
    render();
  });

  buildChips('f-asset', 'asset');
  buildChips('f-strategy', 'strategy');
  buildChips('f-session', 'trading_session');
  buildChips('f-side', 'trade_type');
  buildChips('f-source', 'data_source', syncSourceControls);

  // A source that isn't in the payload gets no button — offering "Real" when
  // the journal was never imported would just filter the dashboard to nothing.
  document.querySelectorAll('.view-btn').forEach(btn => {
    if (btn.dataset.view !== 'both' &&
        !DIMS.data_source.includes(btn.dataset.view)) btn.remove();
  });
  if (DIMS.data_source.length < 2) {
    document.querySelector('.view-toggle').closest('.filter-group').hidden = true;
    document.getElementById('f-source').closest('.filter-group').hidden = true;
  }

  document.querySelectorAll('.view-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const idx = DIMS.data_source.indexOf(btn.dataset.view);
      STATE.data_source.clear();
      if (idx !== -1) STATE.data_source.add(idx);   // "both" isn't a dim value
      syncSourceControls();
      render();
    });
  });

  document.getElementById('f-reset').addEventListener('click', () => {
    STATE.asset.clear(); STATE.strategy.clear();
    STATE.trading_session.clear(); STATE.trade_type.clear(); STATE.data_source.clear();
    STATE.from = 0; STATE.to = Math.max(...C.day);
    from.value = D.dateMin; to.value = D.dateMax;
    document.querySelectorAll('.chip').forEach(c => c.setAttribute('aria-pressed', 'false'));
    syncSourceControls();
    render();
  });

  STATE.to = Math.max(...C.day);
  render();

  // Charts are drawn to the container's pixel width, so a resize needs a repaint.
  let rt;
  window.addEventListener('resize', () => {
    clearTimeout(rt);
    rt = setTimeout(render, 160);
  });
}

document.addEventListener('DOMContentLoaded', init);
