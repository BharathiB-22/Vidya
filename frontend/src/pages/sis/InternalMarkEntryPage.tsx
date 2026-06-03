import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Save, Download, Upload, AlertCircle, Info } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { sisApi, MarkEntryOut } from '@/lib/api/sis'

interface EntryRow {
  entry_id:       string | null
  student_id:     string
  student_name:   string | null
  usn:            string | null
  marks_obtained: string
  remarks:        string
  is_first:       boolean
}

export default function InternalMarkEntryPage() {
  const { componentId } = useParams<{ componentId: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const [rows, setRows]               = useState<EntryRow[]>([])
  const [editReason, setEditReason]   = useState('')
  const [showReason, setShowReason]   = useState(false)
  const [showImport, setShowImport]   = useState(false)
  const [importFile, setImportFile]   = useState<File | null>(null)
  const [importPreview, setImportPreview] = useState<any>(null)
  const [importReason, setImportReason]   = useState('')

  const { data: component, isLoading: loadingComp } = useQuery({
    queryKey: ['marks-component', componentId],
    queryFn:  () => sisApi.getMarksComponent(componentId!),
    enabled:  !!componentId,
  })
  const { data: entries = [], isLoading: loadingEntries } = useQuery({
    queryKey: ['marks-entries', componentId],
    queryFn:  () => sisApi.getMarksEntries(componentId!),
    enabled:  !!componentId,
  })

  useEffect(() => {
    if (!entries.length) return
    setRows(entries.map((e: MarkEntryOut) => ({
      entry_id:       e.id,
      student_id:     e.student_id,
      student_name:   e.student_name,
      usn:            e.usn,
      marks_obtained: e.marks_obtained !== null ? String(e.marks_obtained) : '',
      remarks:        e.remarks ?? '',
      is_first:       e.marked_by === null,
    })))
  }, [entries])

  const bulkMutation = useMutation({
    mutationFn: (payload: { entries: any[]; edit_reason?: string }) =>
      sisApi.bulkEnterMarks(componentId!, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['marks-entries', componentId] })
      qc.invalidateQueries({ queryKey: ['marks-component', componentId] })
      setEditReason(''); setShowReason(false)
    },
  })

  const previewMutation = useMutation({
    mutationFn: (file: File) => sisApi.previewMarksImport(componentId!, file),
    onSuccess:  data => setImportPreview(data),
  })
  const commitMutation = useMutation({
    mutationFn: () => sisApi.commitMarksImport(componentId!, importFile!, importReason || undefined),
    onSuccess:  () => {
      qc.invalidateQueries({ queryKey: ['marks-entries', componentId] })
      qc.invalidateQueries({ queryKey: ['marks-component', componentId] })
      setShowImport(false); setImportPreview(null); setImportFile(null)
    },
  })

  function updateRow(idx: number, field: 'marks_obtained' | 'remarks', value: string) {
    setRows(prev => prev.map((r, i) => i === idx ? { ...r, [field]: value } : r))
  }

  const isLocked    = component?.status === 'LOCKED'
  const isPublished = component?.status === 'PUBLISHED'
  const hasEdits    = rows.some(r => !r.is_first)
  const maxMarks    = component ? Number(component.max_marks) : Infinity
  const invalid     = rows.filter(r => r.marks_obtained !== '' && parseFloat(r.marks_obtained) > maxMarks)

  function handleSave() {
    if (isPublished && hasEdits) { setShowReason(true); return }
    doSave()
  }
  function doSave(reason?: string) {
    bulkMutation.mutate({
      entries: rows.map(r => ({
        student_id:     r.student_id,
        marks_obtained: r.marks_obtained !== '' ? parseFloat(r.marks_obtained) : null,
        remarks:        r.remarks || undefined,
      })),
      edit_reason: reason || editReason || undefined,
    })
  }

  if (loadingComp || loadingEntries) return <div className="p-6 text-muted-foreground">Loading…</div>
  if (!component) return <div className="p-6">Component not found.</div>

  return (
    <PageShell>
      {/* Header bar */}
      <div className="flex items-center gap-3 mb-4">
        <Button variant="ghost" size="sm" onClick={() => navigate('/sis/marks/setup')}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="flex-1">
          <h1 className="text-xl font-bold">{component.name}</h1>
          <p className="text-sm text-muted-foreground">
            {component.course_code} — {component.section_name} · Max: {component.max_marks}
          </p>
        </div>
        <Badge variant="outline" className={`text-xs ${
          component.status === 'LOCKED'    ? 'bg-gray-100 text-gray-700' :
          component.status === 'PUBLISHED' ? 'bg-green-100 text-green-800' :
          'bg-yellow-100 text-yellow-800'
        }`}>{component.status}</Badge>
      </div>

      {/* Notices */}
      {isLocked && (
        <div className="flex gap-2 items-start rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800 mb-3">
          <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
          Marks are locked. Contact Dean or Admin to reopen.
        </div>
      )}
      {isPublished && (
        <div className="flex gap-2 items-start rounded-md border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800 mb-3">
          <Info className="h-4 w-4 mt-0.5 shrink-0" />
          Component is published and visible to students. Edits require a reason.
        </div>
      )}
      {invalid.length > 0 && (
        <div className="flex gap-2 items-start rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 mb-3">
          <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
          {invalid.length} row(s) exceed max marks ({maxMarks}).
        </div>
      )}

      {/* Toolbar */}
      <div className="flex gap-2 justify-end mb-4">
        <Button size="sm" variant="outline" onClick={() => sisApi.downloadMarksTemplate(componentId!)}>
          <Download className="h-4 w-4 mr-1" />Template
        </Button>
        <Button size="sm" variant="outline" onClick={() => setShowImport(true)} disabled={isLocked}>
          <Upload className="h-4 w-4 mr-1" />Import
        </Button>
        <Button size="sm" onClick={handleSave} disabled={isLocked || bulkMutation.isPending || invalid.length > 0}>
          <Save className="h-4 w-4 mr-1" />{bulkMutation.isPending ? 'Saving…' : 'Save All'}
        </Button>
      </div>

      {/* Table */}
      <div className="rounded-md border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-muted/40 text-xs uppercase text-muted-foreground">
            <tr>
              <th className="px-4 py-2 text-left">USN</th>
              <th className="px-4 py-2 text-left">Name</th>
              <th className="px-4 py-2 text-center w-36">Marks (/{maxMarks})</th>
              <th className="px-4 py-2 text-left">Remarks</th>
              <th className="px-4 py-2 text-center w-20">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {rows.map((row, idx) => {
              const val = row.marks_obtained !== '' ? parseFloat(row.marks_obtained) : null
              const over = val !== null && val > maxMarks
              return (
                <tr key={row.student_id} className="hover:bg-muted/20">
                  <td className="px-4 py-2 font-mono text-xs">{row.usn ?? '—'}</td>
                  <td className="px-4 py-2">{row.student_name ?? row.student_id.slice(0, 8)}</td>
                  <td className="px-4 py-2">
                    <Input
                      type="number" min={0} max={maxMarks} step={0.01}
                      className={`h-7 text-center ${over ? 'border-red-400 bg-red-50' : ''}`}
                      value={row.marks_obtained}
                      onChange={e => updateRow(idx, 'marks_obtained', e.target.value)}
                      disabled={isLocked} placeholder="—"
                    />
                  </td>
                  <td className="px-4 py-2">
                    <Input className="h-7" value={row.remarks}
                      onChange={e => updateRow(idx, 'remarks', e.target.value)}
                      disabled={isLocked} placeholder="optional" />
                  </td>
                  <td className="px-4 py-2 text-center">
                    {row.is_first
                      ? <span className="text-muted-foreground text-xs">—</span>
                      : <span className="text-xs px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200">Saved</span>
                    }
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Edit reason dialog */}
      <Dialog open={showReason} onOpenChange={setShowReason}>
        <DialogContent>
          <DialogHeader><DialogTitle>Edit Reason Required</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground">Marks are published. Provide a reason for editing.</p>
          <Textarea rows={3} value={editReason} onChange={e => setEditReason(e.target.value)}
            placeholder="e.g. Corrected data entry error" />
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowReason(false)}>Cancel</Button>
            <Button onClick={() => doSave(editReason)} disabled={!editReason.trim() || bulkMutation.isPending}>
              {bulkMutation.isPending ? 'Saving…' : 'Save with Reason'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Import dialog */}
      <Dialog open={showImport} onOpenChange={v => { if (!v) { setShowImport(false); setImportPreview(null) } }}>
        <DialogContent className="max-w-2xl">
          <DialogHeader><DialogTitle>Import Marks from Excel</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="flex gap-2">
              <Input type="file" accept=".xlsx" onChange={e => { setImportFile(e.target.files?.[0] ?? null); setImportPreview(null) }} />
              <Button variant="outline" disabled={!importFile || previewMutation.isPending}
                onClick={() => importFile && previewMutation.mutate(importFile)}>
                {previewMutation.isPending ? 'Parsing…' : 'Preview'}
              </Button>
            </div>
            {importPreview && (
              <>
                <div className="flex gap-4 text-sm">
                  <span>Total: <strong>{importPreview.total_rows}</strong></span>
                  <span className="text-green-700">Valid: <strong>{importPreview.valid_rows}</strong></span>
                  {importPreview.invalid_rows > 0 && <span className="text-red-700">Invalid: <strong>{importPreview.invalid_rows}</strong></span>}
                </div>
                <div className="max-h-48 overflow-auto rounded border text-xs">
                  <table className="w-full">
                    <thead className="bg-muted/40 sticky top-0">
                      <tr>
                        <th className="px-3 py-1 text-left">#</th>
                        <th className="px-3 py-1 text-left">Student</th>
                        <th className="px-3 py-1 text-right">Marks</th>
                        <th className="px-3 py-1 text-left">Result</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {importPreview.rows.map((r: any) => (
                        <tr key={r.row_number} className={r.is_valid ? '' : 'bg-red-50'}>
                          <td className="px-3 py-1">{r.row_number}</td>
                          <td className="px-3 py-1">{r.student_name ?? r.email}</td>
                          <td className="px-3 py-1 text-right">{r.marks_obtained ?? '—'}</td>
                          <td className="px-3 py-1">
                            {r.is_valid ? <span className="text-green-700">✓</span> : <span className="text-red-700">{r.errors.join('; ')}</span>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {isPublished && (
                  <>
                    <p className="text-xs font-medium">Edit Reason (required — published component)</p>
                    <Textarea rows={2} value={importReason} onChange={e => setImportReason(e.target.value)}
                      placeholder="Reason for importing marks" />
                  </>
                )}
              </>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setShowImport(false); setImportPreview(null) }}>Cancel</Button>
            {importPreview?.valid_rows > 0 && (
              <Button onClick={() => commitMutation.mutate()}
                disabled={commitMutation.isPending || (isPublished && !importReason.trim())}>
                {commitMutation.isPending ? 'Importing…' : `Import ${importPreview.valid_rows} rows`}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageShell>
  )
}
