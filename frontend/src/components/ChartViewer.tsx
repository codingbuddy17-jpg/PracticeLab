import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { X, ChevronLeft, ChevronRight, ZoomIn, ZoomOut, Copy, Check, Search, ChevronUp, ChevronDown, Flag, Highlighter } from 'lucide-react'
import toast from 'react-hot-toast'
import { getChartPages, getChartText, searchInChart, submitFeedback } from '../api'
import type { Chart } from '../types'
import { SPECIALTY_COLORS, DIFFICULTY_COLORS } from '../theme'
import { parseChart, AID_PATTERNS, type Block } from './chartDocument'

interface Props {
  chart: Chart
  viewerName?: string
  onClose: () => void
}

const API_BASE = import.meta.env.VITE_API_URL || '/api'
function pageImgUrl(path: string) {
  return path.startsWith('http') ? path : `${API_BASE}${path}`
}

function escapedRegex(raw: string) {
  return raw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

const AID_RE = new RegExp(`(${AID_PATTERNS.uncertain.source})|(${AID_PATTERNS.linkage.source})`, 'gi')

/** Search matches always; uncertain / linkage wording only when aids are on. */
function HighlightedText({ text, query, aids = false }: { text: string; query: string; aids?: boolean }) {
  const q = query.trim()
  const withAids = (chunk: string, key: string) => {
    if (!aids) return <span key={key}>{chunk}</span>
    const out: React.ReactNode[] = []
    let last = 0
    chunk.replace(AID_RE, (m, unc, _u2, link, _l2, offset: number) => {
      if (offset > last) out.push(chunk.slice(last, offset))
      out.push(<mark key={`${key}-${offset}`} style={unc ? styles.aidUncertain : styles.aidLinkage}
        title={unc ? 'Uncertain diagnosis wording' : 'Linkage wording'}>{m}</mark>)
      last = offset + m.length
      return m
    })
    if (last < chunk.length) out.push(chunk.slice(last))
    return <span key={key}>{out}</span>
  }
  if (!q) return withAids(text, 't')
  const parts = text.split(new RegExp(`(${escapedRegex(q)})`, 'ig'))
  return (
    <>
      {parts.map((part, idx) => part.toLowerCase() === q.toLowerCase()
        ? <mark key={idx} style={styles.searchMark}>{part}</mark>
        : withAids(part, `p${idx}`))}
    </>
  )
}

function blockText(b: Block) {
  switch (b.kind) {
    case 'doc': return b.title
    case 'heading': return `${b.title} ${b.inline}`
    case 'field': return `${b.label}: ${b.value}`
    case 'list': return `${b.marker} ${b.text}`
    case 'text': case 'signature': return b.text
    default: return ''
  }
}

function readPref(key: string): string | null {
  try { return localStorage.getItem(key) } catch { return null }
}
function writePref(key: string, value: string) {
  try { localStorage.setItem(key, value) } catch { /* private window: fine */ }
}

function containsQuery(text: string, query: string) {
  const q = query.trim().toLowerCase()
  return !!q && text.toLowerCase().includes(q)
}

export function ChartViewer({ chart, viewerName = 'anonymous', onClose }: Props) {
  const [pages, setPages] = useState<{ page: number; url: string }[]>([])
  const [textPages, setTextPages] = useState<{ page: number; text: string; has_text: boolean }[]>([])
  const [textLoaded, setTextLoaded] = useState(false)
  const [textLoading, setTextLoading] = useState(false)
  const [textAvailable, setTextAvailable] = useState(false)
  // Image, Text, or Split (scan beside text, kept on the same page) — the last
  // so a coder can check extracted text against the original.
  const [viewMode, setViewMode] = useState<'image' | 'text' | 'split'>('image')
  const [activeSection, setActiveSection] = useState<string | null>(null)
  // Coding aids are the reader's choice, off unless they turn them on, and
  // remembered across charts for that reader.
  const [aidsOn, setAidsOn] = useState(() => readPref('cv:aids') === '1')
  const textPaneRef = useRef<HTMLDivElement>(null)
  const restoredRef = useRef(false)
  const jumpLockRef = useRef<{ id: string; until: number } | null>(null)  // set by a jump, cleared by the reader's own scrolling
  const [currentPage, setCurrentPage] = useState(0)
  const [zoom, setZoom] = useState(1)
  const [loading, setLoading] = useState(true)
  const [copied, setCopied] = useState(false)
  const [showThumbs, setShowThumbs] = useState(true)
  const thumbsRef = useRef<HTMLDivElement>(null)

  // Feedback
  const [showFeedback, setShowFeedback] = useState(false)
  const [selectedIssues, setSelectedIssues] = useState<string[]>([])
  const [feedbackNotes, setFeedbackNotes] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const ISSUE_OPTIONS = [
    '🔍 Chart is illegible / poor scan quality',
    '🔒 Possible PHI visible',
    '📄 Missing pages',
    '❌ Wrong chart / incorrect content',
    '💬 Other',
  ]

  const toggleIssue = (issue: string) => {
    setSelectedIssues(prev => prev.includes(issue) ? prev.filter(i => i !== issue) : [...prev, issue])
  }

  const handleSubmitFeedback = async () => {
    if (selectedIssues.length === 0) { toast.error('Select at least one issue'); return }
    setSubmitting(true)
    try {
      await submitFeedback({
        chart_id: chart.id,
        reporter: viewerName,
        issues: selectedIssues,
        notes: feedbackNotes.trim() || undefined,
      })
      toast.success('Feedback submitted — thank you!')
      setShowFeedback(false)
      setSelectedIssues([])
      setFeedbackNotes('')
    } catch {
      toast.error('Failed to submit feedback')
    } finally {
      setSubmitting(false)
    }
  }

  // In-chart search
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<number[]>([])
  const [searchSnippets, setSearchSnippets] = useState<{ page: number; snippet: string }[]>([])
  const [searchIdx, setSearchIdx] = useState(0)
  const [searching, setSearching] = useState(false)
  const [showSearch, setShowSearch] = useState(false)
  const [targetMatchPage, setTargetMatchPage] = useState<number | null>(null)
  const searchInputRef = useRef<HTMLInputElement>(null)

  const specialtyColor = SPECIALTY_COLORS[chart.specialty]
  const diffColor = DIFFICULTY_COLORS[chart.difficulty]

  useEffect(() => {
    setLoading(true)
    const saved = readPref(`cv:pos:${chart.id}`)
    const savedMode = saved ? saved.split('|')[0] : ''
    setViewMode(savedMode === 'text' || savedMode === 'split' ? savedMode : 'image')
    restoredRef.current = false
    setActiveSection(null)
    setTextPages([])
    setTextLoaded(false)
    setTextAvailable(false)
    getChartPages(chart.id, viewerName)
      .then(d => { setPages(d.pages); setLoading(false) })
      .catch(() => setLoading(false))
  }, [chart.id, viewerName])

  useEffect(() => {
    if (viewMode === 'image' || textLoaded || textLoading) return
    setTextLoading(true)
    getChartText(chart.id)
      .then(d => {
        setTextPages(d.pages)
        setTextAvailable(d.has_text)
        setTextLoaded(true)
      })
      .catch(() => {
        setTextPages([])
        setTextAvailable(false)
        toast.error('Chart text could not be loaded')
      })
      .finally(() => setTextLoading(false))
  }, [chart.id, textLoaded, textLoading, viewMode])

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(chart.chart_number)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }, [chart.chart_number])

  const handleSearch = useCallback(async () => {
    if (!searchQuery.trim()) { setSearchResults([]); setSearchSnippets([]); setTargetMatchPage(null); return }
    setSearching(true)
    try {
      const res = await searchInChart(chart.id, searchQuery.trim())
      setSearchResults(res.matching_pages)
      setSearchSnippets((res.snippets || []).filter(s => s.snippet))
      setSearchIdx(0)
      if (res.matching_pages.length > 0) {
        setCurrentPage(res.matching_pages[0])
        setTargetMatchPage(res.matching_pages[0])
      }
    } finally { setSearching(false) }
  }, [chart.id, searchQuery])

  function clearSearch() {
    setSearchQuery('')
    setSearchResults([])
    setSearchSnippets([])
    setSearchIdx(0)
    setTargetMatchPage(null)
  }

  const navigateSearchResult = (dir: 'next' | 'prev') => {
    if (searchResults.length === 0) return
    const next = dir === 'next'
      ? (searchIdx + 1) % searchResults.length
      : (searchIdx - 1 + searchResults.length) % searchResults.length
    setSearchIdx(next)
    setCurrentPage(searchResults[next])
    setTargetMatchPage(searchResults[next])
  }

  useEffect(() => {
    const el = thumbsRef.current?.querySelector(`[data-page="${currentPage}"]`) as HTMLElement
    el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [currentPage])

  useEffect(() => {
    if (viewMode === 'image' || targetMatchPage === null || textLoading) return
    const el = document.getElementById(`chart-text-match-${targetMatchPage}`)
      || document.getElementById(`chart-text-page-${targetMatchPage}`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [targetMatchPage, textLoading, textLoaded, viewMode])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { if (showSearch) setShowSearch(false); else onClose() }
      if (e.key === 'ArrowRight' && !showSearch) setCurrentPage(p => Math.min(p + 1, pages.length - 1))
      if (e.key === 'ArrowLeft' && !showSearch) setCurrentPage(p => Math.max(p - 1, 0))
      if ((e.ctrlKey || e.metaKey) && e.key === 'f') { e.preventDefault(); setShowSearch(true); setTimeout(() => searchInputRef.current?.focus(), 50) }
      const typing = (e.target as HTMLElement)?.tagName === 'INPUT' || (e.target as HTMLElement)?.tagName === 'TEXTAREA'
      if (e.key === '/' && !typing) { e.preventDefault(); setShowSearch(true); setTimeout(() => searchInputRef.current?.focus(), 50) }
      if (e.altKey && (e.key === 'ArrowDown' || e.key === 'ArrowUp') && viewModeRef.current !== 'image') {
        e.preventDefault()
        stepSectionRef.current(e.key === 'ArrowDown' ? 1 : -1)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, pages.length, showSearch])

  const isMatchPage = searchResults.includes(currentPage)
  const parsed = useMemo(() => parseChart(textPages), [textPages])
  const flatSections = useMemo(() => parsed.docs.flatMap(d => d.sections), [parsed])

  /** Scroll the text pane so an element sits at its top. */
  const jumpTo = useCallback((id: string) => {
    const pane = textPaneRef.current
    const el = document.getElementById(id)
    if (!pane || !el) return
    // Hold the clicked section while the smooth scroll runs: the scroll
    // tracker would otherwise credit whatever passes under it on the way, or,
    // near the end of a chart that cannot scroll that far, an earlier section.
    jumpLockRef.current = { id, until: Infinity }
    pane.scrollTo({ top: el.offsetTop - 8, behavior: 'smooth' })
    setActiveSection(id)
    // The page this heading sits on, so the scan beside it follows at once
    // rather than waiting for the smooth scroll to arrive.
    const pageEl = el.closest('[data-page-anchor]') as HTMLElement | null
    if (pageEl) setCurrentPage(Number(pageEl.dataset.pageAnchor))
    writePref(`cv:pos:${chart.id}`, `${viewModeRef.current}|${id}`)
  }, [chart.id])

  // Alt+↓ / Alt+↑ step through sections. Refs, so the key handler registered
  // once always sees the current chart and mode.
  const viewModeRef = useRef(viewMode)
  viewModeRef.current = viewMode
  const stepSectionRef = useRef<(dir: number) => void>(() => {})
  stepSectionRef.current = (dir: number) => {
    if (!flatSections.length) return
    const i = flatSections.findIndex(x => x.id === activeSection)
    const next = flatSections[Math.min(flatSections.length - 1, Math.max(0, i + dir))]
    if (next) jumpTo(next.id)
  }

  // Which section and page are on screen, as an EHR navigator highlights them.
  const onTextScroll = useCallback(() => {
    const pane = textPaneRef.current
    if (!pane) return
    // Until the reader scrolls by hand, the section they jumped to stays theirs.
    if (jumpLockRef.current) return
    const top = pane.scrollTop + 24
    let sec: string | null = null
    const heads = pane.querySelectorAll<HTMLElement>('[data-sec]')
    heads.forEach(el => { if (el.offsetTop <= top) sec = el.id })
    // Scrolled to the very end: the last sections can never reach the top of
    // the pane, so the reader is in the last one.
    if (pane.scrollTop + pane.clientHeight >= pane.scrollHeight - 4 && heads.length) {
      sec = heads[heads.length - 1].id
    }
    let pg: number | null = null
    pane.querySelectorAll<HTMLElement>('[data-page-anchor]').forEach(el => {
      if (el.offsetTop <= top) pg = Number(el.dataset.pageAnchor)
    })
    setActiveSection(sec)
    if (pg !== null) setCurrentPage(pg)
    writePref(`cv:pos:${chart.id}`, `${viewModeRef.current}|${sec || ''}`)
  }, [chart.id])

  // Reopen where the reader left off: their mode, and the section they were in.
  useEffect(() => {
    if (viewMode === 'image' || restoredRef.current || !textLoaded) return
    restoredRef.current = true
    const saved = (readPref(`cv:pos:${chart.id}`) || '').split('|')[1]
    if (saved && document.getElementById(saved)) setTimeout(() => jumpTo(saved), 60)
  }, [viewMode, textLoaded, chart.id, jumpTo])

  /** The reader took over scrolling: let the tracker follow them again. */
  const releaseJump = useCallback(() => { jumpLockRef.current = null }, [])

  /** Change mode and remember it for this chart. Only a reader's choice is
   *  written — never the mode a first render happens to start in. */
  function changeMode(m: 'image' | 'text' | 'split') {
    setViewMode(m)
    writePref(`cv:pos:${chart.id}`, `${m}|${m === 'image' ? '' : activeSection || ''}`)
  }

  function toggleAids() {
    setAidsOn(v => { writePref('cv:aids', v ? '0' : '1'); return !v })
  }

  return (
    <div style={styles.overlay}>
      <div style={{ ...styles.modal, maxWidth: viewMode === 'split' ? 1560 : viewMode === 'text' ? 1240 : 1000 }}>
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
            <div style={styles.viewToggle} aria-label="Chart view mode">
              {(['image', 'text', 'split'] as const).map(m => (
                <button key={m}
                  style={{ ...styles.viewToggleBtn, ...(viewMode === m ? styles.viewToggleActive : {}) }}
                  onClick={() => changeMode(m)}
                  title={m === 'split' ? 'Scanned page beside its text' : undefined}
                >
                  {m === 'image' ? 'Image' : m === 'text' ? 'Text' : 'Side by side'}
                </button>
              ))}
            </div>
            {viewMode !== 'image' && (
              <button
                style={{ ...styles.iconBtn, gap: 5, fontSize: 12, fontWeight: 700, color: aidsOn ? '#92400e' : '#6b7280', background: aidsOn ? '#fffbeb' : '#fff', borderColor: aidsOn ? '#fcd34d' : '#e5e7eb' }}
                onClick={toggleAids}
                title="Highlight uncertain-diagnosis and linkage wording"
              >
                <Highlighter size={14} /> Coding aids
              </button>
            )}
            <button style={styles.iconBtn} onClick={() => { setShowSearch(s => !s); setTimeout(() => searchInputRef.current?.focus(), 50) }} title="Search in chart (Ctrl+F)">
              <Search size={15} color={showSearch ? specialtyColor.bg : '#6b7280'} />
            </button>
            <button style={styles.iconBtn} onClick={handleCopy} title="Copy chart number">
              {copied ? <Check size={15} color="#22c55e" /> : <Copy size={15} />}
            </button>
            <button style={styles.iconBtn} onClick={() => setZoom(z => Math.min(z + 0.25, 3))} title="Zoom in"><ZoomIn size={15} /></button>
            <button style={styles.iconBtn} onClick={() => setZoom(z => Math.max(z - 0.25, 0.5))} title="Zoom out"><ZoomOut size={15} /></button>
            <button
              style={{ ...styles.iconBtn, borderColor: showFeedback ? '#fca5a5' : '#e5e7eb', background: showFeedback ? '#fff5f5' : '#fff' }}
              onClick={() => setShowFeedback(s => !s)}
              title="Report an issue with this chart"
            >
              <Flag size={15} color={showFeedback ? '#dc2626' : '#6b7280'} />
            </button>
            <button style={{ ...styles.iconBtn, ...styles.closeBtn }} onClick={onClose} title="Close (Esc)"><X size={17} /></button>
          </div>
        </div>

        {/* In-chart search bar */}
        {showSearch && (
          <div style={styles.searchPanel}>
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
              {searchQuery && (
                <button style={styles.clearSearchBtn} onClick={clearSearch} title="Clear search">
                  <X size={13} />
                </button>
              )}
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
            {searchSnippets.length > 0 && (
              <div style={styles.snippetList}>
                {searchSnippets.slice(0, 8).map((item, idx) => (
                  <button
                    key={`${item.page}-${idx}`}
                    style={{
                      ...styles.snippetBtn,
                      borderColor: item.page === currentPage ? specialtyColor.bg : '#e5e7eb',
                    }}
                    onClick={() => {
                      setSearchIdx(Math.max(0, searchResults.indexOf(item.page)))
                      setCurrentPage(item.page)
                      setTargetMatchPage(item.page)
                      if (viewMode === 'image') changeMode('text')
                    }}
                  >
                    <span style={styles.snippetPage}>Page {item.page + 1}</span>
                    <span style={styles.snippetText}>
                      <HighlightedText text={item.snippet} query={searchQuery} />
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Feedback panel */}
        {showFeedback && (
          <div style={styles.feedbackPanel}>
            <div style={styles.feedbackTitle}><Flag size={14} color="#dc2626" /> Report an issue with {chart.chart_number}</div>
            <div style={styles.issueList}>
              {ISSUE_OPTIONS.map(issue => (
                <label key={issue} style={styles.issueRow}>
                  <input
                    type="checkbox"
                    checked={selectedIssues.includes(issue)}
                    onChange={() => toggleIssue(issue)}
                  />
                  <span style={styles.issueLabel}>{issue}</span>
                </label>
              ))}
            </div>
            <textarea
              style={styles.feedbackNotes}
              placeholder="Additional notes (optional)"
              value={feedbackNotes}
              onChange={e => setFeedbackNotes(e.target.value)}
              rows={2}
            />
            <div style={styles.feedbackActions}>
              <button style={styles.submitBtn} onClick={handleSubmitFeedback} disabled={submitting}>
                {submitting ? 'Submitting...' : 'Submit Feedback'}
              </button>
              <button style={styles.cancelFeedbackBtn} onClick={() => { setShowFeedback(false); setSelectedIssues([]); setFeedbackNotes('') }}>
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Body */}
        <div style={styles.bodyWrap}>
          {/* Thumbnail strip */}
          {viewMode === 'image' && showThumbs && pages.length > 1 && (
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
                  <img src={pageImgUrl(p.url)} alt={`Page ${i + 1}`} style={styles.thumbImg} />
                  <span style={{ ...styles.thumbLabel, color: i === currentPage ? specialtyColor.bg : '#9ca3af', fontWeight: i === currentPage ? 700 : 400 }}>
                    {i + 1}
                  </span>
                  {searchResults.includes(i) && <div style={styles.thumbMatchDot} />}
                </button>
              ))}
            </div>
          )}

          {/* Main page */}
          <div style={viewMode === 'image' ? styles.body : styles.bodyDoc}>
            {viewMode !== 'image' ? (
              textLoading ? (
                <div style={styles.center}>
                  <div style={styles.spinner} />
                  <span>Loading chart text...</span>
                </div>
              ) : !textAvailable ? (
                <div style={styles.center}>
                  Text is not available for this chart — it was uploaded as a scan or image.
                  <button style={styles.textPageBtn} onClick={() => changeMode('image')}>View the image</button>
                </div>
              ) : (
                <div style={styles.docLayout}>
                  {/* Navigator: documents, then their sections, in chart order */}
                  <nav style={styles.navigator} aria-label="Chart contents">
                    <div style={styles.navHead}>
                      Contents
                      <span style={styles.navCount}>{parsed.sectionCount} section{parsed.sectionCount !== 1 ? 's' : ''}</span>
                    </div>
                    {parsed.docs.length === 0 && (
                      <div style={styles.navEmpty}>No section headings recognised. The full text is shown.</div>
                    )}
                    {parsed.docs.map(d => (
                      <div key={d.id} style={{ marginBottom: 8 }}>
                        <button style={styles.navDoc} onClick={() => jumpTo(d.id)} title={d.title}>
                          <span style={styles.navDocType}>{d.type}</span>
                          <span style={styles.navDocTitle}>{d.title !== d.type ? d.title : ''}</span>
                          <span style={styles.navPage}>p{d.page + 1}</span>
                        </button>
                        {d.sections.map(sec => {
                          const on = sec.id === activeSection
                          return (
                            <button key={sec.id} onClick={() => jumpTo(sec.id)} title={sec.title}
                              style={{ ...styles.navSec, ...(on ? { ...styles.navSecOn, borderLeft: `3px solid ${specialtyColor.bg}`, color: specialtyColor.bg } : {}) }}>
                              <span style={styles.navSecLabel}>{sec.label}</span>
                              <span style={styles.navPage}>p{sec.page + 1}</span>
                            </button>
                          )
                        })}
                      </div>
                    ))}
                    <div style={styles.navKeys}>Alt+↓ / Alt+↑ next / previous section · / search</div>
                  </nav>

                  {/* The document, as a note */}
                  <div ref={textPaneRef} onScroll={onTextScroll} style={styles.docPane}
                    onWheel={releaseJump} onTouchStart={releaseJump} onMouseDown={releaseJump} onKeyDown={releaseJump}>
                    {aidsOn && (
                      <div style={styles.aidLegend}>
                        <mark style={styles.aidUncertain}>uncertain wording</mark>
                        <mark style={styles.aidLinkage}>linkage wording</mark>
                        <span>highlighted to notice, not an answer</span>
                      </div>
                    )}
                    {parsed.pages.map(page => (
                      <section id={`chart-text-page-${page.page}`} data-page-anchor={page.page} key={page.page} style={{ ...styles.textPage, flexShrink: 0 }}>
                        <div style={styles.textPageHeader}>
                          <span>Page {page.page + 1}</span>
                          {viewMode === 'text' && (
                            <button style={styles.textPageBtn} onClick={() => { setCurrentPage(page.page); changeMode('image') }}>
                              View Image
                            </button>
                          )}
                        </div>
                        {page.has_text ? (
                          <div style={styles.pageText}>
                            {page.blocks.map((block, idx) => {
                              const matchId = page.page === targetMatchPage && containsQuery(blockText(block), searchQuery)
                                ? `chart-text-match-${page.page}` : undefined
                              const hl = (t: string) => <HighlightedText text={t} query={searchQuery} aids={aidsOn} />
                              switch (block.kind) {
                                case 'gap': return <div key={idx} style={styles.textGap} />
                                case 'doc': return (
                                  <div id={block.id} key={idx} style={styles.docBand}>
                                    <span style={styles.docBandType}>{block.type}</span>
                                    <span>{hl(block.title)}</span>
                                  </div>
                                )
                                case 'heading': return (
                                  <div key={idx}>
                                    <div id={block.id} data-sec="1" style={styles.noteSectionHead}>
                                      <span style={styles.noteSectionRule} />
                                      <span>{block.label}</span>
                                      {block.title.toLowerCase() !== block.label.toLowerCase() && (
                                        <span style={styles.noteSectionAs}>{block.title}</span>
                                      )}
                                    </div>
                                    {block.inline && <p id={matchId} style={styles.noteTextLine}>{hl(block.inline)}</p>}
                                  </div>
                                )
                                case 'field': return (
                                  <div id={matchId} key={idx} style={styles.noteFieldLine}>
                                    <strong>{hl(`${block.label}:`)}</strong>
                                    <span>{hl(block.value)}</span>
                                  </div>
                                )
                                case 'list': return (
                                  <div id={matchId} key={idx} style={styles.noteListLine}>
                                    <span style={styles.noteListMarker}>{block.marker}</span>
                                    <span>{hl(block.text)}</span>
                                  </div>
                                )
                                case 'signature': return (
                                  <p id={matchId} key={idx} style={styles.noteSignature}>{hl(block.text)}</p>
                                )
                                default: return (
                                  <p id={matchId} key={idx} style={styles.noteTextLine}>{hl(block.text)}</p>
                                )
                              }
                            })}
                          </div>
                        ) : (
                          <div style={styles.emptyPageText}>No extracted text on this page — it is a scan. Use Image or Side by side.</div>
                        )}
                      </section>
                    ))}
                  </div>

                  {/* Side by side: the scan of the page being read */}
                  {viewMode === 'split' && (
                    <div style={styles.splitImagePane}>
                      <div style={styles.splitImageHead}>
                        <button style={styles.navBtn} disabled={currentPage === 0} onClick={() => setCurrentPage(p => p - 1)}><ChevronLeft size={14} /></button>
                        <span style={styles.pageLabel}>Page {currentPage + 1} of {pages.length}</span>
                        <button style={styles.navBtn} disabled={currentPage >= pages.length - 1} onClick={() => setCurrentPage(p => p + 1)}><ChevronRight size={14} /></button>
                      </div>
                      <div style={styles.splitImageScroll}>
                        {pages[currentPage] && (
                          <img src={pageImgUrl(pages[currentPage].url)} alt={`Page ${currentPage + 1}`}
                            style={{ ...styles.pageImg, width: `${zoom * 100}%`, maxWidth: 'none' }} />
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )
            ) : loading ? (
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
                  src={pages[currentPage] ? pageImgUrl(pages[currentPage].url) : undefined}
                  alt={`Page ${currentPage + 1}`}
                  style={{ ...styles.pageImg, transform: `scale(${zoom})`, transformOrigin: 'top center', outline: isMatchPage ? `3px solid ${specialtyColor.bg}` : 'none' }}
                />
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div style={styles.footer}>
          {viewMode !== 'image' && textAvailable ? (
            <span style={styles.pageLabel}>
              {parsed.docs.length} document{parsed.docs.length !== 1 ? 's' : ''} · {parsed.sectionCount} section{parsed.sectionCount !== 1 ? 's' : ''} · {textPages.length} page{textPages.length !== 1 ? 's' : ''}
            </span>
          ) : pages.length > 1 ? (
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
          <span style={styles.keyHint}>← → page &nbsp;·&nbsp; Alt+↑↓ section &nbsp;·&nbsp; / or Ctrl+F search &nbsp;·&nbsp; Esc close</span>
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
  viewToggle: { display: 'flex', alignItems: 'center', border: '1px solid #e5e7eb', borderRadius: 7, overflow: 'hidden', background: '#fff' },
  viewToggleBtn: { border: 'none', background: '#fff', color: '#6b7280', padding: '6px 10px', cursor: 'pointer', fontSize: 12, fontWeight: 700 },
  viewToggleActive: { background: '#eef2ff', color: '#4f46e5' },
  closeBtn: { borderColor: '#fca5a5', background: '#fff5f5' },
  searchPanel: { background: '#f8fafc', borderBottom: '1px solid #e5e7eb' },
  searchBar: { display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px' },
  searchInput: { flex: 1, padding: '6px 10px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13, outline: 'none' },
  clearSearchBtn: { border: '1px solid #e5e7eb', background: '#fff', color: '#64748b', borderRadius: 6, padding: '5px 7px', cursor: 'pointer', display: 'flex', alignItems: 'center' },
  searchBtn: { padding: '6px 14px', background: '#4f46e5', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 13, fontWeight: 600 },
  searchCount: { fontSize: 12, color: '#6b7280', whiteSpace: 'nowrap' as const },
  searchNavBtn: { border: '1px solid #e5e7eb', background: '#fff', borderRadius: 5, padding: '3px 7px', cursor: 'pointer', display: 'flex', alignItems: 'center' },
  noMatch: { fontSize: 12, color: '#ef4444' },
  snippetList: { display: 'flex', gap: 8, overflowX: 'auto' as const, padding: '0 14px 10px' },
  snippetBtn: { flex: '0 0 260px', border: '1px solid #e5e7eb', background: '#fff', borderRadius: 7, padding: '7px 9px', textAlign: 'left' as const, cursor: 'pointer', boxShadow: '0 1px 2px rgba(15,23,42,0.04)' },
  snippetPage: { display: 'block', color: '#4f46e5', fontSize: 11, fontWeight: 900, marginBottom: 3 },
  snippetText: { display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' as const, overflow: 'hidden', color: '#334155', fontSize: 11.5, lineHeight: 1.35 },
  searchMark: { background: '#fde68a', color: '#78350f', borderRadius: 3, padding: '0 2px', fontWeight: 800 },
  bodyWrap: { flex: 1, display: 'flex', overflow: 'hidden' },
  thumbStrip: { width: 90, overflowY: 'auto', background: '#f9fafb', borderRight: '1px solid #e5e7eb', display: 'flex', flexDirection: 'column', gap: 6, padding: '10px 6px', flexShrink: 0 },
  thumbBtn: { borderRadius: 6, padding: 4, cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3, position: 'relative' as const, transition: 'border-color 0.15s' },
  thumbImg: { width: '100%', borderRadius: 4, display: 'block', boxShadow: '0 1px 3px rgba(0,0,0,0.1)' },
  thumbLabel: { fontSize: 10 },
  thumbMatchDot: { position: 'absolute' as const, top: 4, right: 4, width: 7, height: 7, borderRadius: '50%', background: '#f59e0b' },
  body: { flex: 1, overflowY: 'auto', padding: 20, background: '#f3f4f6' },
  // Pages inside docPane must not shrink: a flex column squeezes its children
  // to the pane's height and clips each page's text, instead of scrolling.
  // Text and side-by-side: the body holds three panes that scroll on their own,
  // so the navigator stays put while the document moves.
  bodyDoc: { flex: 1, overflow: 'hidden', background: '#f3f4f6', display: 'flex', minHeight: 0 },
  docLayout: { flex: 1, display: 'flex', minHeight: 0, minWidth: 0 },
  navigator: { width: 236, flexShrink: 0, overflowY: 'auto', background: '#fff', borderRight: '1px solid #e5e7eb', padding: '10px 8px 14px' },
  navHead: { display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', fontSize: 11, fontWeight: 800, color: '#334155', textTransform: 'uppercase' as const, letterSpacing: 0.5, padding: '2px 6px 8px' },
  navCount: { fontSize: 10, fontWeight: 600, color: '#94a3b8', textTransform: 'none' as const, letterSpacing: 0 },
  navEmpty: { fontSize: 12, color: '#94a3b8', padding: '4px 6px', lineHeight: 1.4 },
  navDoc: { width: '100%', display: 'flex', alignItems: 'baseline', gap: 6, border: 'none', background: '#f1f5f9', borderRadius: 6, padding: '6px 8px', cursor: 'pointer', textAlign: 'left' as const, marginBottom: 2, minWidth: 0 },
  navDocType: { fontSize: 11, fontWeight: 800, color: '#1e293b', whiteSpace: 'nowrap' as const },
  navDocTitle: { fontSize: 10, color: '#64748b', flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const },
  navSec: { width: '100%', display: 'flex', alignItems: 'center', gap: 6, border: 'none', borderLeft: '3px solid transparent', background: 'transparent', padding: '4px 8px 4px 10px', cursor: 'pointer', textAlign: 'left' as const, color: '#334155', borderRadius: '0 5px 5px 0', minWidth: 0 },
  navSecOn: { background: '#f5f3ff', fontWeight: 700 },
  navSecLabel: { fontSize: 12, flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const },
  navPage: { fontSize: 10, color: '#94a3b8', flexShrink: 0 },
  navKeys: { fontSize: 10, color: '#94a3b8', padding: '10px 6px 0', borderTop: '1px solid #f1f5f9', marginTop: 6, lineHeight: 1.4 },
  docPane: { flex: 1, minWidth: 0, overflowY: 'auto', padding: 16, position: 'relative' as const, display: 'flex', flexDirection: 'column', gap: 10 },
  docBand: { display: 'flex', alignItems: 'center', gap: 10, margin: '4px 0 10px', padding: '9px 12px', background: '#1e293b', color: '#fff', borderRadius: 7, fontSize: 13, fontWeight: 700 },
  docBandType: { fontSize: 10, fontWeight: 800, textTransform: 'uppercase' as const, letterSpacing: 0.6, background: 'rgba(255,255,255,0.15)', borderRadius: 4, padding: '2px 7px', flexShrink: 0 },
  noteSectionAs: { marginLeft: 'auto', fontSize: 10, fontWeight: 600, color: '#64748b', textTransform: 'none' as const, letterSpacing: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const, maxWidth: '45%' },
  noteListLine: { display: 'grid', gridTemplateColumns: '26px 1fr', gap: 4, padding: '2px 0', color: '#1f2937', wordBreak: 'break-word' as const },
  noteListMarker: { color: '#64748b', fontWeight: 700, textAlign: 'right' as const, paddingRight: 4 },
  noteSignature: { margin: '10px 0 4px', color: '#64748b', fontSize: 12, fontStyle: 'italic', borderTop: '1px dashed #e2e8f0', paddingTop: 6 },
  aidLegend: { flexShrink: 0, display: 'flex', alignItems: 'center', gap: 8, fontSize: 11, color: '#64748b', background: '#fff', border: '1px solid #e5e7eb', borderRadius: 7, padding: '6px 10px' },
  aidUncertain: { background: '#fef3c7', color: '#92400e', borderBottom: '2px solid #f59e0b', borderRadius: 2, padding: '0 1px' },
  aidLinkage: { background: '#e0f2fe', color: '#075985', borderBottom: '2px solid #0ea5e9', borderRadius: 2, padding: '0 1px' },
  splitImagePane: { width: '44%', flexShrink: 0, display: 'flex', flexDirection: 'column', borderLeft: '1px solid #e5e7eb', background: '#e5e7eb', minHeight: 0 },
  splitImageHead: { display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, padding: '6px 8px', background: '#fafafa', borderBottom: '1px solid #e5e7eb' },
  splitImageScroll: { flex: 1, overflow: 'auto', padding: 12 },
  center: { display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 200, color: '#9ca3af', gap: 12 },
  spinner: { width: 28, height: 28, border: '3px solid #e5e7eb', borderTopColor: '#4f46e5', borderRadius: '50%', animation: 'spin 0.8s linear infinite' },
  pageImg: { display: 'block', margin: '0 auto', maxWidth: '100%', boxShadow: '0 4px 12px rgba(0,0,0,0.15)', borderRadius: 4, transition: 'outline 0.2s' },
  matchBanner: { textAlign: 'center', padding: '6px', background: '#fef9c3', color: '#854d0e', fontSize: 12, fontWeight: 600, borderRadius: 4, marginBottom: 10 },
  textView: { maxWidth: 900, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 12 },
  sectionBar: { display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap' as const, background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: '9px 10px', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' },
  sectionBarLabel: { fontSize: 11, color: '#6b7280', fontWeight: 800, textTransform: 'uppercase' as const, letterSpacing: 0.5, marginRight: 2 },
  sectionChip: { display: 'flex', alignItems: 'center', gap: 6, border: '1px solid #dbeafe', background: '#eff6ff', color: '#1d4ed8', borderRadius: 6, padding: '5px 8px', fontSize: 12, fontWeight: 700, cursor: 'pointer' },
  sectionPage: { color: '#64748b', fontSize: 11, fontWeight: 700 },
  textPages: { display: 'flex', flexDirection: 'column', gap: 10 },
  textPage: { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' },
  textPageHeader: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, padding: '8px 12px', background: '#f8fafc', borderBottom: '1px solid #e5e7eb', color: '#334155', fontSize: 12, fontWeight: 800 },
  textPageBtn: { border: '1px solid #e5e7eb', background: '#fff', borderRadius: 6, color: '#4f46e5', cursor: 'pointer', padding: '4px 8px', fontSize: 11, fontWeight: 700 },
  pageText: { padding: '16px 18px 18px', color: '#111827', fontSize: 13, lineHeight: 1.55, background: '#fff' },
  noteSectionHead: { display: 'flex', alignItems: 'center', gap: 9, margin: '16px 0 8px', padding: '8px 10px', border: '1px solid #dbeafe', borderLeft: '4px solid #2563eb', borderRadius: 7, background: '#eff6ff', color: '#1e3a8a', fontSize: 12, fontWeight: 900, textTransform: 'uppercase' as const, letterSpacing: 0.4 },
  noteSectionRule: { width: 6, height: 6, borderRadius: '50%', background: '#2563eb', flexShrink: 0 },
  noteFieldLine: { display: 'grid', gridTemplateColumns: 'minmax(110px, 200px) minmax(0, 1fr)', wordBreak: 'break-word' as const, gap: 10, padding: '5px 0', borderBottom: '1px solid #f1f5f9', alignItems: 'start', color: '#1f2937' },
  noteTextLine: { margin: '5px 0', color: '#1f2937', whiteSpace: 'pre-wrap' as const, wordBreak: 'break-word' as const },
  textGap: { height: 8 },
  emptyPageText: { padding: 14, color: '#94a3b8', fontSize: 12, fontStyle: 'italic' },
  footer: { borderTop: '1px solid #e5e7eb', padding: '10px 16px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12, background: '#fafafa' },
  navBtn: { border: '1px solid #e5e7eb', background: '#fff', borderRadius: 6, padding: '5px 12px', cursor: 'pointer', display: 'flex', alignItems: 'center', transition: 'all 0.15s' },
  pageInfo: { display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 },
  pageLabel: { fontSize: 13, fontWeight: 600, color: '#374151' },
  keyHint: { fontSize: 11, color: '#c4c4c4', marginLeft: 'auto' },
  feedbackPanel: { background: '#fff5f5', borderBottom: '1px solid #fecaca', padding: '14px 18px', display: 'flex', flexDirection: 'column', gap: 10 },
  feedbackTitle: { display: 'flex', alignItems: 'center', gap: 7, fontWeight: 700, fontSize: 13, color: '#dc2626' },
  issueList: { display: 'flex', flexDirection: 'column', gap: 6 },
  issueRow: { display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' },
  issueLabel: { fontSize: 13, color: '#374151' },
  feedbackNotes: { padding: '8px 10px', border: '1px solid #fecaca', borderRadius: 6, fontSize: 13, resize: 'vertical' as const, fontFamily: 'inherit', background: '#fff' },
  feedbackActions: { display: 'flex', gap: 8 },
  submitBtn: { padding: '8px 18px', background: '#dc2626', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 700, fontSize: 13 },
  cancelFeedbackBtn: { padding: '8px 14px', background: '#fff', border: '1px solid #fecaca', borderRadius: 6, cursor: 'pointer', fontSize: 13, color: '#6b7280' },
}
