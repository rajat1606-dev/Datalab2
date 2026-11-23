import { useEffect, useRef } from 'react'
import Plotly from 'plotly.js-dist-min'
import { useApp } from '../context'
import { applyChartTheme } from '../chartTheme'

const CONFIG = {
  responsive: true,
  displaylogo: false,
  modeBarButtonsToRemove: ['lasso2d', 'select2d', 'toggleSpikelines'],
  doubleClick: 'reset',
}

/**
 * Renders a Plotly figure ({ data, layout }) produced by the backend or built
 * in the browser. Supports full touch interactions (zoom / pan / tap) which
 * also makes it Android-ready via Capacitor.
 */
export default function ChartRenderer({ figure, plotRef, emptyText }) {
  const divRef = useRef(null)
  const { theme } = useApp()

  useEffect(() => {
    if (plotRef) plotRef.current = divRef.current
  }, [plotRef])

  useEffect(() => {
    const el = divRef.current
    if (!el) return undefined
    if (figure && Array.isArray(figure.data) && figure.data.length > 0) {
      // Re-theme the layout (backgrounds, text, gridlines, palette) so
      // backend and client-built figures both follow the Day/Night mode.
      const layout = applyChartTheme({ ...figure.layout, autosize: true }, theme)
      Plotly.react(el, figure.data, layout, CONFIG).then(() => {
        Plotly.Plots.resize(el)
      })
    } else {
      Plotly.purge(el)
    }
    return () => {
      try { Plotly.purge(el) } catch { /* ignore */ }
    }
  }, [figure, theme])

  useEffect(() => {
    const onResize = () => {
      if (divRef.current && figure) Plotly.Plots.resize(divRef.current)
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [figure])

  if (!figure || !Array.isArray(figure.data) || figure.data.length === 0) {
    return <div className="chart-empty">{emptyText || 'Nothing to display yet.'}</div>
  }
  return <div ref={divRef} style={{ width: '100%' }} />
}
