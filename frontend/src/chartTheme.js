// Client-side Plotly layout helper that mirrors the backend dark theme,
// used for the small dashboard charts built in the browser.
export const CHART_BG = '#0f172a'

export function themedLayout(title, { height = 330, margins } = {}) {
  return {
    paper_bgcolor: CHART_BG,
    plot_bgcolor: CHART_BG,
    font: { family: "Inter, 'Segoe UI', system-ui, sans-serif", size: 12.5, color: '#9fb0c9' },
    title: { text: title, font: { size: 15, color: '#e7edf6' }, x: 0.005, xanchor: 'left' },
    colorway: ['#3b82f6', '#22d3ee', '#a78bfa', '#34d399', '#fbbf24', '#fb7185'],
    margin: margins || { l: 60, r: 24, t: 56, b: 54 },
    height,
    autosize: true,
    hoverlabel: { bgcolor: '#1b2540', bordercolor: '#33415e', font: { color: '#e7edf6' } },
    legend: { bgcolor: 'rgba(0,0,0,0)', bordercolor: '#33415e', borderwidth: 1 },
    xaxis: { gridcolor: '#22304d', zerolinecolor: '#33415e', linecolor: '#33415e', tickfont: { color: '#9fb0c9' }, title_font: { color: '#c6d2e4' } },
    yaxis: { gridcolor: '#22304d', zerolinecolor: '#33415e', linecolor: '#33415e', tickfont: { color: '#9fb0c9' }, title_font: { color: '#c6d2e4' } },
  }
}
