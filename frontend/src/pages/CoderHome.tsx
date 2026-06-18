import { useState, useEffect, useCallback } from 'react'
import { Search, BookOpen, Clock, X, ArrowUpDown, Pencil, ExternalLink } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { searchCharts, getCategories, getResources } from '../api'
import { ChartViewer } from '../components/ChartViewer'
import { useLocalStorage } from '../hooks/useLocalStorage'
import type { Chart, Specialty, Difficulty } from '../types'
import { SPECIALTIES, DIFFICULTIES } from '../types'
import { SPECIALTY_COLORS, DIFFICULTY_COLORS } from '../theme'

type SortOption = 'chart_number' | 'difficulty' | 'recent'

export function CoderHome() {
  const navigate = useNavigate()
  const [coderName, setCoderName] = useLocalStorage<string>('coder_name', '')
  const [nameInput, setNameInput] = useState('')
  const [showNamePrompt, setShowNamePrompt] = useState(!coderName)

  const [query, setQuery] = useState('')
  const [specialty, setSpecialty] = useState<Specialty | ''>('')
  const [category, setCategory] = useState('')
  const [difficulty, setDifficulty] = useState<Difficulty | ''>('')
  const [sort, setSort] = useState<SortOption>('chart_number')
  const [categories, setCategories] = useState<string[]>([])
  const [hasSearched, setHasSearched] = useState(false)

  const [results, setResults] = useState<Chart[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)

  const [selectedChart, setSelectedChart] = useState<Chart | null>(null)
  const [recentlyViewed, setRecentlyViewed] = useLocalStorage<Chart[]>('recently_viewed', [])
  const [resources, setResources] = useState<{ id: number; title: string; description: string | null; url: string }[]>([])

  useEffect(() => {
    getResources().then(setResources).catch(() => {})
  }, [])

  const hasFilters = !!(specialty || category || difficulty)

  const doSearch = useCallback(async (p = 1) => {
    if (!query.trim() && !specialty && !category && !difficulty) {
      toast.error('Enter a chart number or select a filter to search')
      return
    }
    setLoading(true)
    setHasSearched(true)
    try {
      const res = await searchCharts({
        q: query || undefined,
        specialty: specialty || undefined,
        category: category || undefined,
        difficulty: difficulty || undefined,
        page: p,
        page_size: 20,
      })
      const incoming = Array.isArray(res.results) ? res.results : []
      setResults(prev => p === 1 ? incoming : [...prev, ...incoming])
      setTotal(res.total ?? 0)
      setPage(p)
    } finally {
      setLoading(false)
    }
  }, [query, specialty, category, difficulty])

  useEffect(() => {
    if (hasSearched) doSearch(1)
  }, [specialty, category, difficulty])

  useEffect(() => {
    getCategories(specialty || undefined).then(d => setCategories(Array.isArray(d) ? d : []))
  }, [specialty])

  const clearFilters = () => {
    setQuery('')
    setSpecialty('')
    setCategory('')
    setDifficulty('')
    setHasSearched(false)
    setResults([])
    setTotal(0)
  }

  const openChart = (chart: Chart) => {
    setSelectedChart(chart)
    setRecentlyViewed([chart, ...recentlyViewed.filter(c => c.id !== chart.id)].slice(0, 10))
  }

  const sortedResults = [...results].sort((a, b) => {
    if (sort === 'difficulty') {
      const order = { Beginner: 0, Intermediate: 1, Advanced: 2 }
      return order[a.difficulty] - order[b.difficulty]
    }
    if (sort === 'recent') return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    return a.chart_number.localeCompare(b.chart_number)
  })

  if (showNamePrompt) {
    return (
      <div style={styles.nameOverlay}>
        <div style={styles.nameBox}>
          <div style={styles.nameLogoWrap}><BookOpen size={36} color="#4f46e5" /></div>
          <h2 style={styles.nameTitle}>Welcome to PracticeLab</h2>
          <p style={styles.nameSub}>Enter your name to track your practice session.</p>
          <input
            style={styles.nameInput}
            placeholder="Your name"
            value={nameInput}
            onChange={e => setNameInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && nameInput.trim()) { setCoderName(nameInput.trim()); setShowNamePrompt(false) } }}
            autoFocus
          />
          <button
            style={{ ...styles.primaryBtn, opacity: nameInput.trim() ? 1 : 0.5, width: '100%' }}
            disabled={!nameInput.trim()}
            onClick={() => { setCoderName(nameInput.trim()); setShowNamePrompt(false) }}
          >
            Continue
          </button>
          <button style={styles.skipBtn} onClick={() => setShowNamePrompt(false)}>Skip for now</button>
        </div>
      </div>
    )
  }

  return (
    <div style={styles.container}>
      {/* Top bar */}
      <div style={styles.topBar}>
        <div style={styles.logo}>
          <BookOpen size={22} color="#4f46e5" />
          <span style={styles.logoText}>PracticeLab</span>
        </div>
        {coderName && (
          <div style={styles.coderChip}>
            <span style={styles.coderDot} />
            {coderName}
          </div>
        )}
        <button style={styles.selfPracticeBtn} onClick={() => navigate('/self-practice')}>
          <Pencil size={14} /> Self Practice
        </button>
      </div>

      <div style={styles.main}>
        {/* Search section */}
        <div style={styles.searchSection}>
          <div style={styles.searchRow}>
            <div style={styles.searchWrap}>
              <Search size={17} color="#9ca3af" style={styles.searchIcon} />
              <input
                style={styles.searchInput}
                placeholder="Search by chart number (e.g. IP048) or keyword..."
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') doSearch(1) }}
              />
              {query && <button style={styles.clearInputBtn} onClick={() => setQuery('')}><X size={14} /></button>}
            </div>
            <button style={styles.searchBtn} onClick={() => doSearch(1)}>Search</button>
          </div>

          <div style={styles.filterRow}>
            <select style={styles.select} value={specialty} onChange={e => setSpecialty(e.target.value as Specialty | '')}>
              <option value="">All Specialties</option>
              {SPECIALTIES.map(s => <option key={s} value={s}>{s}</option>)}
            </select>

            <input
              style={styles.filterInput}
              list="category-list"
              placeholder="Category"
              value={category}
              onChange={e => setCategory(e.target.value)}
            />
            <datalist id="category-list">
              {categories.map(c => <option key={c} value={c} />)}
            </datalist>

            <select style={styles.select} value={difficulty} onChange={e => setDifficulty(e.target.value as Difficulty | '')}>
              <option value="">All Difficulties</option>
              {DIFFICULTIES.map(d => <option key={d} value={d}>{d}</option>)}
            </select>

            {hasFilters && (
              <button style={styles.clearFiltersBtn} onClick={clearFilters}>
                <X size={13} /> Clear filters
              </button>
            )}
          </div>
        </div>

        {/* Recently viewed */}
        {recentlyViewed.length > 0 && !hasSearched && (
          <div style={styles.recentSection}>
            <div style={styles.sectionLabel}><Clock size={13} /> Recently Viewed</div>
            <div style={styles.recentList}>
              {recentlyViewed.map(c => (
                <button
                  key={c.id}
                  style={{ ...styles.recentChip, background: SPECIALTY_COLORS[c.specialty].light, color: SPECIALTY_COLORS[c.specialty].bg }}
                  onClick={() => openChart(c)}
                >
                  {c.chart_number}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Coding Resources — compact strip when search is active */}
        {resources.length > 0 && hasSearched && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14, flexWrap: 'wrap' as const }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: '#9ca3af', textTransform: 'uppercase' as const, letterSpacing: 0.5, whiteSpace: 'nowrap' as const, display: 'flex', alignItems: 'center', gap: 5 }}>
              <BookOpen size={12} color="#9ca3af" /> Resources
            </span>
            {resources.map((r, i) => {
              const STRIP_COLORS = ['#7c3aed','#2563eb','#16a34a','#d97706','#db2777','#0891b2']
              const c = STRIP_COLORS[i % STRIP_COLORS.length]
              return (
                <a key={r.id} href={r.url} target="_blank" rel="noopener noreferrer"
                  style={{ fontSize: 12, fontWeight: 600, color: c, background: '#fff', border: `1px solid ${c}22`, borderRadius: 20, padding: '3px 12px', textDecoration: 'none', whiteSpace: 'nowrap' as const, display: 'flex', alignItems: 'center', gap: 5 }}>
                  <ExternalLink size={11} /> {r.title}
                </a>
              )
            })}
          </div>
        )}

        {/* Results */}
        <div style={styles.resultsSection}>
          {!hasSearched ? (
            <div style={styles.emptyState}>
              <div style={styles.emptyTitle}>Search for a chart to get started</div>
              <div style={styles.emptySub}>Enter a chart number, or use the filters above to browse by specialty, category or difficulty.</div>
            </div>
          ) : loading ? (
            <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 10, overflow: 'hidden' }}>
              {[...Array(8)].map((_, i) => <div key={i} style={styles.skeletonRow} />)}
            </div>
          ) : results.length === 0 ? (
            <div style={styles.emptyState}>
              <Search size={44} color="#e5e7eb" />
              <div style={styles.emptyTitle}>No charts found</div>
              <div style={styles.emptySub}>Try a different search term or adjust the filters.</div>
            </div>
          ) : (
            <>
              <div style={styles.resultsMeta}>
                <span>{total} chart{total !== 1 ? 's' : ''} found</span>
                <div style={styles.sortRow}>
                  <ArrowUpDown size={13} color="#9ca3af" />
                  <select style={styles.sortSelect} value={sort} onChange={e => setSort(e.target.value as SortOption)}>
                    <option value="chart_number">Chart Number</option>
                    <option value="difficulty">Difficulty</option>
                    <option value="recent">Recently Added</option>
                  </select>
                </div>
              </div>
              <div style={styles.list}>
                {sortedResults.map(chart => {
                  const sc = SPECIALTY_COLORS[chart.specialty]
                  const dc = DIFFICULTY_COLORS[chart.difficulty]
                  return (
                    <button key={chart.id} style={styles.listRow} onClick={() => openChart(chart)}>
                      <div style={{ ...styles.listAccent, background: sc.bg }} />
                      <div style={styles.listChartNum}>
                        {chart.chart_number}
                        {chart.alias && <div style={{ fontSize: 10, fontWeight: 500, color: '#6b7280', marginTop: 1 }}>{chart.alias}</div>}
                      </div>
                      <div style={{ ...styles.listSpecBadge, background: sc.light, color: sc.bg }}>{chart.specialty}</div>
                      <div style={styles.listCategory}>{chart.category}</div>
                      <div style={{ ...styles.listDiffBadge, ...dc }}>{chart.difficulty}</div>
                      <div style={styles.listArrow}>→</div>
                    </button>
                  )
                })}
              </div>
              {page < 3 && total > page * 20 && (
                <button style={styles.loadMoreBtn} onClick={() => doSearch(page + 1)}>
                  Load more — {Math.min(total - page * 20, 20)} more of {total - page * 20} remaining
                </button>
              )}
              {(page >= 3 && total > 60) && (
                <div style={{ textAlign: 'center' as const, padding: '18px 16px', background: '#fffbeb', border: '1px solid #fcd34d', borderRadius: 10, margin: '16px 0', fontSize: 13, color: '#92400e' }}>
                  <div style={{ fontWeight: 700, marginBottom: 4 }}>Showing 60 of {total} charts</div>
                  <div style={{ color: '#b45309' }}>Add a chart number or category to narrow down your results.</div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Coding Resources — full cards when no search active */}
        {resources.length > 0 && !hasSearched && (() => {
          const PALETTE = [
            { bg: '#ede9fe', border: '#c4b5fd', icon: '#7c3aed', hover: '#ddd6fe' },
            { bg: '#dbeafe', border: '#93c5fd', icon: '#2563eb', hover: '#bfdbfe' },
            { bg: '#dcfce7', border: '#86efac', icon: '#16a34a', hover: '#bbf7d0' },
            { bg: '#fef3c7', border: '#fcd34d', icon: '#d97706', hover: '#fde68a' },
            { bg: '#fce7f3', border: '#f9a8d4', icon: '#db2777', hover: '#fbcfe8' },
            { bg: '#cffafe', border: '#67e8f9', icon: '#0891b2', hover: '#a5f3fc' },
          ]
          return (
            <div style={{ marginTop: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
                <div style={{ flex: 1, height: 1, background: '#e5e7eb' }} />
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <BookOpen size={16} color="#4f46e5" />
                  <span style={{ fontSize: 15, fontWeight: 800, color: '#111', letterSpacing: -0.3 }}>Coding Resources</span>
                </div>
                <div style={{ flex: 1, height: 1, background: '#e5e7eb' }} />
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap' as const, gap: 12 }}>
                {resources.map((r, i) => {
                  const p = PALETTE[i % PALETTE.length]
                  return (
                    <a
                      key={r.id}
                      href={r.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '12px 16px', background: p.bg, border: `1px solid ${p.border}`, borderRadius: 12, textDecoration: 'none', color: 'inherit', minWidth: 200, maxWidth: 300, flex: '1 1 200px', boxShadow: '0 1px 4px rgba(0,0,0,0.06)', transition: 'box-shadow 0.15s, background 0.15s' }}
                      onMouseEnter={e => { e.currentTarget.style.background = p.hover; e.currentTarget.style.boxShadow = '0 4px 14px rgba(0,0,0,0.1)' }}
                      onMouseLeave={e => { e.currentTarget.style.background = p.bg; e.currentTarget.style.boxShadow = '0 1px 4px rgba(0,0,0,0.06)' }}
                    >
                      <ExternalLink size={15} style={{ color: p.icon, marginTop: 2, flexShrink: 0 }} />
                      <div>
                        <div style={{ fontSize: 13, fontWeight: 700, color: '#111' }}>{r.title}</div>
                        {r.description && <div style={{ fontSize: 11, color: '#374151', marginTop: 3, lineHeight: 1.5 }}>{r.description}</div>}
                      </div>
                    </a>
                  )
                })}
              </div>
            </div>
          )
        })()}

      </div>

      {selectedChart && (
        <ChartViewer
          chart={selectedChart}
          viewerName={coderName || 'anonymous'}
          onClose={() => setSelectedChart(null)}
        />
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: { minHeight: '100vh', background: 'linear-gradient(135deg, #eff6ff 0%, #f0fdf4 50%, #fdf4ff 100%)', fontFamily: 'system-ui, sans-serif' },
  topBar: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 28px', background: 'rgba(255,255,255,0.75)', backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)', borderBottom: '1px solid rgba(255,255,255,0.5)', position: 'sticky', top: 0, zIndex: 10, boxShadow: '0 1px 3px rgba(0,0,0,0.05)' },
  logo: { display: 'flex', alignItems: 'center', gap: 8 },
  logoText: { fontWeight: 800, fontSize: 18, color: '#111', letterSpacing: -0.5 },
  coderChip: { display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#374151', background: '#f3f4f6', padding: '5px 12px', borderRadius: 20, fontWeight: 500 },
  coderDot: { width: 7, height: 7, borderRadius: '50%', background: '#22c55e' },
  selfPracticeBtn: { display: 'flex', alignItems: 'center', gap: 6, padding: '7px 14px', background: '#4f46e5', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontSize: 13, fontWeight: 700 },
  main: { maxWidth: 960, margin: '0 auto', padding: '24px 24px 60px' },
  searchSection: { background: 'rgba(255,255,255,0.62)', backdropFilter: 'blur(14px)', WebkitBackdropFilter: 'blur(14px)', border: '1px solid rgba(255,255,255,0.5)', borderRadius: 14, padding: 20, marginBottom: 20, boxShadow: '0 4px 24px rgba(0,0,0,0.07)' },
  searchRow: { display: 'flex', gap: 10, marginBottom: 14 },
  searchWrap: { flex: 1, position: 'relative', display: 'flex', alignItems: 'center' },
  searchIcon: { position: 'absolute', left: 12 },
  searchInput: { width: '100%', padding: '11px 36px 11px 38px', border: '1px solid #e5e7eb', borderRadius: 8, fontSize: 14, outline: 'none', background: '#f9fafb', transition: 'border-color 0.15s', boxSizing: 'border-box' as const },
  clearInputBtn: { position: 'absolute', right: 10, border: 'none', background: 'none', cursor: 'pointer', display: 'flex', color: '#9ca3af', padding: 4 },
  searchBtn: { padding: '11px 24px', background: '#4f46e5', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 700, fontSize: 14, whiteSpace: 'nowrap' as const },
  filterRow: { display: 'flex', gap: 8, flexWrap: 'wrap' as const, alignItems: 'center' },
  select: { padding: '8px 12px', border: '1px solid #e5e7eb', borderRadius: 7, fontSize: 13, background: '#fff', cursor: 'pointer', color: '#374151' },
  filterInput: { padding: '8px 12px', border: '1px solid #e5e7eb', borderRadius: 7, fontSize: 13, color: '#374151' },
  clearFiltersBtn: { display: 'flex', alignItems: 'center', gap: 5, padding: '7px 12px', border: '1px solid #fca5a5', background: '#fff5f5', color: '#dc2626', borderRadius: 7, cursor: 'pointer', fontSize: 12, fontWeight: 600 },
  recentSection: { marginBottom: 20 },
  sectionLabel: { display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#9ca3af', marginBottom: 8, fontWeight: 600, textTransform: 'uppercase' as const, letterSpacing: 0.5 },
  recentList: { display: 'flex', gap: 8, flexWrap: 'wrap' as const },
  recentChip: { padding: '5px 14px', border: 'none', borderRadius: 20, cursor: 'pointer', fontSize: 13, fontWeight: 700 },
  resultsSection: {},
  resultsMeta: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 13, color: '#6b7280', marginBottom: 14 },
  sortRow: { display: 'flex', alignItems: 'center', gap: 6 },
  sortSelect: { padding: '5px 10px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 12, background: '#fff', cursor: 'pointer' },
  list: { display: 'flex', flexDirection: 'column', gap: 0, background: 'rgba(255,255,255,0.62)', backdropFilter: 'blur(14px)', WebkitBackdropFilter: 'blur(14px)', border: '1px solid rgba(255,255,255,0.5)', borderRadius: 12, overflow: 'hidden', boxShadow: '0 4px 24px rgba(0,0,0,0.07)' },
  listRow: { display: 'flex', alignItems: 'center', gap: 14, padding: '12px 16px', background: 'transparent', border: 'none', borderBottom: '1px solid rgba(243,244,246,0.8)', cursor: 'pointer', textAlign: 'left', transition: 'background 0.1s', width: '100%' },
  listAccent: { width: 4, height: 36, borderRadius: 2, flexShrink: 0 },
  listChartNum: { fontWeight: 800, fontSize: 15, color: '#111', minWidth: 72, letterSpacing: -0.3 },
  listSpecBadge: { fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 20, textTransform: 'uppercase' as const, letterSpacing: 0.4, whiteSpace: 'nowrap' as const, minWidth: 80, textAlign: 'center' as const },
  listCategory: { fontSize: 13, color: '#374151', flex: 1 },
  listDiffBadge: { fontSize: 11, padding: '2px 9px', borderRadius: 20, fontWeight: 600, whiteSpace: 'nowrap' as const },
  listArrow: { fontSize: 14, color: '#d1d5db', marginLeft: 4 },
  diffBadge: { fontSize: 11, padding: '2px 9px', borderRadius: 20, fontWeight: 600 },
  loadMoreBtn: { display: 'block', margin: '20px auto 0', padding: '10px 28px', border: '1px solid #e5e7eb', background: '#fff', borderRadius: 8, cursor: 'pointer', fontSize: 13, fontWeight: 600, color: '#374151' },
  emptyState: { textAlign: 'center', padding: '70px 0', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 },
  emptyTitle: { fontSize: 16, fontWeight: 700, color: '#6b7280' },
  emptySub: { fontSize: 13, color: '#9ca3af', maxWidth: 380, lineHeight: 1.7 },
  skeletonRow: { height: 48, borderBottom: '1px solid #f3f4f6', background: 'linear-gradient(90deg, #f9fafb 25%, #f3f4f6 50%, #f9fafb 75%)', backgroundSize: '200% 100%', animation: 'shimmer 1.4s infinite' },
  nameOverlay: { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 999, backdropFilter: 'blur(4px)' },
  nameBox: { background: '#fff', borderRadius: 14, padding: '36px 32px', maxWidth: 400, width: '90%', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14, textAlign: 'center', boxShadow: '0 20px 40px rgba(0,0,0,0.2)' },
  nameLogoWrap: { background: '#ede9fe', borderRadius: '50%', padding: 14, display: 'flex' },
  nameTitle: { margin: 0, fontSize: 22, fontWeight: 800, color: '#111' },
  nameSub: { margin: 0, fontSize: 14, color: '#6b7280', lineHeight: 1.6 },
  nameInput: { width: '100%', padding: '11px 14px', border: '1px solid #e5e7eb', borderRadius: 8, fontSize: 14, boxSizing: 'border-box' as const, outline: 'none' },
  primaryBtn: { padding: '11px 20px', background: '#4f46e5', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 700, fontSize: 14 },
  skipBtn: { background: 'none', border: 'none', color: '#9ca3af', cursor: 'pointer', fontSize: 13 },
}
