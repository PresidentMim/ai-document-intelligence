import { useEffect, useState } from 'react'
const API = import.meta.env.VITE_API_URL ||
  (window.location.port === '5173' ? 'http://localhost:8000' : '')
// Dev (vite :5173) -> backend :8000; served from the backend or a tunnel
// (same origin) -> relative paths, so one public URL serves the whole app.

export default function App() {
  const [docs, setDocs] = useState([])
  const [selected, setSelected] = useState(null)
  const [query, setQuery] = useState('')
  const [searchMode, setSearchMode] = useState('hybrid')
  const [searchResults, setSearchResults] = useState(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [edit, setEdit] = useState({})
  const [notice, setNotice] = useState('')

  const load = async () => {
    const r = await fetch(`${API}/documents?limit=50${statusFilter ? `&status=${statusFilter}` : ''}`)
    const j = await r.json(); setDocs(j.documents || [])
  }
  useEffect(() => { load(); const t = setInterval(load, 3000); return () => clearInterval(t) }, [statusFilter])

  const upload = async (e) => {
    const files = e.target.files; if (!files.length) return
    const fd = new FormData()
    for (const f of files) fd.append('files', f)
    const r = await fetch(`${API}/documents/upload`, { method: 'POST', body: fd })
    const j = await r.json()
    setNotice(r.ok ? `Queued ${j.jobs.length} file(s) — processing in background.` : `Upload failed: ${JSON.stringify(j)}`)
    load()
  }
  const search = async () => {
    if (!query.trim()) return
    const r = await fetch(`${API}/search?q=${encodeURIComponent(query)}&mode=${searchMode}`)
    setSearchResults(await r.json())
  }
  const open = async (id) => {
    const r = await fetch(`${API}/documents/${id}`); const j = await r.json()
    setSelected(j); setEdit(j.extraction || {})
  }
  const saveCorrection = async () => {
    const r = await fetch(`${API}/documents/${selected.id}/correct`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(edit) })
    const j = await r.json(); setSelected(j); setNotice('Correction saved — validation re-ran.'); load()
  }
  const reprocess = async (id) => {
    await fetch(`${API}/documents/${id}/reprocess`, { method: 'POST' })
    setNotice('Reprocessing queued.'); load()
  }
  const badge = s => ({ done: '✅', needs_review: '⚠️', failed: '❌', queued: '⏳', processing: '🔄' }[s] || s)
  return (
    <div className="wrap">
      <header><h1>📄 Document Intelligence</h1><p>Upload invoices (PDF / image / Excel / CSV) — OCR, extraction, validation, search.</p></header>
      {notice && <div className="notice" onClick={() => setNotice('')}>{notice} ✕</div>}
      <section className="card">
        <h2>Upload documents</h2>
        <input type="file" multiple accept=".pdf,.jpg,.jpeg,.png,.tif,.tiff,.xlsx,.xls,.csv" onChange={upload} />
        <p className="hint">Multiple files at once. Scanned PDFs/images go through OCR; spreadsheets are parsed sheet by sheet.</p>
      </section>
      <section className="card">
        <h2>Search</h2>
        <div className="row">
          <input value={query} onChange={e => setQuery(e.target.value)} placeholder="e.g. Acme INV-1042" onKeyDown={e => e.key === 'Enter' && search()} />
          <select value={searchMode} onChange={e => setSearchMode(e.target.value)}>
            <option value="hybrid">Hybrid</option><option value="keyword">Keyword</option><option value="semantic">Semantic</option>
          </select>
          <button onClick={search}>Search</button>
        </div>
        {searchResults && <ul>{searchResults.results.map(r => (
          <li key={r.id}><button className="link" onClick={() => open(r.id)}>{r.filename}</button> — score {r.score} {r.invoice_number ? `· ${r.invoice_number}` : ''}</li>
        ))}{searchResults.results.length === 0 && <li>No matches.</li>}</ul>}
      </section>
      <section className="card">
        <h2>Documents ({docs.length})</h2>
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
          <option value="">All statuses</option><option value="done">Done</option>
          <option value="needs_review">Needs review</option><option value="failed">Failed</option>
          <option value="processing">Processing</option><option value="queued">Queued</option>
        </select>
        <table><thead><tr><th>File</th><th>Status</th><th>Invoice</th><th>Supplier</th><th>Total</th><th></th></tr></thead>
        <tbody>{docs.map(d => <tr key={d.id}>
          <td>{d.filename}</td><td>{badge(d.status)} {d.status}</td>
          <td>{d.extraction?.invoice_number || '—'}</td><td>{d.extraction?.supplier_name || '—'}</td>
          <td>{d.extraction?.total ?? '—'} {d.extraction?.currency || ''}</td>
          <td><button onClick={() => open(d.id)}>Inspect</button> {d.status === 'failed' && <button onClick={() => reprocess(d.id)}>Reprocess</button>}</td>
        </tr>)}</tbody></table>
      </section>
      {selected && (
        <section className="card detail">
          <h2>Inspect — {selected.filename} <button onClick={() => setSelected(null)}>Close</button></h2>
          <p>Status: {badge(selected.status)} {selected.status} {selected.error && <span className="err">· {selected.error}</span>}</p>
          {selected.validation_errors?.length > 0 && <div className="errs"><h3>Validation issues</h3>
            <ul>{selected.validation_errors.map((v, i) => <li key={i}><b>{v.severity}</b> [{v.code}] {v.message}</li>)}</ul></div>}
          <h3>Extracted fields (edit to correct)</h3>
          <div className="grid">
            {['invoice_number', 'invoice_date', 'supplier_name', 'customer_name', 'subtotal', 'tax', 'total', 'currency'].map(k => (
              <label key={k}>{k}<input value={edit[k] ?? ''} onChange={e => setEdit({ ...edit, [k]: e.target.value })} />
                <small>confidence {selected.extraction?.confidence?.[k] ?? 0}</small></label>
            ))}
          </div>
          <button onClick={saveCorrection}>Save correction &amp; re-validate</button>
          <h3>Line items</h3>
          <pre>{JSON.stringify(selected.extraction?.line_items, null, 2)}</pre>
          <h3>Processing history</h3>
          <ul>{selected.history?.map((h, i) => <li key={i}>{h.step}: {h.status} {h.detail} {h.duration_ms ? `(${h.duration_ms} ms)` : ''}</li>)}</ul>
        </section>
      )}
    </div>
  )
}
