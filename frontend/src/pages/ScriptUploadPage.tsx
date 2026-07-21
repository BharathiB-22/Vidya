// M09 Paper Administration — Upload scanned answer script
// Board/Admin uploads PDF/image; exam paper and student chosen from dropdowns.
import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import {
  AlertTriangle, ChevronLeft, CheckCircle2, FileText, Loader2, Upload, X,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { uploadScript } from '@/lib/api/scripts'
import { listAllExamPapers } from '@/lib/api/exam'
import { usersApi } from '@/lib/api/users'
import { generateUploadUrl, createAsset } from '@/lib/api/storage'
import type { ScriptIngestPayload, ScriptIngestResponse } from '@/types/script'

const ALLOWED_MIME = ['application/pdf', 'image/jpeg', 'image/png'] as const
const MAX_SIZE_MB = 20

export default function ScriptUploadPage() {
  const navigate = useNavigate()

  const [examPaperId,    setExamPaperId]    = useState('')
  const [studentUserId,  setStudentUserId]  = useState('')
  const [studentSearch,  setStudentSearch]  = useState('')
  const [studentRollRef, setStudentRollRef] = useState('')
  const [file,           setFile]           = useState<File | null>(null)
  const [uploadStep,     setUploadStep]     = useState<string | null>(null)
  const [error,          setError]          = useState<string | null>(null)
  const [result,         setResult]         = useState<ScriptIngestResponse | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Released exam papers for dropdown
  const { data: papersData } = useQuery({
    queryKey: ['exam-papers-released'],
    queryFn:  () => listAllExamPapers({ status: 'RELEASED', limit: 200 }),
  })

  // All users — filter to STUDENT client-side for dropdown
  const { data: allUsers } = useQuery({
    queryKey: ['users-all'],
    queryFn:  () => usersApi.list(),
  })
  const students = (allUsers ?? []).filter(u => u.role === 'STUDENT')
  const filteredStudents = studentSearch.trim()
    ? students.filter(s =>
        s.full_name.toLowerCase().includes(studentSearch.toLowerCase()) ||
        s.email.toLowerCase().includes(studentSearch.toLowerCase()) ||
        (s.identifier ?? '').toLowerCase().includes(studentSearch.toLowerCase())
      )
    : students

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] ?? null
    if (!f) return
    if (!(ALLOWED_MIME as readonly string[]).includes(f.type)) {
      setError('Only PDF, JPEG, and PNG files are allowed.')
      return
    }
    if (f.size > MAX_SIZE_MB * 1024 * 1024) {
      setError(`File must be under ${MAX_SIZE_MB} MB.`)
      return
    }
    setError(null)
    setFile(f)
  }

  const submitMut = useMutation({
    mutationFn: async () => {
      let objectKey: string | undefined

      if (file) {
        // 1 — get presigned PUT URL (entity_id = exam_paper_id groups all scripts for that paper)
        setUploadStep('Preparing upload…')
        const { object_key, presigned_url } = await generateUploadUrl({
          entity_type:       'scanned_script',
          entity_id:         examPaperId,
          original_filename: file.name,
          content_type:      file.type,
          size_bytes:        file.size,
        })
        objectKey = object_key

        // 2 — PUT file directly to MinIO / S3 via presigned URL
        setUploadStep('Uploading file…')
        const putResp = await fetch(presigned_url, {
          method:  'PUT',
          headers: { 'Content-Type': file.type },
          body:    file,
        })
        if (!putResp.ok) throw new Error(`File upload to storage failed (HTTP ${putResp.status}).`)

        // 3 — persist asset metadata
        setUploadStep('Saving file record…')
        await createAsset({
          object_key,
          entity_type:       'scanned_script',
          entity_id:         examPaperId,
          original_filename: file.name,
          content_type:      file.type,
          size_bytes:        file.size,
        })
      }

      // 4 — register scanned script and queue AI scoring
      setUploadStep('Registering script…')
      const payload: ScriptIngestPayload = {
        exam_paper_id:    examPaperId,
        student_user_id:  studentUserId || undefined,
        student_roll_ref: studentRollRef.trim() || undefined,
      }
      return uploadScript(payload, objectKey)
    },
    onSuccess: (data) => {
      setResult(data)
      setError(null)
      setUploadStep(null)
    },
    onError: (err: unknown) => {
      const apiMsg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message
      setError(apiMsg ?? (err as Error).message ?? 'Upload failed. Please try again.')
      setUploadStep(null)
    },
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (!examPaperId) { setError('Select an exam paper.'); return }
    submitMut.mutate()
  }

  function reset() {
    setResult(null); setExamPaperId(''); setStudentUserId(''); setStudentSearch('')
    setStudentRollRef(''); setFile(null); setUploadStep(null); setError(null)
  }

  // ── Success screen ──────────────────────────────────────────────────────────
  if (result) {
    return (
      <div className="max-w-xl mx-auto p-6 space-y-6">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => navigate('/scripts')}>
            <ChevronLeft className="w-5 h-5" />
          </Button>
          <h1 className="text-xl font-bold text-gray-900">Script Registered</h1>
        </div>

        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-6 space-y-3">
          <div className="flex items-center gap-2 text-emerald-700 font-semibold">
            <CheckCircle2 className="w-5 h-5" /> Script registered and scoring queued
          </div>
          <div className="space-y-1 text-sm text-emerald-800">
            <p><span className="font-medium">Masked ID:</span> <span className="font-mono">{result.masked_id}</span></p>
            <p><span className="font-medium">Script ID:</span> <span className="font-mono text-xs">{result.script_id}</span></p>
            <p><span className="font-medium">Job ID:</span> <span className="font-mono text-xs">{result.job_id}</span></p>
            <p><span className="font-medium">Status:</span> {result.status}</p>
          </div>
          <p className="text-xs text-emerald-600">
            AI scoring is running in the background. Check the script list for progress.
          </p>
        </div>

        <div className="flex gap-3">
          <Button onClick={() => navigate('/scripts')} className="bg-indigo-600 hover:bg-indigo-700 text-white">
            Back to Script List
          </Button>
          <Button variant="outline" onClick={reset}>Upload Another</Button>
        </div>
      </div>
    )
  }

  // ── Upload form ─────────────────────────────────────────────────────────────
  return (
    <div className="max-w-xl mx-auto p-6 space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate('/scripts')}>
          <ChevronLeft className="w-5 h-5" />
        </Button>
        <div className="flex items-center gap-2">
          <Upload className="w-5 h-5 text-indigo-600" />
          <h1 className="text-xl font-bold text-gray-900">Upload Scanned Script</h1>
        </div>
      </div>

      <div className="rounded-xl border border-yellow-200 bg-yellow-50 p-4 flex gap-2 text-sm text-yellow-800">
        <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-yellow-600" />
        Student identity is masked from evaluators until Board finalisation.
      </div>

      <form onSubmit={handleSubmit} className="space-y-5">

        {/* ── Exam paper dropdown ──────────────────────────── */}
        <div className="space-y-1">
          <label className="block text-sm font-medium text-gray-700">
            Exam Paper <span className="text-red-500">*</span>
          </label>
          <select
            value={examPaperId}
            onChange={e => setExamPaperId(e.target.value)}
            required
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 bg-white"
          >
            <option value="">— Select released exam paper —</option>
            {(papersData?.items ?? []).map(p => (
              <option key={p.id} value={p.id}>
                {p.title} · {p.exam_type.replace('_', ' ')} · {p.total_marks} marks
              </option>
            ))}
          </select>
          {papersData?.items.length === 0 && (
            <p className="text-xs text-orange-600">
              No released exam papers found. A paper must be RELEASED before scripts can be uploaded.
            </p>
          )}
        </div>

        {/* ── File picker ──────────────────────────────────── */}
        <div className="space-y-1">
          <label className="block text-sm font-medium text-gray-700">
            Scanned File <span className="text-gray-600">(PDF / JPG / PNG, max {MAX_SIZE_MB} MB)</span>
          </label>

          {file ? (
            <div className="flex items-center gap-3 border border-gray-200 rounded-lg px-3 py-2 bg-gray-50">
              <FileText className="w-4 h-4 text-indigo-500 shrink-0" />
              <span className="text-sm text-gray-700 truncate flex-1">{file.name}</span>
              <span className="text-xs text-gray-600 shrink-0">
                {(file.size / 1024 / 1024).toFixed(1)} MB
              </span>
              <button
                type="button"
                onClick={() => {
                  setFile(null)
                  if (fileInputRef.current) fileInputRef.current.value = ''
                }}
                className="text-gray-600 hover:text-red-500 shrink-0"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="w-full border-2 border-dashed border-gray-200 rounded-lg px-3 py-6 text-sm text-gray-500 hover:border-indigo-300 hover:text-indigo-600 transition-colors"
            >
              Click to select file (PDF / JPEG / PNG)
            </button>
          )}

          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.jpg,.jpeg,.png"
            onChange={handleFileChange}
            className="hidden"
          />
        </div>

        {/* ── Student identity (optional) ───────────────────── */}
        <div className="border border-gray-100 rounded-xl p-4 space-y-4 bg-gray-50">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
            Student Identity — Optional
          </p>

          {/* Searchable student picker */}
          <div className="space-y-1 relative">
            <label className="block text-sm font-medium text-gray-700">Student Account</label>
            <input
              type="text"
              value={studentSearch}
              onChange={e => { setStudentSearch(e.target.value); setStudentUserId('') }}
              placeholder="Search by name, email, or roll number…"
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 bg-white"
            />
            {studentSearch.trim() && !studentUserId && filteredStudents.length > 0 && (
              <div className="absolute z-10 left-0 right-0 border border-gray-200 rounded-lg bg-white shadow-lg max-h-44 overflow-y-auto">
                {filteredStudents.slice(0, 8).map(s => (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => {
                      setStudentUserId(s.id)
                      setStudentSearch(s.full_name)
                      if (!studentRollRef) setStudentRollRef(s.identifier ?? '')
                    }}
                    className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-indigo-50 border-b border-gray-100 last:border-0"
                  >
                    <span className="font-medium">{s.full_name}</span>
                    {s.identifier && (
                      <span className="text-gray-600 ml-2 text-xs">{s.identifier}</span>
                    )}
                    <span className="text-gray-600 ml-1 text-xs">· {s.email}</span>
                  </button>
                ))}
              </div>
            )}
            {studentUserId && (
              <p className="text-xs text-indigo-600">
                Selected: <strong>{studentSearch}</strong>{' '}
                <button
                  type="button"
                  className="underline text-gray-600 hover:text-red-500"
                  onClick={() => { setStudentUserId(''); setStudentSearch('') }}
                >
                  clear
                </button>
              </p>
            )}
          </div>

          {/* Roll number / reference */}
          <div className="space-y-1">
            <label className="block text-sm font-medium text-gray-700">Roll Number / Reference</label>
            <input
              type="text"
              value={studentRollRef}
              onChange={e => setStudentRollRef(e.target.value)}
              placeholder="e.g. 21CS001"
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 bg-white"
            />
          </div>
        </div>

        {error && (
          <div className="flex gap-2 bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-600">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            {error}
          </div>
        )}

        <Button
          type="submit"
          disabled={submitMut.isPending || !examPaperId}
          className="w-full bg-indigo-600 hover:bg-indigo-700 text-white gap-2"
        >
          {submitMut.isPending ? (
            <><Loader2 className="w-4 h-4 animate-spin" /> {uploadStep ?? 'Processing…'}</>
          ) : (
            <><Upload className="w-4 h-4" /> Register Script &amp; Queue Scoring</>
          )}
        </Button>
      </form>
    </div>
  )
}
