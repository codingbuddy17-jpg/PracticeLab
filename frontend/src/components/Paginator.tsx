/**
 * Reusable pagination bar + hook.
 * Usage:
 *   const { page, setPage, pageData, totalPages, Paginator } = usePagination(items, 20)
 *   pageData.map(...) — renders only the current page slice
 *   <Paginator /> — renders the page control bar
 */
import React, { useState, useMemo } from 'react'

export function usePagination<T>(items: T[], pageSize = 20) {
  const [page, setPage] = useState(1)

  const totalPages = Math.max(1, Math.ceil(items.length / pageSize))
  // clamp page if data shrinks (e.g. after a filter change)
  const safePage = Math.min(page, totalPages)

  const pageData = useMemo(
    () => items.slice((safePage - 1) * pageSize, safePage * pageSize),
    [items, safePage, pageSize],
  )

  function Paginator() {
    if (totalPages <= 1) return null
    const start = (safePage - 1) * pageSize + 1
    const end   = Math.min(safePage * pageSize, items.length)

    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 12, fontSize: 12, color: '#6b7280' }}>
        <span>{start}–{end} of {items.length}</span>
        <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
          <PageBtn label="«" disabled={safePage === 1} onClick={() => setPage(1)} />
          <PageBtn label="‹" disabled={safePage === 1} onClick={() => setPage(p => Math.max(1, p - 1))} />
          {pageNumbers(safePage, totalPages).map((n, i) =>
            n === '…'
              ? <span key={`e${i}`} style={{ padding: '3px 4px', color: '#9ca3af' }}>…</span>
              : <PageBtn key={n} label={String(n)} active={n === safePage} onClick={() => setPage(n as number)} />
          )}
          <PageBtn label="›" disabled={safePage === totalPages} onClick={() => setPage(p => Math.min(totalPages, p + 1))} />
          <PageBtn label="»" disabled={safePage === totalPages} onClick={() => setPage(totalPages)} />
        </div>
      </div>
    )
  }

  return { page: safePage, setPage, pageData, totalPages, Paginator }
}

function PageBtn({ label, onClick, disabled, active }: { label: string; onClick: () => void; disabled?: boolean; active?: boolean }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: '3px 9px', border: '1px solid', borderRadius: 6,
        fontSize: 12, cursor: disabled ? 'default' : 'pointer', fontWeight: active ? 700 : 400,
        background: active ? '#7c3aed' : disabled ? '#f9fafb' : '#fff',
        color: active ? '#fff' : disabled ? '#d1d5db' : '#374151',
        borderColor: active ? '#7c3aed' : '#e5e7eb',
      }}
    >
      {label}
    </button>
  )
}

function pageNumbers(current: number, total: number): (number | '…')[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1)
  const pages: (number | '…')[] = [1]
  if (current > 3) pages.push('…')
  for (let i = Math.max(2, current - 1); i <= Math.min(total - 1, current + 1); i++) pages.push(i)
  if (current < total - 2) pages.push('…')
  pages.push(total)
  return pages
}
