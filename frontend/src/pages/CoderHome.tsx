import { useState, useEffect, useCallback } from 'react'
import { Search, BookOpen, Clock } from 'lucide-react'
import { searchCharts, getCategories } from '../api'
import { ChartViewer } from '../components/ChartViewer'
import { useLocalStorage } from '../hooks/useLocalStorage'
import type { Chart, Specialty, Difficulty } from '../types'
import { SPECIALTIES, DIFFICULTIES } from '../types'

export function CoderHome() {
  const [coderName, setCoderName] = useLocalStorage<string>('coder_name', '')
  const [nameInput, setNameInput] = useState('')
  const [showNamePrompt, setShowNamePrompt] = useState(!coderName)

  const [query, setQuery] = useState('')
  const [specialty, setSpecialty] = useState<Specialty | ''>('')
  const [category, setCategory] = useState('')
  const [difficulty, setDifficulty] = useState<Difficulty | ''>('')
  const [categories, setCategories] = useState<string[]>([])

  const [results, setResults] = useState<Chart[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)

  const [selectedChart, setSelectedChart] = useState<Chart | null>(null)
  const [recentlyViewed, setRecentlyViewed] = useLocalStorage<Chart[]>('recently_viewed', [])

  const doSearch = useCallback(async (p = 1) => {
    setLoading(true)
    try {
      const res = await searchCharts({
        q: query || undefined,
        specialty: specialty || undefined,
        category: category || undefined,
        difficulty: difficulty || undefined,
        page: p,
        page_size: 20,
      })
      setResults(Array.isArray(res.results) ? res.results : [])
      setTotal(res.total ?? 0)
      setPage(p)
    } finally {
      setLoading(false)
    }
  }, [query, specialty, category, difficulty])

  useEffect(() => { doSearch(1) }, [specialty, category, difficulty])

  useEffect(() => {
    getCategories(specialty || undefined).then(d => setCategories(Array.isArray(d) ? d : []))
  }, [specialty])

  const handleQueryKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') doSearch(1)
  }

  const openChart = (chart: Chart) => {
    setSelectedChart(chart)
    setRecentlyViewed([chart, ...recentlyViewed.filter(c => c.id !== chart.id)].slice(0, 10))
  }

  if (showNamePrompt) {
    return (
      <div style={styles.namePromptOverlay}>
        <div style={styles.namePromptBox}>
          <BookOpen size={32} color="#4f46e5" />
          <h2 style={styles.namePromptTitle}>Welcome to Chart Viewer</h2>
          <p style={styles.namePromptSub}>Enter your name to get started. This helps track your practice session.</p>
          <input
            style={styles.nameInput}
            placeholder="Your name"
            value={nameInput}
            onChange={e => setNameInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && nameInput.trim()) { setCoderName(nameInput.trim()); setShowNamePrompt(false) } }}
            autoFocus
          />
          <button
            style={{ ...styles.primaryBtn, opacity: nameInput.trim() ? 1 : 0.5 }}
            disabled={!nameInput.trim()}
            onClick={() => { setCoderName(nameInput.trim()); setShowNamePrompt(false) }}
          >
            Continue
          </button>
          <button style={styles.skipBtn} onClick={() => setShowNamePrompt(false)}>Skip</button>
        </div>
      </div>
    )
  }

  return (
    <div style={styles.container}>
      <div style={styles.topBar}>
        <div style={styles.logo}><BookOpen size={22} color="#4f46e5" /><span style={styles.logoText}>Chart Viewer</span></div>
        {coderName && <span style={styles.coderTag}>Hi, {coderName}</span>}
      </div>

      <div style={styles.searchSection}>
        <div style={styles.searchRow}>
          <div style={styles.searchWrap}>
            <Search size={18} color="#9ca3af" style={styles.searchIcon} />
            <input
              style={styles.searchInput}
              placeholder="Search by chart number (e.g. IP048) or keyword..."
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={handleQueryKeyDown}
            />
          </div>
          <button style={styles.primaryBtn} onClick={() => doSearch(1)}>Search</button>
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
        </div>
      </div>

      {/* Recently viewed */}
      {recentlyViewed.length > 0 && results.length === 0 && !loading && (
        <div style={styles.recentSection}>
          <div style={styles.sectionLabel}><Clock size={14} /> Recently Viewed</div>
          <div style={styles.recentList}>
            {recentlyViewed.map(c => (
              <button key={c.id} style={styles.recentChip} onClick={() => openChart(c)}>
                {c.chart_number}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Results */}
      <div style={styles.resultsSection}>
        {loading ? (
          <div style={styles.center}>Searching...</div>
        ) : results.length === 0 ? (
          <div style={styles.center}>No charts found. Try a different search.</div>
        ) : (
          <>
            <div style={styles.resultsMeta}>{total} chart{total !== 1 ? 's' : ''} found</div>
            <div style={styles.grid}>
              {results.map(chart => (
                <button key={chart.id} style={styles.card} onClick={() => openChart(chart)}>
                  <div style={styles.cardNum}>{chart.chart_number}</div>
                  <div style={styles.cardSpecialty}>{chart.specialty}</div>
                  <div style={styles.cardCategory}>{chart.category}</div>
                  <div style={styles.cardFooter}>
                    <span style={{ ...styles.diffBadge, ...diffColor(chart.difficulty) }}>{chart.difficulty}</span>
                  </div>
                </button>
              ))}
            </div>
            {total > page * 20 && (
              <button style={styles.loadMoreBtn} onClick={() => doSearch(page + 1)}>Load more</button>
            )}
          </>
        )}
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

function diffColor(d: Difficulty): React.CSSProperties {
  if (d === 'Beginner') return { background: '#dcfce7', color: '#166534' }
  if (d === 'Intermediate') return { background: '#fef9c3', color: '#854d0e' }
  return { background: '#fee2e2', color: '#991b1b' }
}

const styles: Record<string, React.CSSProperties> = {
  container: { minHeight: '100vh', background: '#f9fafb', fontFamily: 'system-ui, sans-serif' },
  topBar: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 24px', background: '#fff', borderBottom: '1px solid #e5e7eb' },
  logo: { display: 'flex', alignItems: 'center', gap: 8 },
  logoText: { fontWeight: 700, fontSize: 18, color: '#111' },
  coderTag: { fontSize: 14, color: '#6b7280' },
  searchSection: { padding: '24px 24px 0', maxWidth: 900, margin: '0 auto' },
  searchRow: { display: 'flex', gap: 8, marginBottom: 12 },
  searchWrap: { flex: 1, position: 'relative' },
  searchIcon: { position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)' },
  searchInput: { width: '100%', padding: '10px 12px 10px 36px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 14, outline: 'none', boxSizing: 'border-box' },
  filterRow: { display: 'flex', gap: 8, flexWrap: 'wrap' },
  select: { padding: '8px 12px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13, background: '#fff', cursor: 'pointer' },
  filterInput: { padding: '8px 12px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 13 },
  primaryBtn: { padding: '10px 20px', background: '#4f46e5', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 600, fontSize: 14 },
  recentSection: { maxWidth: 900, margin: '16px auto 0', padding: '0 24px' },
  sectionLabel: { display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: '#6b7280', marginBottom: 8 },
  recentList: { display: 'flex', gap: 8, flexWrap: 'wrap' },
  recentChip: { padding: '4px 12px', background: '#ede9fe', color: '#4f46e5', border: 'none', borderRadius: 20, cursor: 'pointer', fontSize: 13, fontWeight: 600 },
  resultsSection: { maxWidth: 900, margin: '16px auto', padding: '0 24px' },
  resultsMeta: { fontSize: 13, color: '#6b7280', marginBottom: 12 },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 12 },
  card: { background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, padding: 16, cursor: 'pointer', textAlign: 'left', transition: 'box-shadow 0.15s', display: 'flex', flexDirection: 'column', gap: 4 },
  cardNum: { fontWeight: 700, fontSize: 16, color: '#111' },
  cardSpecialty: { fontSize: 12, color: '#6b7280' },
  cardCategory: { fontSize: 13, color: '#374151', flex: 1 },
  cardFooter: { marginTop: 8 },
  diffBadge: { fontSize: 11, padding: '2px 8px', borderRadius: 20, fontWeight: 600 },
  loadMoreBtn: { display: 'block', margin: '16px auto', padding: '8px 24px', border: '1px solid #e5e7eb', background: '#fff', borderRadius: 6, cursor: 'pointer' },
  center: { textAlign: 'center', padding: '60px 0', color: '#9ca3af', fontSize: 14 },
  namePromptOverlay: { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 999 },
  namePromptBox: { background: '#fff', borderRadius: 12, padding: 32, maxWidth: 400, width: '90%', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, textAlign: 'center' },
  namePromptTitle: { margin: 0, fontSize: 20, fontWeight: 700 },
  namePromptSub: { margin: 0, fontSize: 14, color: '#6b7280' },
  nameInput: { width: '100%', padding: '10px 12px', border: '1px solid #e5e7eb', borderRadius: 6, fontSize: 14, boxSizing: 'border-box' },
  skipBtn: { background: 'none', border: 'none', color: '#9ca3af', cursor: 'pointer', fontSize: 13 },
}
