import { useState, useEffect, useCallback } from 'react'
import { X, ChevronLeft, ChevronRight, ZoomIn, ZoomOut, Copy, Check } from 'lucide-react'
import { getChartPages } from '../api'
import type { Chart } from '../types'

interface Props {
  chart: Chart
  viewerName?: string
  onClose: () => void
}

export function ChartViewer({ chart, viewerName = 'anonymous', onClose }: Props) {
  const [pages, setPages] = useState<{ page: number; url: string }[]>([])
  const [currentPage, setCurrentPage] = useState(0)
  const [zoom, setZoom] = useState(1)
  const [loading, setLoading] = useState(true)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    setLoading(true)
    getChartPages(chart.id, viewerName)
      .then(d => { setPages(d.pages); setLoading(false) })
      .catch(() => setLoading(false))
  }, [chart.id, viewerName])

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(chart.chart_number)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }, [chart.chart_number])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowRight') setCurrentPage(p => Math.min(p + 1, pages.length - 1))
      if (e.key === 'ArrowLeft') setCurrentPage(p => Math.max(p - 1, 0))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, pages.length])

  return (
    <div style={styles.overlay}>
      <div style={styles.modal}>
        {/* Header */}
        <div style={styles.header}>
          <div style={styles.headerLeft}>
            <span style={styles.chartNum}>{chart.chart_number}</span>
            <span style={styles.meta}>{chart.specialty} · {chart.category} · {chart.difficulty}</span>
          </div>
          <div style={styles.headerRight}>
            <button style={styles.iconBtn} onClick={handleCopy} title="Copy chart number">
              {copied ? <Check size={16} color="#22c55e" /> : <Copy size={16} />}
            </button>
            <button style={styles.iconBtn} onClick={() => setZoom(z => Math.min(z + 0.25, 3))}><ZoomIn size={16} /></button>
            <button style={styles.iconBtn} onClick={() => setZoom(z => Math.max(z - 0.25, 0.5))}><ZoomOut size={16} /></button>
            <button style={{ ...styles.iconBtn, ...styles.closeBtn }} onClick={onClose}><X size={18} /></button>
          </div>
        </div>

        {/* Body */}
        <div style={styles.body}>
          {loading ? (
            <div style={styles.center}>Loading chart...</div>
          ) : pages.length === 0 ? (
            <div style={styles.center}>No pages found.</div>
          ) : (
            <img
              src={pages[currentPage]?.url}
              alt={`Page ${currentPage + 1}`}
              style={{ ...styles.pageImg, transform: `scale(${zoom})`, transformOrigin: 'top center' }}
            />
          )}
        </div>

        {/* Footer pagination */}
        {pages.length > 1 && (
          <div style={styles.footer}>
            <button style={styles.navBtn} disabled={currentPage === 0} onClick={() => setCurrentPage(p => p - 1)}>
              <ChevronLeft size={18} />
            </button>
            <span style={styles.pageLabel}>Page {currentPage + 1} of {pages.length}</span>
            <button style={styles.navBtn} disabled={currentPage === pages.length - 1} onClick={() => setCurrentPage(p => p + 1)}>
              <ChevronRight size={18} />
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  overlay: { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)', zIndex: 1000, display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: '24px' },
  modal: { background: '#fff', borderRadius: 8, width: '100%', maxWidth: 960, maxHeight: '95vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' },
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', borderBottom: '1px solid #e5e7eb', background: '#f9fafb' },
  headerLeft: { display: 'flex', flexDirection: 'column', gap: 2 },
  headerRight: { display: 'flex', gap: 8, alignItems: 'center' },
  chartNum: { fontWeight: 700, fontSize: 18, color: '#111' },
  meta: { fontSize: 13, color: '#6b7280' },
  iconBtn: { border: '1px solid #e5e7eb', background: '#fff', borderRadius: 6, padding: '4px 8px', cursor: 'pointer', display: 'flex', alignItems: 'center' },
  closeBtn: { borderColor: '#fca5a5', background: '#fef2f2' },
  body: { flex: 1, overflowY: 'auto', padding: 16, background: '#f3f4f6' },
  center: { display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200, color: '#6b7280' },
  pageImg: { display: 'block', margin: '0 auto', maxWidth: '100%', boxShadow: '0 2px 8px rgba(0,0,0,0.15)' },
  footer: { borderTop: '1px solid #e5e7eb', padding: '10px 16px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 16, background: '#f9fafb' },
  navBtn: { border: '1px solid #e5e7eb', background: '#fff', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', display: 'flex', alignItems: 'center' },
  pageLabel: { fontSize: 14, color: '#374151' },
}
