/**
 * Keeping charts legible as the data grows.
 *
 * The rule these helpers encode: a chart is for reading a shape at a glance,
 * and that only works up to roughly 20 categories. Past that, more data does
 * not make the chart more informative — it makes it unreadable, and the honest
 * move is to stop drawing all of it rather than to squeeze.
 *
 * Which way you cut depends on the question the chart answers:
 *
 *   TIME SERIES (batch trend, coder trend) — cut to the most RECENT n. The
 *   question is "where is this heading", so the newest points are the ones
 *   that matter and the oldest are the ones to drop.
 *
 *   RANKED BARS (by category, by coder) — cut to the top n by magnitude. The
 *   question is "who stands out", which the extremes answer and the middle
 *   does not.
 *
 * In both cases the full data stays available in the table beneath the chart,
 * so nothing is hidden — it moves to the control that scales, which is a
 * scrollable list, not a 3000px-tall axis.
 */

/** Above this many categories, a chart stops being readable at typical widths. */
export const CHART_LEGIBLE_MAX = 20

/** No chart should grow taller than roughly one screen. */
export const CHART_MAX_HEIGHT = 560

/** Window sizes offered for time-series charts. */
export const TREND_WINDOWS = [10, 25, 50] as const

/**
 * Height for a horizontal bar chart: proportional to row count, but capped so
 * a long list cannot produce a chart taller than the page it sits on.
 */
export function barHeight(rows: number, perRow = 48, min = 180): number {
  return Math.min(CHART_MAX_HEIGHT, Math.max(min, rows * perRow))
}

/** The most recent n points, in chronological order. */
export function recent<T>(data: T[], n: number | 'all'): T[] {
  if (n === 'all') return data
  return data.length <= n ? data : data.slice(-n)
}

/**
 * The n rows furthest from the middle — the best and worst performers.
 *
 * Taking the top n by score would hide every struggling row the moment the
 * list got long, which is the opposite of what this analytics page is for.
 */
export function extremes<T>(data: T[], key: (row: T) => number, n = CHART_LEGIBLE_MAX): T[] {
  if (data.length <= n) return data
  const sorted = [...data].sort((a, b) => key(a) - key(b))
  const half = Math.floor(n / 2)
  return [...sorted.slice(0, half), ...sorted.slice(-(n - half))]
}

/**
 * X-axis tick spacing. Recharts draws every label by default, which overlaps
 * into an unreadable band well before the line itself becomes useless.
 */
export function tickInterval(points: number, budget = 12): number {
  return points <= budget ? 0 : Math.ceil(points / budget) - 1
}

/** Truncate a category label to something an axis can render. */
export function axisLabel(text: string, max = 16): string {
  if (!text) return ''
  return text.length > max ? text.slice(0, max) + '…' : text
}
