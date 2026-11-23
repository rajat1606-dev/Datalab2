// Client-side Plotly theming. Mirrors the CSS theme in src/theme.css so
// charts recolor instantly when the Day/Night mode flips — without any
// backend changes. Only layout-level properties are overridden here
// (backgrounds, text, gridlines, legends, series palette); trace data is
// left untouched, and traces without explicit colours inherit `colorway`.

export const CHART_THEMES = {
  night: {
    bg: '#101B2E',
    text: '#A4B1C5',
    title: '#E8EEF9',
    axisTitle: '#C6D2E4',
    grid: '#25334E',
    line: '#33415E',
    hoverBg: '#1C2940',
    hoverBorder: '#3A4C6B',
    mutedMark: '#64789A',
    colorway: ['#6295FF', '#2DD4BF', '#A78BFA', '#34D399', '#FBBF24', '#FB7185', '#60A5FA', '#F472B6'],
  },
  day: {
    bg: '#FFFFFF',
    text: '#64748B',
    title: '#172B4D',
    axisTitle: '#33456B',
    grid: '#E5EAF1',
    line: '#C9D3E0',
    hoverBg: '#EDF2F8',
    hoverBorder: '#C9D3E0',
    mutedMark: '#9AA8BC',
    colorway: ['#356AE6', '#0D9488', '#7C3AED', '#0E9F6E', '#D97706', '#DC2626', '#2563EB', '#DB2777'],
  },
}

export function currentChartMode() {
  const t = typeof document !== 'undefined' ? document.documentElement.dataset.theme : ''
  return t === 'day' ? 'day' : 'night'
}

/** Series colour palette for the active theme (for inline trace markers). */
export function chartPalette(mode = currentChartMode()) {
  return (CHART_THEMES[mode] || CHART_THEMES.night).colorway
}

/** Neutral marker colour (e.g. "other" pie slice) for the active theme. */
export function chartMuted(mode = currentChartMode()) {
  return (CHART_THEMES[mode] || CHART_THEMES.night).mutedMark
}

const mergeFont = (font, color) => ({ ...(font || {}), color })

/** Merge the active theme into any figure layout (backend or client-built). */
export function applyChartTheme(layout = {}, mode = currentChartMode()) {
  const t = CHART_THEMES[mode] || CHART_THEMES.night
  const themed = {
    ...layout,
    paper_bgcolor: t.bg,
    plot_bgcolor: t.bg,
    colorway: t.colorway,
    font: mergeFont(layout.font, t.text),
    hoverlabel: {
      ...(layout.hoverlabel || {}),
      bgcolor: t.hoverBg,
      bordercolor: t.hoverBorder,
      font: mergeFont(layout.hoverlabel?.font, t.title),
    },
    legend: {
      ...(layout.legend || {}),
      bgcolor: 'rgba(0,0,0,0)',
      bordercolor: t.hoverBorder,
      borderwidth: layout.legend?.borderwidth ?? 1,
    },
  }
  if (layout.title) {
    themed.title = typeof layout.title === 'string'
      ? { text: layout.title, font: { size: 15, color: t.title }, x: 0.005, xanchor: 'left' }
      : { ...layout.title, font: mergeFont(layout.title.font, t.title) }
  }
  for (const axis of ['xaxis', 'yaxis', 'xaxis2', 'yaxis2', 'xaxis3', 'yaxis3']) {
    const a = layout[axis]
    if (!a) continue
    themed[axis] = {
      ...a,
      gridcolor: t.grid,
      zerolinecolor: t.line,
      ...(a.linecolor ? { linecolor: t.line } : {}),
      tickfont: mergeFont(a.tickfont, t.text),
      title_font: mergeFont(a.title_font, t.axisTitle),
    }
  }
  return themed
}

/** Base layout for charts built in the browser, in the active theme. */
export function themedLayout(title, { height = 330, margins } = {}, mode = currentChartMode()) {
  return applyChartTheme({
    title: { text: title, font: { size: 15 }, x: 0.005, xanchor: 'left' },
    margin: margins || { l: 60, r: 24, t: 56, b: 54 },
    height,
    autosize: true,
  }, mode)
}
