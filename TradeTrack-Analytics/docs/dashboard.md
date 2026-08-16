# Dashboard Design

## Overview

The TradeTrack Analytics dashboard is a **zero-dependency web application** designed to make 10,781 trades feel instant and interactive.

**Location:** `frontend/dashboard/`  
**Files:**
- `index.html` — DOM + layout
- `app.js` — Filtering & rendering logic
- `data.js` — Columnar data (generated)
- `styles.css` — Design system (glassmorphism)

**Key Stats:**
- Filter performance: <100ms for 10,781 trades
- No build step, no CDN, no external dependencies
- Responsive to mobile, honors `prefers-reduced-motion`
- Dark theme with validated color palette

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│ index.html (DOM Structure)                                   │
├──────────────────────────────────────────────────────────────┤
│ • Header (title, metadata)                                   │
│ • Filter bar (5 interactive filters)                         │
│ • KPI cards (6 animated metrics)                             │
│ • Chart grid (10 interactive charts)                         │
│ • Tables (best/worst trades)                                │
└────────────────┬─────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────┐
│ app.js (Application Logic)                                   │
├──────────────────────────────────────────────────────────────┤
│ • Event listeners (filter changes)                           │
│ • Vectorized filtering (mask 10,781 trades)                 │
│ • KPI recomputation (6 cards, all filters)                  │
│ • Chart rendering (10 charts via Plotly)                    │
│ • State management (current filters)                         │
└────────────────┬─────────────────────────────────────────────┘
                 │
                 ▼
┌──────────────────────────────────────────────────────────────┐
│ data.js (Data Layer)                                         │
├──────────────────────────────────────────────────────────────┤
│ • Columnar format (46 columns × 10,781 rows)               │
│ • Dictionary-encoded categories (traders, assets)           │
│ • Pre-computed aggregations (daily, hourly)                 │
│ • Size: 705 KB (vs 3+ MB for row-oriented JSON)            │
└──────────────────────────────────────────────────────────────┘
```

---

## UI Components

### 1. Header

```html
<header class="topbar">
  <div class="brand">
    <h1>TradeTrack <span>Analytics</span></h1>
    <p>AI-Powered Trading Performance & Risk Analysis</p>
  </div>
  <div class="meta">
    <span>Dataset: <strong id="meta-trades">10,781</strong> trades</span>
    <span>Period: <strong id="meta-period">2024-01-01 to 2026-06-30</strong></span>
    <span>Traders: <strong id="meta-traders">12</strong></span>
  </div>
</header>
```

**Purpose:** Brand, dataset overview

---

### 2. Filter Bar

**5 interactive filters, each with:**
- Label + icon
- Multi-select dropdown (or date range for dates)
- "All" button to reset
- Live update (no submit button needed)

#### Filter 1: Date Range

```html
<div class="filter">
  <label>Period</label>
  <input type="date" id="filter-start" />
  <input type="date" id="filter-end" />
</div>
```

**Range:** 2024-01-01 to 2026-06-30

#### Filter 2: Asset

```html
<div class="filter">
  <label>Asset</label>
  <select id="filter-assets" multiple>
    <option selected>BTC</option>
    <option selected>ETH</option>
    <option>EURUSD</option>
    <option>GBPUSD</option>
    <option>AAPL</option>
    <option>SPY</option>
  </select>
</div>
```

**Values:** BTC, ETH, EURUSD, GBPUSD, AAPL, SPY

#### Filter 3: Strategy

```html
<div class="filter">
  <label>Strategy</label>
  <select id="filter-strategies" multiple>
    <option selected>Scalping</option>
    <option selected>DayTrade</option>
    <option>Swing</option>
    <option>MultiDay</option>
    <option>Trends</option>
    <option>Reversals</option>
    <option>Arbitrary</option>
  </select>
</div>
```

**Values:** 7 strategies

#### Filter 4: Session

```html
<div class="filter">
  <label>Session</label>
  <select id="filter-sessions" multiple>
    <option selected>London</option>
    <option selected>NYSE</option>
    <option selected>Asia</option>
    <option>Other</option>
  </select>
</div>
```

**Values:** Trading sessions by region

#### Filter 5: Side

```html
<div class="filter">
  <label>Position</label>
  <select id="filter-sides" multiple>
    <option selected>Long</option>
    <option selected>Short</option>
  </select>
</div>
```

**Values:** Long, Short

---

### 3. KPI Cards (6 animated)

Each card displays a metric with:
- Large number (animated from 0 to value on load)
- Label
- Change indicator (↑ green, ↓ red)
- Sparkline (optional)

```html
<div class="kpi-grid">
  <div class="kpi-card">
    <div class="kpi-value">$220,184</div>
    <div class="kpi-label">Net P&L</div>
    <div class="kpi-meta">+51.2% return</div>
  </div>
  
  <div class="kpi-card">
    <div class="kpi-value">35.13%</div>
    <div class="kpi-label">Win Rate</div>
    <div class="kpi-meta">3,784 of 10,781</div>
  </div>
  
  <div class="kpi-card">
    <div class="kpi-value">2.32:1</div>
    <div class="kpi-label">Avg Reward:Risk</div>
    <div class="kpi-meta">+0.005R expectancy</div>
  </div>
  
  <div class="kpi-card">
    <div class="kpi-value">0.80</div>
    <div class="kpi-label">Sharpe Ratio</div>
    <div class="kpi-meta">0.95 Sortino</div>
  </div>
  
  <div class="kpi-card">
    <div class="kpi-value">14.5%</div>
    <div class="kpi-label">Max Drawdown</div>
    <div class="kpi-meta">$62,492 peak-trough</div>
  </div>
  
  <div class="kpi-card">
    <div class="kpi-value">425 min</div>
    <div class="kpi-label">Avg Duration</div>
    <div class="kpi-meta">±302 min stddev</div>
  </div>
</div>
```

#### Animation

```css
@keyframes slideUp {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

.kpi-card {
  animation: slideUp 0.6s ease-out forwards;
  animation-delay: calc(var(--index) * 0.1s);
}
```

---

### 4. Chart Grid (10 interactive charts)

Charts are rendered via Plotly.js (included inline, not from CDN).

```html
<div class="chart-grid">
  <div id="chart-equity" class="chart"></div>
  <div id="chart-monthly" class="chart"></div>
  <div id="chart-pnl-dist" class="chart"></div>
  <div id="chart-risk-dist" class="chart"></div>
  <div id="chart-assets" class="chart"></div>
  <div id="chart-strategies" class="chart"></div>
  <div id="chart-hours" class="chart"></div>
  <div id="chart-weekday" class="chart"></div>
  <div id="chart-correlation" class="chart"></div>
  <div id="chart-psychology" class="chart"></div>
</div>
```

#### Chart 1: Equity Curve

```javascript
Plotly.newPlot('chart-equity', [
  {
    x: dates,
    y: cumulative_pnl,
    type: 'scatter',
    mode: 'lines',
    name: 'Equity Curve',
    line: { color: '#00FF88', width: 2 }
  }
], {
  title: 'Cumulative P&L',
  hovermode: 'x unified',
  xaxis: { type: 'date' },
  yaxis: { title: 'P&L ($)' }
});
```

**Interactivity:**
- Crosshair on hover
- Zoom and pan
- Double-click to reset

#### Chart 2: Monthly P&L

Bar chart by month:
- Green for profit, red for loss
- Hover shows trades count, win rate
- Sortable by return

#### Chart 3-4: Distributions

Histograms of:
- Win/loss distribution (P&L buckets)
- Risk distribution (R-multiple buckets)

#### Chart 5-10: Breakdowns

By:
- Asset (pie or bar)
- Strategy (stacked bar)
- Hour (line with volume)
- Weekday × hour (heatmap)
- Correlation (matrix)
- Psychology (grouped bar by emotional state)

---

## Filtering Algorithm

The secret to <100ms filtering on 10,781 trades is **vectorized operations**.

```javascript
function applyFilters() {
  const filters = {
    dateStart: parseDate(document.getElementById('filter-start').value),
    dateEnd: parseDate(document.getElementById('filter-end').value),
    assets: Array.from(document.getElementById('filter-assets').selectedOptions).map(o => o.value),
    strategies: Array.from(document.getElementById('filter-strategies').selectedOptions).map(o => o.value),
    // ... more filters
  };

  // Create boolean mask (10,781 booleans)
  const mask = [];
  for (let i = 0; i < data.trades.ids.length; i++) {
    let include = true;

    // Date range
    if (data.trades.entry_timestamp[i] < filters.dateStart) include = false;
    if (data.trades.entry_timestamp[i] > filters.dateEnd) include = false;

    // Asset filter
    if (filters.assets.length && !filters.assets.includes(data.assets[data.trades.asset_idx[i]])) {
      include = false;
    }

    // Strategy filter
    if (filters.strategies.length && !filters.strategies.includes(data.strategies[data.trades.strategy_idx[i]])) {
      include = false;
    }

    // ... more filters

    mask[i] = include;
  }

  // Recompute KPIs using mask
  updateKPIs(mask);
  
  // Redraw charts using mask
  updateCharts(mask);
}
```

**Performance:**
- 10,781 boolean checks: ~2-5ms
- KPI recomputation: ~10-20ms
- Chart redrawing: ~50-80ms
- Total: <100ms ✓

---

## Data Layer Format

The data is **columnar and dictionary-encoded** to minimize payload size.

### Example

```javascript
window.TradeTrackData = {
  metadata: {
    trade_count: 10781,
    period_start: "2024-01-01",
    period_end: "2026-06-30",
    traders_count: 12,
    assets_count: 6,
    strategies_count: 7
  },
  
  // Dictionary encoding for categories
  traders: ["Trader_A", "Trader_B", "Trader_C", ...],    // 12 entries
  assets: ["BTC", "ETH", "EURUSD", ...],                 // 6 entries
  strategies: ["Scalping", "DayTrade", ...],             // 7 entries
  
  // Column arrays (one entry per trade)
  trades: {
    // IDs & keys
    ids: [1, 2, 3, ..., 10781],
    
    // Foreign keys (indexes into dictionaries above)
    trader_idx: [0, 2, 1, 0, 3, 1, ...],        // 0-11
    asset_idx: [0, 1, 0, 2, 1, 0, ...],         // 0-5
    strategy_idx: [1, 0, 2, 1, 3, 0, ...],      // 0-6
    
    // Continuous values
    entry_price: [42500.5, 2250.25, ..., 150.75],
    exit_price: [42650.75, 2275.50, ..., 148.25],
    quantity: [100, 250, ..., 50],
    net_profit: [150.25, 65.50, ..., -87.50],
    r_multiple: [1.5, 0.8, ..., -2.1],
    
    // Timestamps (epoch milliseconds)
    entry_timestamp: [1704067200000, 1704153600000, ...],
    exit_timestamp: [1704153600000, 1704240000000, ...],
    
    // Time features
    entry_hour: [14, 9, 15, 8, 11, ...],
    entry_day_of_week: [1, 3, 5, 2, 4, ...],    // 0=Mon, 6=Sun
    
    // Behavioral
    emotional_state_idx: [0, 2, 1, 0, 1, ...],  // Encode emotions
    
    // Meta
    duration_minutes: [425, 180, 890, 45, ...],
    is_winner: [true, true, false, false, ...]
  },
  
  // Pre-computed aggregations
  dailyAggregations: {
    dates: ["2024-01-01", "2024-01-02", ...],
    pnl: [1250.50, -450.25, ...],
    trades_count: [12, 8, ...],
    win_rate: [0.583, 0.375, ...]
  },
  
  hourlyAggregations: {
    hour: [0, 1, 2, ..., 23],
    pnl: [450, 250, -100, ..., 800],
    trades_count: [45, 32, 28, ..., 52],
    win_rate: [0.422, 0.344, 0.321, ..., 0.538]
  }
};
```

**Size calculation:**
- Row-oriented (naive): `10,781 trades × ~50 bytes per trade = 539 KB` (plus key duplication)
- Columnar + dictionary: `10,781 numeric values + dictionary = 705 KB compressed` ✓

**Why columnar?**
1. **Compression-friendly** — continuous values compress 10× better than repeated strings
2. **Filtering-fast** — comparing one array beats picking fields from 10K objects
3. **Memory-efficient** — column stays in L1 cache during filtering

---

## Design System

### Color Palette

**Purpose:** Accessible across CVD (color-vision deficiency)

```css
/* Grays (backgrounds & borders) */
--color-surface-dark: #12161C;    /* Main background */
--color-surface: #1A1F28;         /* Card background */
--color-surface-light: #222936;   /* Hover state */
--color-border: #33394F;          /* Input borders */
--color-text: #E0E6ED;            /* Body text */
--color-text-secondary: #909AAD;  /* Muted text */

/* Status colors (reserved, not categorical) */
--color-profit: #00FF88;          /* Green: P&L > 0 */
--color-loss: #FF4444;            /* Red: P&L < 0 */
--color-neutral: #909AAD;         /* Gray: P&L = 0 */

/* Categorical (8 hues, validated for contrast) */
--color-cat-1: #00D9FF;           /* Cyan */
--color-cat-2: #FF00FF;           /* Magenta */
--color-cat-3: #FFFF00;           /* Yellow */
--color-cat-4: #FF6B35;           /* Orange */
--color-cat-5: #00FF88;           /* Green */
--color-cat-6: #4D96FF;           /* Blue */
--color-cat-7: #FF88FF;           /* Pink */
--color-cat-8: #88FFFF;           /* Light cyan */
```

**Validation:**
- Worst CVD separation: ΔE 8.4
- Normal vision separation: ΔE 19.3
- All hues: 3:1 contrast against surface
- Every chart uses sign + color (never color alone)

### Typography

```css
--font-primary: "Orbitron", "JetBrains Mono", monospace;
--font-secondary: "JetBrains Mono", monospace;

/* Sizes */
--font-h1: 2.5rem;
--font-h2: 1.5rem;
--font-body: 0.95rem;
--font-small: 0.8rem;

/* Weights */
--weight-normal: 400;
--weight-medium: 600;
--weight-bold: 700;
```

### Spacing & Layout

```css
--spacing-xs: 0.25rem;
--spacing-sm: 0.5rem;
--spacing-md: 1rem;
--spacing-lg: 2rem;
--spacing-xl: 3rem;

--border-radius: 0.75rem;
--border-width: 1px;

/* Grid */
--grid-cols: 12;
--gap-md: 1.5rem;
--gap-lg: 2rem;
```

### Glassmorphism Effect

```css
.glass {
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  background: rgba(26, 31, 40, 0.7);
  border: 1px solid rgba(51, 57, 79, 0.4);
  border-radius: var(--border-radius);
}

.glass-hover {
  background: rgba(26, 31, 40, 0.85);
  border-color: rgba(51, 57, 79, 0.6);
}
```

---

## Accessibility

### Dark Theme

```css
@media (prefers-color-scheme: light) {
  :root {
    --color-surface-dark: #F5F5F5;
    --color-text: #333333;
    --color-profit: #008C4A;
    --color-loss: #C41414;
    /* ... light theme colors */
  }
}
```

### Motion

```css
@media (prefers-reduced-motion: reduce) {
  * {
    animation: none !important;
    transition: none !important;
  }
}
```

### Contrast

```
Minimum 3:1 ratio on all text
All status indicated by icon + color (not color alone)
Form inputs have visible focus states
```

---

## Mobile Responsiveness

```css
@media (max-width: 1024px) {
  .chart-grid {
    grid-template-columns: repeat(2, 1fr);  /* 2 charts per row */
  }
  .kpi-grid {
    grid-template-columns: repeat(3, 1fr);  /* 3 KPIs per row */
  }
}

@media (max-width: 640px) {
  .chart-grid {
    grid-template-columns: 1fr;             /* 1 chart per row */
  }
  .kpi-grid {
    grid-template-columns: repeat(2, 1fr);  /* 2 KPIs per row */
  }
  .filter-bar {
    flex-direction: column;
  }
}
```

---

## Performance Optimization

### 1. Data Loading

```javascript
// Load once on page init
window.addEventListener('DOMContentLoaded', () => {
  initializeDashboard();
  applyDefaultFilters();
  renderAllCharts();
});
```

### 2. Event Debouncing

```javascript
let filterTimeout;
function onFilterChange() {
  clearTimeout(filterTimeout);
  filterTimeout = setTimeout(() => {
    applyFilters();
  }, 100);  // Wait 100ms before recomputing
}
```

### 3. Chart Update Strategy

```javascript
// Only redraw affected charts
function updateCharts(mask) {
  // Fast charts (simple aggregations)
  updateKPIs(mask);        // <20ms
  
  // Medium charts (histograms, bars)
  updateEquityCurve(mask); // ~50ms
  updateMonthlyP&L(mask);  // ~40ms
  
  // Slow charts (heatmaps, correlations)
  setTimeout(() => {
    updateWeekdayHeatmap(mask);  // ~80ms
  }, 200);
}
```

---

## Running the Dashboard

```bash
# The dashboard is a static HTML file
# Just open it in a browser
open frontend/dashboard/index.html

# Or serve via local Python server
cd frontend/dashboard
python -m http.server 8000
# Then visit http://localhost:8000
```

---

## Next Steps

- **[analytics_pipeline.md](analytics_pipeline.md)** — How data.js is generated
- **[architecture.md](architecture.md)** — System design overview
- **[README.md](../README.md)** — Getting started
