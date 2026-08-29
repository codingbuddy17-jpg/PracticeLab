import { useState, useEffect, useCallback, useRef } from 'react'
import { X, ChevronLeft, ChevronRight, ZoomIn, ZoomOut, Copy, Check, Search, ChevronUp, ChevronDown, Flag } from 'lucide-react'
import toast from 'react-hot-toast'
import { getChartPages, getChartText, searchInChart, submitFeedback } from '../api'
import type { Chart } from '../types'
import { SPECIALTY_COLORS, DIFFICULTY_COLORS } from '../theme'

interface Props {
  chart: Chart
  viewerName?: string
  onClose: () => void
}

const API_BASE = import.meta.env.VITE_API_URL || '/api'
function pageImgUrl(path: string) {
  return path.startsWith('http') ? path : `${API_BASE}${path}`
}

const SECTION_PATTERNS: { label: string; pattern: RegExp }[] = [
  { label: 'Discharge Summary', pattern: /\b(discharge summary|hospital course|discharge diagnosis|discharge diagnoses)\b/i },
  { label: 'History & Physical', pattern: /\b(history and physical|history & physical|h&p|chief complaint|history of present illness|hpi)\b/i },
  { label: 'Operative Note', pattern: /\b(operative report|operative note|procedure performed|preoperative diagnosis|postoperative diagnosis)\b/i },
  { label: 'Procedure Note', pattern: /\b(procedure note|procedures performed|indication for procedure|description of procedure)\b/i },
  { label: 'Pathology', pattern: /\b(pathology|specimen|final diagnosis|microscopic diagnosis)\b/i },
  { label: 'Radiology', pattern: /\b(radiology|impression:|ct |mri |x-ray|ultrasound|portable chest)\b/i },
  { label: 'Labs', pattern: /\b(laboratory|lab results|wbc|hemoglobin|creatinine|sodium|potassium|bun)\b/i },
  { label: 'ED Course', pattern: /\b(ed course|emergency department course|emergency room course|medical decision making)\b/i },
  { label: 'Assessment & Plan', pattern: /\b(assessment and plan|assessment\/plan|assessment & plan|plan:)\b/i },
  { label: 'Medication List', pattern: /\b(medications|home medications|current medications|medication list)\b/i },
  { label: 'Consult Note', pattern: /\b(consultation|consult note|consultant|reason for consult)\b/i },
]

function sectionBreakers(pages: { page: number; text: string; has_text: boolean }[]) {
  const seen = new Map<string, number>()
  for (const page of pages) {
    if (!page.has_text) continue
    for (const section of SECTION_PATTERNS) {
      if (!seen.has(section.label) && section.pattern.test(page.text)) {
        seen.set(section.label, page.page)
      }
    }
  }
  return [...seen.entries()].map(([label, page]) => ({ label, page }))
}

function sectionLabelForLine(line: string) {
  const compact = line.trim().replace(/\s+/g, ' ')
  const withoutColon = compact.replace(/:$/, '')
  for (const section of SECTION_PATTERNS) {
    if (section.pattern.test(compact)) return section.label
  }
  if (/^[A-Z0-9 /&().,'-]{4,72}:?$/.test(compact) && /[A-Z]/.test(compact)) {
    return withoutColon
  }
  return ''
}

function textBlocks(text: string) {
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  const blocks: Array<
    | { kind: 'heading'; text: string }
    | { kind: 'field'; label: string; value: string }
    | { kind: 'text'; text: string }
    | { kind: 'gap' }
  > = []
  let previousGap = false

  for (const raw of lines) {
    const line = raw.trim()
    if (!line) {
      if (!previousGap && blocks.length) blocks.push({ kind: 'gap' })
      previousGap = true
      continue
    }
    previousGap = false

    const heading = sectionLabelForLine(line)
    if (heading && line.length <= 90) {
      blocks.push({ kind: 'heading', text: heading })
      continue
    }

    const field = line.match(/^([A-Za-z][A-Za-z0-9 /&().,'-]{2,42}):\s*(.+)$/)
    if (field) {
      blocks.push({ kind: 'field', label: field[1].trim(), value: field[2].trim() })
      continue
    }

    blocks.push({ kind: 'text', text: line.replace(/\s{3,}/g, '  ') })
  }

  return blocks
}

export function ChartViewer({ chart, viewerName = 'anonymous', onClose }: Props) {
  const [pages, setPages] = useState<{ page: number; url: string }[]>([])
  const [textPages, setTextPages] = useState<{ page: number; text: string; has_text: boolean }[]>([])
  const [textLoaded, setTextLoaded] = useState(false)
  const [textLoading, setTextLoading] = useState(false)
  const [textAvailable, setTextAvailable] = useState(false)
  const [viewMode, setViewMode] = useState<'image' | 'text'>('image')
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
  const searchInputRef = useRef<HTMLInputElement>(null)

  const specialtyColor = SPECIALTY_COLORS[chart.specialty]
  const diffColor = DIFFICULTY_COLORS[chart.difficulty]

  useEffect(() => {
    setLoading(true)
    setViewMode('image')
    setTextPages([])
    setTextLoaded(false)
    setTextAvailable(false)
    getChartPages(chart.id, viewerName)
      .then(d => { setPages(d.pages); setLoading(false) })
      .catch(() => setLoading(false))
  }, [chart.id, viewerName])

  useEffect(() => {
    if (viewMode !== 'text' || textLoaded || textLoading) return
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
    if (!searchQuery.trim()) { setSearchResults([]); setSearchSnippets([]); return }
    setSearching(true)
    try {
      const res = await searchInChart(chart.id, searchQuery.trim())
      setSearchResults(res.matching_pages)
      setSearchSnippets((res.snippets || []).filter(s => s.snippet))
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
  const sections = sectionBreakers(textPages)

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
            <div style={styles.viewToggle} aria-label="Chart view mode">
              <button
                style={{ ...styles.viewToggleBtn, ...(viewMode === 'image' ? styles.viewToggleActive : {}) }}
                onClick={() => setViewMode('image')}
              >
                Image
              </button>
              <button
                style={{ ...styles.viewToggleBtn, ...(viewMode === 'text' ? styles.viewToggleActive : {}) }}
                onClick={() => setViewMode('text')}
              >
                Text
              </button>
            </div>
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
                      setViewMode('text')
                    }}
                  >
                    <span style={styles.snippetPage}>Page {item.page + 1}</span>
                    <span style={styles.snippetText}>{item.snippet}</span>
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
          <div style={styles.body}>
            {viewMode === 'text' ? (
              textLoading ? (
                <div style={styles.center}>
                  <div style={styles.spinner} />
                  <span>Loading chart text...</span>
                </div>
              ) : !textAvailable ? (
                <div style={styles.center}>Text is not available for this chart.</div>
              ) : (
                <div style={styles.textView}>
                  {sections.length > 0 && (
                    <div style={styles.sectionBar}>
                      <span style={styles.sectionBarLabel}>Sections</span>
                      {sections.map(section => (
                        <button
                          key={section.label}
                          style={styles.sectionChip}
                          onClick={() => {
                            setCurrentPage(section.page)
                            document.getElementById(`chart-text-page-${section.page}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                          }}
                        >
                          {section.label}
                          <span style={styles.sectionPage}>p{section.page + 1}</span>
                        </button>
                      ))}
                    </div>
                  )}
                  <div style={styles.textPages}>
                    {textPages.map(page => (
                      <section
                        id={`chart-text-page-${page.page}`}
                        key={page.page}
                        style={{
                          ...styles.textPage,
                          borderColor: page.page === currentPage ? specialtyColor.bg : '#e5e7eb',
                        }}
                      >
                        <div style={styles.textPageHeader}>
                          <span>Page {page.page + 1}</span>
                          <button style={styles.textPageBtn} onClick={() => { setCurrentPage(page.page); setViewMode('image') }}>
                            View Image
                          </button>
                        </div>
                        {page.has_text ? (
                          <div style={styles.pageText}>
                            {textBlocks(page.text).map((block, idx) => {
                              if (block.kind === 'gap') return <div key={idx} style={styles.textGap} />
                              if (block.kind === 'heading') {
                                return (
                                  <div key={idx} style={styles.noteSectionHead}>
                                    <span style={styles.noteSectionRule} />
                                    <span>{block.text}</span>
                                  </div>
                                )
                              }
                              if (block.kind === 'field') {
                                return (
                                  <div key={idx} style={styles.noteFieldLine}>
                                    <strong>{block.label}:</strong>
                                    <span>{block.value}</span>
                                  </div>
                                )
                              }
                              return <p key={idx} style={styles.noteTextLine}>{block.text}</p>
                            })}
                          </div>
                        ) : (
                          <div style={styles.emptyPageText}>No extracted text on this page.</div>
                        )}
                      </section>
                    ))}
                  </div>
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
          {viewMode === 'text' && textAvailable ? (
            <span style={styles.pageLabel}>{textPages.filter(p => p.has_text).length} text page{textPages.filter(p => p.has_text).length !== 1 ? 's' : ''}</span>
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
  viewToggle: { display: 'flex', alignItems: 'center', border: '1px solid #e5e7eb', borderRadius: 7, overflow: 'hidden', background: '#fff' },
  viewToggleBtn: { border: 'none', background: '#fff', color: '#6b7280', padding: '6px 10px', cursor: 'pointer', fontSize: 12, fontWeight: 700 },
  viewToggleActive: { background: '#eef2ff', color: '#4f46e5' },
  closeBtn: { borderColor: '#fca5a5', background: '#fff5f5' },
  searchPanel: { background: '#f8fafc', borderBottom: '1px solid #e5e7eb' },
  searchBar: { display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px' },
  searchInput: { flex: 1, padding: '6px 10px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13, outline: 'none' },
  searchBtn: { padding: '6px 14px', background: '#4f46e5', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 13, fontWeight: 600 },
  searchCount: { fontSize: 12, color: '#6b7280', whiteSpace: 'nowrap' as const },
  searchNavBtn: { border: '1px solid #e5e7eb', background: '#fff', borderRadius: 5, padding: '3px 7px', cursor: 'pointer', display: 'flex', alignItems: 'center' },
  noMatch: { fontSize: 12, color: '#ef4444' },
  snippetList: { display: 'flex', gap: 8, overflowX: 'auto' as const, padding: '0 14px 10px' },
  snippetBtn: { flex: '0 0 260px', border: '1px solid #e5e7eb', background: '#fff', borderRadius: 7, padding: '7px 9px', textAlign: 'left' as const, cursor: 'pointer', boxShadow: '0 1px 2px rgba(15,23,42,0.04)' },
  snippetPage: { display: 'block', color: '#4f46e5', fontSize: 11, fontWeight: 900, marginBottom: 3 },
  snippetText: { display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' as const, overflow: 'hidden', color: '#334155', fontSize: 11.5, lineHeight: 1.35 },
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
  noteFieldLine: { display: 'grid', gridTemplateColumns: 'minmax(130px, 220px) 1fr', gap: 10, padding: '5px 0', borderBottom: '1px solid #f1f5f9', alignItems: 'start', color: '#1f2937' },
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
