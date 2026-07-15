import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Upload, BarChart2, FileText, Settings, BookOpen, Flag, ArrowLeft, Plus, Trash2, ExternalLink } from 'lucide-react'
import toast from 'react-hot-toast'
import { getResources, createResource, deleteResource, getUnresolvedCount } from '../api'

export function ChartManagementHome() {
  const [unresolvedCount, setUnresolvedCount] = useState(0)
  const [resources, setResources] = useState<{ id: number; title: string; description: string | null; url: string }[]>([])
  const [showResourcesPanel, setShowResourcesPanel] = useState(false)
  const [showAddResource, setShowAddResource] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [newUrl, setNewUrl] = useState('')

  const trainerName = localStorage.getItem('trainer_name') || 'Trainer'

  useEffect(() => {
    getUnresolvedCount().then(setUnresolvedCount).catch(() => {})
    getResources().then(setResources).catch(() => {})
  }, [])

  async function handleAddResource() {
    if (!newTitle.trim() || !newUrl.trim()) { toast.error('Title and URL are required'); return }
    try {
      await createResource({ title: newTitle.trim(), description: newDesc.trim() || undefined, url: newUrl.trim(), created_by: trainerName })
      toast.success('Resource added')
      setNewTitle(''); setNewDesc(''); setNewUrl(''); setShowAddResource(false)
      getResources().then(setResources).catch(() => {})
    } catch { toast.error('Failed to add resource') }
  }

  async function handleDeleteResource(id: number) {
    try {
      await deleteResource(id)
      setResources(r => r.filter(x => x.id !== id))
      toast.success('Resource removed')
    } catch { toast.error('Failed to remove resource') }
  }

  const cards = [
    { to: '/trainer/upload', icon: <Upload size={26} />, title: 'Upload Charts', desc: 'Bulk upload new charts with metadata', color: '#4f46e5', light: '#ede9fe', badge: null },
    { to: '/trainer/charts', icon: <Settings size={26} />, title: 'Manage Charts', desc: 'Edit, retire, restore and add files to charts', color: '#0891b2', light: '#cffafe', badge: null },
    { to: '/trainer/reports', icon: <FileText size={26} />, title: 'Reports', desc: 'Filter, view and export the chart library', color: '#16a34a', light: '#dcfce7', badge: null },
    { to: '/trainer/analytics', icon: <BarChart2 size={26} />, title: 'Analytics', desc: 'Most viewed, least viewed, specialty breakdown', color: '#d97706', light: '#fef3c7', badge: null },
    { to: '/trainer/feedback', icon: <Flag size={26} />, title: 'Feedback', desc: 'Review issues flagged by coders on charts', color: '#dc2626', light: '#fee2e2', badge: unresolvedCount > 0 ? unresolvedCount : null },
  ]

  return (
    <div style={s.container}>
      <div style={s.blob1} />
      <div style={s.blob2} />

      <div style={s.topBar}>
        <Link to="/trainer" style={s.backBtn}>
          <ArrowLeft size={16} /> Trainer Home
        </Link>
        <div style={s.pageTitle}>
          <FileText size={18} color="#4f46e5" />
          Chart Management
        </div>
      </div>

      <div style={s.content}>
        <div style={s.grid}>
          {cards.map(c => (
            <Link key={c.to} to={c.to} style={s.card}>
              <div style={s.cardTop}>
                <div style={{ ...s.iconWrap, background: c.light, color: c.color }}>{c.icon}</div>
                {c.badge !== null && <span style={s.cardBadge}>{c.badge}</span>}
              </div>
              <div style={s.cardTitle}>{c.title}</div>
              <div style={s.cardDesc}>{c.desc}</div>
            </Link>
          ))}

          {/* Coding Resources — toggle card (visually distinct from nav cards) */}
          <div
            style={{ ...s.card, cursor: 'pointer', border: showResourcesPanel ? '1.5px solid #059669' : '1.5px dashed #6ee7b7', background: showResourcesPanel ? 'rgba(240,253,244,0.7)' : 'rgba(240,253,244,0.35)' }}
            onClick={() => setShowResourcesPanel(p => !p)}
          >
            <div style={s.cardTop}>
              <div style={{ ...s.iconWrap, background: '#dcfce7', color: '#059669' }}><BookOpen size={26} /></div>
              <span style={{ fontSize: 11, fontWeight: 700, color: '#059669', background: '#dcfce7', padding: '3px 8px', borderRadius: 6 }}>
                {showResourcesPanel ? '▲ Hide' : '▼ Show'}
              </span>
            </div>
            <div style={s.cardTitle}>Coding Resources</div>
            <div style={s.cardDesc}>
              {resources.length > 0 ? `${resources.length} link${resources.length > 1 ? 's' : ''} — guides, PDFs, tools` : 'Links visible to all coders — guides, PDFs, tools'}
            </div>
          </div>
        </div>

        {/* Resources panel */}
        {showResourcesPanel && (
          <div style={s.resourcesPanel}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <div style={{ fontSize: 14, fontWeight: 700, color: '#374151' }}>Coding Resources</div>
              <button style={s.addBtn} onClick={() => setShowAddResource(p => !p)}>
                <Plus size={14} /> Add Resource
              </button>
            </div>
            {showAddResource && (
              <div style={s.addForm}>
                <input style={s.input} placeholder="Title *" value={newTitle} onChange={e => setNewTitle(e.target.value)} />
                <input style={s.input} placeholder="Short description (optional)" value={newDesc} onChange={e => setNewDesc(e.target.value)} />
                <input style={s.input} placeholder="URL * (e.g. https://cms.gov/...)" value={newUrl} onChange={e => setNewUrl(e.target.value)} />
                <div style={{ display: 'flex', gap: 8 }}>
                  <button style={s.saveBtn} onClick={handleAddResource}>Save</button>
                  <button style={s.cancelBtn} onClick={() => setShowAddResource(false)}>Cancel</button>
                </div>
              </div>
            )}
            {resources.length === 0 && !showAddResource && (
              <div style={{ fontSize: 13, color: '#9ca3af', textAlign: 'center' as const, padding: '20px 0' }}>No resources yet. Add links to coding guides, CMS PDFs, or tool URLs.</div>
            )}
            <div style={{ display: 'flex', flexDirection: 'column' as const, gap: 8 }}>
              {resources.map(r => (
                <div key={r.id} style={s.resourceRow}>
                  <ExternalLink size={13} style={{ color: '#4f46e5', flexShrink: 0 }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 700 }}>{r.title}</div>
                    {r.description && <div style={{ fontSize: 11, color: '#6b7280' }}>{r.description}</div>}
                    <div style={{ fontSize: 11, color: '#9ca3af', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' as const }}>{r.url}</div>
                  </div>
                  <a href={r.url} target="_blank" rel="noopener noreferrer" style={{ fontSize: 12, color: '#4f46e5', textDecoration: 'none', fontWeight: 600, flexShrink: 0 }}>Open</a>
                  <button style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#dc2626', padding: 4, display: 'flex' }} onClick={() => handleDeleteResource(r.id)}>
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

const s: Record<string, React.CSSProperties> = {
  container: { minHeight: '100vh', background: 'linear-gradient(135deg, #dbeafe 0%, #ede9fe 40%, #d1fae5 100%)', fontFamily: 'system-ui, sans-serif', position: 'relative', overflow: 'hidden' },
  blob1: { position: 'absolute', top: -80, left: -80, width: 360, height: 360, borderRadius: '50%', background: 'radial-gradient(circle, #818cf8 0%, #6366f1 60%, transparent 100%)', opacity: 0.22, filter: 'blur(60px)', pointerEvents: 'none' },
  blob2: { position: 'absolute', bottom: 40, right: -60, width: 300, height: 300, borderRadius: '50%', background: 'radial-gradient(circle, #34d399 0%, #059669 60%, transparent 100%)', opacity: 0.18, filter: 'blur(60px)', pointerEvents: 'none' },
  topBar: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 28px', background: 'rgba(255,255,255,0.75)', backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)', borderBottom: '1px solid rgba(255,255,255,0.5)', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' },
  backBtn: { display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, fontWeight: 600, color: '#6b7280', textDecoration: 'none' },
  pageTitle: { display: 'flex', alignItems: 'center', gap: 8, fontSize: 16, fontWeight: 800, color: '#111' },
  content: { maxWidth: 860, margin: '0 auto', padding: '40px 24px' },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 18 },
  card: { background: 'rgba(255,255,255,0.45)', backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)', border: '1px solid rgba(255,255,255,0.65)', borderRadius: 16, padding: '24px 20px', display: 'flex', flexDirection: 'column' as const, gap: 12, textDecoration: 'none', color: 'inherit', boxShadow: '0 8px 32px rgba(99,102,241,0.1), 0 1px 0 rgba(255,255,255,0.8) inset', transition: 'box-shadow 0.2s, transform 0.2s' },
  cardTop: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' },
  iconWrap: { width: 50, height: 50, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center' },
  cardBadge: { background: '#fee2e2', color: '#dc2626', fontSize: 12, fontWeight: 800, padding: '3px 9px', borderRadius: 20, minWidth: 24, textAlign: 'center' as const },
  cardTitle: { fontWeight: 800, fontSize: 15, color: '#111' },
  cardDesc: { fontSize: 13, color: '#6b7280', lineHeight: 1.5 },
  resourcesPanel: { background: 'rgba(255,255,255,0.6)', backdropFilter: 'blur(14px)', border: '1px solid rgba(255,255,255,0.65)', borderRadius: 14, padding: 20, marginTop: 18 },
  addBtn: { display: 'flex', alignItems: 'center', gap: 6, padding: '7px 14px', background: '#4f46e5', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontSize: 13, fontWeight: 700 },
  addForm: { background: '#f9fafb', border: '1px solid #e5e7eb', borderRadius: 10, padding: 16, marginBottom: 16, display: 'flex', flexDirection: 'column' as const, gap: 10 },
  input: { padding: '9px 12px', border: '1px solid #e5e7eb', borderRadius: 7, fontSize: 13, fontFamily: 'inherit' },
  saveBtn: { padding: '8px 18px', background: '#4f46e5', color: '#fff', border: 'none', borderRadius: 7, cursor: 'pointer', fontSize: 13, fontWeight: 700 },
  cancelBtn: { padding: '8px 14px', background: 'none', border: '1px solid #e5e7eb', borderRadius: 7, cursor: 'pointer', fontSize: 13, color: '#6b7280' },
  resourceRow: { display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px', background: '#fff', border: '1px solid #f3f4f6', borderRadius: 8 },
}
