import { useState, useEffect, useCallback, useRef } from 'react'
import { X, ChevronLeft, ChevronRight, ZoomIn, ZoomOut, Copy, Check, Search, ChevronUp, ChevronDown } from 'lucide-react'
import { getChartPages, searchInChart } from '../api'
import type { Chart } from '../types'
import { SPECIALTY_COLORS, DIFFICULTY_COLORS } from '../theme'

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
  const [showThumbs, setShowThumbs] = useState(true)
  const thumbsRef = useRef<HTMLDivElement>(null)

  // In-chart search
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<number[]>([])
  const [searchIdx, setSearchIdx] = useState(0)
  const [searching, setSearching] = useState(false)
  const [showSearch, setShowSearch] = useState(false)
  const searchInputRef = useRef<HTMLInputElement>(null)

  const specialtyColor = SPECIALTY_COLORS[chart.specialty]
  const diffColor = DIFFICULTY_COLORS[chart.difficulty]

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

  const handleSearch = useCallback(async () => {
    if (!searchQuery.trim()) { setSearchResults([]); return }
    setSearching(true)
    try {
      const res = await searchInChart(chart.id, searchQuery.trim())
      setSearchResults(res.matching_pages)
      setSearchIdx(0)
      if (res.matching_pages.length > 0) setCurrentPage(res.matching_pages[0])
    } finally { setSearching(false) }
  }, [chart.id, searchQuery])

  const navigateSearchResult = (dir: 'next' | 'prev') => {
    if (searchResults.length === 0) return
    const next = dir === 'next'
      ? (searchIdx + 1) % searchResults.length
      : (searchIdx - 1 + searchResults.length) % searchResults.length
    setSearchIdx(next)
    setCurrentPage(searchResults[next])
  }

  useEffect(() => {
    const el = thumbsRef.current?.querySelector(`[data-page="${currentPage}"]`) as HTMLElement
    el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [currentPage])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { if (showSearch) setShowSearch(false); else onClose() }
      if (e.key === 'ArrowRight' && !showSearch) setCurrentPage(p => Math.min(p + 1, pages.length - 1))
      if (e.key === 'ArrowLeft' && !showSearch) setCurrentPage(p => Math.max(p - 1, 0))
      if ((e.ctrlKey || e.metaKey) && e.key === 'f') { e.preventDefault(); setShowSearch(true); setTimeout(() => searchInputRef.current?.focus(), 50) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, pages.length, showSearch])

  const isMatchPage = searchResults.includes(currentPage)

  return (
    <div style={styles.overlay}>
      <div style={styles.modal}>
        {/* Specialty color bar */}
        <div style={{ height: 4, background: specialtyColor.bg, borderRadius: '8px 8px 0 0' }} />

        {/* Header */}
        <div style={styles.header}>
          <div style={styles.headerLeft}>
            <span style={styles.chartNum}>{chart.chart_number}</span>
            <div style={styles.headerMeta}>
              <span style={{ ...styles.specialtyBadge, background: specialtyColor.light, color: specialtyColor.bg }}>{chart.specialty}</span>
              <span style={styles.metaDot}>·</span>
              <span style={styles.metaText}>{chart.category}</span>
              <span style={styles.metaDot}>·</span>
              <span style={{ ...styles.diffBadge, ...diffColor }}>{chart.difficulty}</span>
            </div>
          </div>
          <div style={styles.headerRight}>
            <button style={{ ...styles.iconBtn, background: showThumbs ? '#ede9fe' : '#fff' }} onClick={() => setShowThumbs(s => !s)} title="Toggle page thumbnails">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke={showThumbs ? specialtyColor.bg : '#6b7280'} strokeWidth="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
            </button>
            <button style={styles.iconBtn} onClick={() => { setShowSearch(s => !s); setTimeout(() => searchInputRef.current?.focus(), 50) }} title="Search in chart (Ctrl+F)">
              <Search size={15} color={showSearch ? specialtyColor.bg : '#6b7280'} />
            </button>
            <button style={styles.iconBtn} onClick={handleCopy} title="Copy chart number">
              {copied ? <Check size={15} color="#22c55e" /> : <Copy size={15} />}
            </button>
            <button style={styles.iconBtn} onClick={() => setZoom(z => Math.min(z + 0.25, 3))} title="Zoom in"><ZoomIn size={15} /></button>
            <button style={styles.iconBtn} onClick={() => setZoom(z => Math.max(z - 0.25, 0.5))} title="Zoom out"><ZoomOut size={15} /></button>
            <button style={{ ...styles.iconBtn, ...styles.closeBtn }} onClick={onClose} title="Close (Esc)"><X size={17} /></button>
          </div>
        </div>

        {/* In-chart search bar */}
        {showSearch && (
          <div style={styles.searchBar}>
            <Search size={14} color="#9ca3af" />
            <input
              ref={searchInputRef}
              style={styles.searchInput}
              placeholder="Search text in chart..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleSearch() }}
            />
            <button style={styles.searchBtn} onClick={handleSearch} disabled={searching}>
              {searching ? '...' : 'Search'}
            </button>
            {searchResults.length > 0 && (
              <>
                <span style={styles.searchCount}>
                  {searchIdx + 1} / {searchResults.length} page{searchResults.length !== 1 ? 's' : ''}
                </span>
                <button style={styles.searchNavBtn} onClick={() => navigateSearchResult('prev')}><ChevronUp size={14} /></button>
                <button style={styles.searchNavBtn} onClick={() => navigateSearchResult('next')}><ChevronDown size={14} /></button>
              </>
            )}
            {searchResults.length === 0 && searchQuery && !searching && (
              <span style={styles.noMatch}>No matches found</span>
            )}
          </div>
        )}

        {/* Body */}
        <div style={styles.bodyWrap}>
          {/* Thumbnail strip */}
          {showThumbs && pages.length > 1 && (
            <div ref={thumbsRef} style={styles.thumbStrip}>
              {pages.map((p, i) => (
                <button
                  key={i}
                  data-page={i}
                  style={{
                    ...styles.thumbBtn,
                    border: i === currentPage ? `2px solid ${specialtyColor.bg}` : '2px solid transparent',
                    background: searchResults.includes(i) ? '#fef9c3' : '#fff',
                  }}
                  onClick={() => setCurrentPage(i)}
                  title={`Page ${i + 1}${searchResults.includes(i) ? ' — search match' : ''}`}
                >
                  <img src={p.url} alt={`Page ${i + 1}`} style={styles.thumbImg} />
                  <span style={{ ...styles.thumbLabel, color: i === currentPage ? specialtyColor.bg : '#9ca3af', fontWeight: i === currentPage ? 700 : 400 }}>
                    {i + 1}
                  </span>
                  {searchResults.includes(i) && <div style={styles.thumbMatchDot} />}
                </button>
              ))}
            </div>
          )}

          {/* Main page */}
          <div style={styles.body}>
            {loading ? (
              <div style={styles.center}>
                <div style={styles.spinner} />
                <span>Loading chart...</span>
              </div>
            ) : pages.length === 0 ? (
              <div style={styles.center}>No pages found.</div>
            ) : (
              <div style={{ position: 'relative' }}>
                {isMatchPage && (
                  <div style={styles.matchBanner}>
                    🔍 Search match found on this page
                  </div>
                )}
                <img
                  src={pages[currentPage]?.url}
                  alt={`Page ${currentPage + 1}`}
                  style={{ ...styles.pageImg, transform: `scale(${zoom})`, transformOrigin: 'top center', outline: isMatchPage ? `3px solid ${specialtyColor.bg}` : 'none' }}
                />
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div style={styles.footer}>
          {pages.length > 1 ? (
            <>
              <button style={styles.navBtn} disabled={currentPage === 0} onClick={() => setCurrentPage(p => p - 1)}>
                <ChevronLeft size={16} />
              </button>
              <div style={styles.pageInfo}>
                <span style={styles.pageLabel}>Page {currentPage + 1} of {pages.length}</span>
              </div>
              <button style={styles.navBtn} disabled={currentPage === pages.length - 1} onClick={() => setCurrentPage(p => p + 1)}>
                <ChevronRight size={16} />
              </button>
            </>
          ) : (
            <span style={styles.pageLabel}>1 page</span>
          )}
          <span style={styles.keyHint}>← → navigate &nbsp;·&nbsp; Ctrl+F search &nbsp;·&nbsp; Esc close</span>
        </div>
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  overlay: { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)', zIndex: 1000, display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: '20px', backdropFilter: 'blur(2px)' },
  modal: { background: '#fff', borderRadius: 10, width: '100%', maxWidth: 1000, maxHeight: '96vh', display: 'flex', flexDirection: 'column', overflow: 'hidden', boxShadow: '0 25px 50px rgba(0,0,0,0.4)' },
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', borderBottom: '1px solid #e5e7eb', background: '#fafafa' },
  headerLeft: { display: 'flex', flexDirection: 'column', gap: 5 },
  headerRight: { display: 'flex', gap: 6, alignItems: 'center' },
  headerMeta: { display: 'flex', alignItems: 'center', gap: 6 },
  chartNum: { fontWeight: 800, fontSize: 20, color: '#111', letterSpacing: -0.5 },
  specialtyBadge: { fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 20, textTransform: 'uppercase' as const, letterSpacing: 0.5 },
  diffBadge: { fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 20 },
  metaDot: { color: '#d1d5db', fontSize: 12 },
  metaText: { fontSize: 12, color: '#6b7280' },
  iconBtn: { border: '1px solid #e5e7eb', background: '#fff', borderRadius: 6, padding: '5px 9px', cursor: 'pointer', display: 'flex', alignItems: 'center', transition: 'all 0.15s' },
  closeBtn: { borderColor: '#fca5a5', background: '#fff5f5' },
  searchBar: { display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px', background: '#f8fafc', borderBottom: '1px solid #e5e7eb' },
  searchInput: { flex: 1, padding: '6px 10px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13, outline: 'none' },
  searchBtn: { padding: '6px 14px', background: '#4f46e5', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 13, fontWeight: 600 },
  searchCount: { fontSize: 12, color: '#6b7280', whiteSpace: 'nowrap' as const },
  searchNavBtn: { border: '1px solid #e5e7eb', background: '#fff', borderRadius: 5, padding: '3px 7px', cursor: 'pointer', display: 'flex', alignItems: 'center' },
  noMatch: { fontSize: 12, color: '#ef4444' },
  bodyWrap: { flex: 1, display: 'flex', overflow: 'hidden' },
  thumbStrip: { width: 90, overflowY: 'auto', background: '#f9fafb', borderRight: '1px solid #e5e7eb', display: 'flex', flexDirection: 'column', gap: 6, padding: '10px 6px', flexShrink: 0 },
  thumbBtn: { borderRadius: 6, padding: 4, cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3, position: 'relative' as const, transition: 'border-color 0.15s' },
  thumbImg: { width: '100%', borderRadius: 4, display: 'block', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' },
  thumbLabel: { fontSize: 10 },
  thumbMatchDot: { position: 'absolute' as const, top: 4, right: 4, width: 7, height: 7, borderRadius: '50%', background: '#f59e0b' },
  body: { flex: 1, overflowY: 'auto', padding: 20, background: '#f3f4f6' },
  center: { display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 200, color: '#9ca3af', gap: 12 },
  spinner: { width: 28, height: 28, border: '3px solid #e5e7eb', borderTopColor: '#4f46e5', borderRadius: '50%', animation: 'spin 0.8s linear infinite' },
  pageImg: { display: 'block', margin: '0 auto', maxWidth: '100%', boxShadow: '0 4px 12px rgba(0,0,0,0.15)', borderRadius: 4, transition: 'outline 0.2s' },
  matchBanner: { textAlign: 'center', padding: '6px', background: '#fef9c3', color: '#854d0e', fontSize: 12, fontWeight: 600, borderRadius: 4, marginBottom: 10 },
  footer: { borderTop: '1px solid #e5e7eb', padding: '10px 16px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12, background: '#fafafa' },
  navBtn: { border: '1px solid #e5e7eb', background: '#fff', borderRadius: 6, padding: '5px 12px', cursor: 'pointer', display: 'flex', alignItems: 'center', transition: 'all 0.15s' },
  pageInfo: { display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 },
  pageLabel: { fontSize: 13, fontWeight: 600, color: '#374151' },
  keyHint: { fontSize: 11, color: '#c4c4c4', marginLeft: 'auto' },
}
