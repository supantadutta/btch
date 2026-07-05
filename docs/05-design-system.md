# Design System — Vantage Dark Premium

Feel: quant research terminal × options analytics dashboard × modern crypto execution
workstation. Dense but readable, calm, trustworthy. Desktop-first.

## Color tokens (Tailwind theme, `frontend/tailwind.config.ts`)

| Token | Hex | Use |
|---|---|---|
| `bg` | `#0B0E11` | app background (near-black charcoal) |
| `surface` | `#12161C` | cards, panels |
| `surface-2` | `#181D25` | nested panels, table headers, inputs |
| `border` | `#232A33` | 1px hairline borders |
| `text` | `#E6EAF0` | primary text |
| `text-dim` | `#8B93A1` | secondary text, labels |
| `text-faint` | `#5A6270` | tertiary, axis labels |
| `up` | `#2EBD85` | gains, longs (muted green) |
| `down` | `#F6465D` | losses, shorts (muted red) |
| `accent` | `#4A9EFF` | interactive, links, focus |
| `warn` | `#F0B90B` | warnings, soft kill switch |
| `crit` | `#FF5C5C` | hard kill switch, critical banners |

Rules: color encodes **meaning only** (PnL sign, side, severity) — never decoration.
Charts use `up`/`down`/`accent` plus a neutral series ramp; backgrounds stay flat; glow is a
1px inner border + very soft `box-shadow: 0 0 0 1px border, 0 8px 24px rgb(0 0 0 / .35)`.

## Typography

- UI: `Inter` (400/500/600). Numbers/tickers/tables: `JetBrains Mono` with `font-variant-numeric: tabular-nums`.
- Scale: 12 (dense tables/labels), 13 (body), 15 (card titles), 20/28 (KPI values). No decorative sizes.

## Spacing & layout

- 4px base grid; cards `rounded-lg (8px)`, padding 16; panel gap 12.
- Shell: 48px top nav · 220px collapsible left sidebar (56px collapsed) · fluid workspace.
- Workspace: 12-col CSS grid; widgets declare col/row spans; resizable panels via
  `react-resizable-panels` where useful (terminal, lab).

## Components (in `frontend/src/components/ui`)

`Card` `KpiStat` (value + delta + sparkline) `DataTable` (mono, sticky header, virtualized)
`Badge` (status: live/paper/degraded/tripped) `SideTag` (LONG/SHORT) `PnL` (signed, colored,
tabular) `Toggle` `Select` `Input` `Modal` `Toast` `Banner` (kill-switch / stale-data)
`Skeleton` `EmptyState` `CommandPalette (⌘K)` `Sparkline` `ConfidenceMeter` `RegimeChip`.

## States & motion

- Every data panel has: loading skeleton → empty state → error state → stale badge (age > 5s).
- Motion: 120–160 ms ease-out on hover/expand only. No chart animation on live updates.
- Status is always visible: top-nav shows mode badge (PAPER), data-health dot, and the
  global kill-switch state. Tripped switch = full-width `crit` banner, non-dismissable
  until acknowledged.

## Charting

- Candles/price: `lightweight-charts` (TradingView OSS) — dark theme, tabular crosshair.
- Analytics (equity, distributions, scatter, Monte Carlo cone): `recharts` with the token palette.
- All charts: right-aligned last-value label, muted gridlines (`border` at 40% alpha).

## Accessibility & keyboard

- Contrast ≥ 4.5:1 for text tokens on `surface`. Focus rings use `accent`.
- Shortcuts: `⌘K` palette · `g d/t/l/p/r/a/i/s` go-to page · `⇧X` open kill-switch modal ·
  `Esc` close. Shortcuts listed in palette footer.
