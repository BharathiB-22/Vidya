// M09 Paper Administration — Upload / ingest a scanned answer script
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { Upload, ChevronLeft, Loader2, CheckCircle2, AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { uploadScript } from '@/lib/api/scripts'
import type { ScriptIngestPayload, ScriptIngestResponse } from '@/types/script'

export default function ScriptUploadPage() {
  const navigate = useNavigate()

  const [examPaperId, setExamPaperId]       = useState('')
  const [studentUserId, setStudentUserId]   = useState('')
  const [studentRollRef, setStudentRollRef] = useState('')
  const [uploadUrl, setUploadUrl]           = useState('')
  const [error, setError]                   = useState<string | null>(null)
  const [result, setResult]                 = useState<ScriptIngestResponse | null>(null)

  const uploadMut = useMutation({
    mutationFn: () => {
      const payload: ScriptIngestPayload = {
        exam_paper_id:    examPaperId.trim(),
        student_user_id:  studentUserId.trim() || undefined,
        student_roll_ref: studentRollRef.trim() || undefined,
      }
      return uploadScript(payload, uploadUrl.trim() || undefined)
    },
    onSuccess: (data) => {
      setResult(data)
      setError(null)
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message
      setError(msg ?? 'Upload failed. Please try again.')
    },
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (!examPaperId.trim()) {
      setError('Exam Paper ID is required.')
      return
    }
    uploadMut.mutate()
  }

  if (result) {
    return (
      <div className="max-w-xl mx-auto p-6 space-y-6">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => navigate('/scripts')}>
            <ChevronLeft className="w-5 h-5" />
          </Button>
          <h1 className="text-xl font-bold text-gray-900">Script Uploaded</h1>
        </div>

        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-6 space-y-3">
          <div className="flex items-center gap-2 text-emerald-700 font-semibold">
            <CheckCircle2 className="w-5 h-5" />
            Script registered successfully
          </div>
          <div className="space-y-1 text-sm text-emerald-800">
            <p><span className="font-medium">Masked ID:</span> <span className="font-mono">{result.masked_id}</span></p>
            <p><span className="font-medium">Script ID:</span> <span className="font-mono text-xs">{result.script_id}</span></p>
            <p><span className="font-medium">Job ID:</span> <span className="font-mono text-xs">{result.job_id}</span></p>
            <p><span className="font-medium">Status:</span> {result.status}</p>
          </div>
          <p className="text-xs text-emerald-600">
            The AI scoring task has been queued. Refresh the script list to check progress.
          </p>
        </div>

        <div className="flex gap-3">
          <Button onClick={() => navigate('/scripts')} className="bg-indigo-600 hover:bg-indigo-700 text-white">
            Back to Script List
          </Button>
          <Button variant="outline" onClick={() => { setResult(null); setExamPaperId(''); setStudentUserId(''); setStudentRollRef(''); setUploadUrl('') }}>
            Upload Another
          </Button>
        </div>
      </div>
    )
  }

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
        <span>
          Student identity is stored securely and will not be visible to evaluators until Board finalisation.
          Provide student details only if available.
        </span>
      </div>

      <form onSubmit={handleSubmit} className="space-y-5">
        <div className="space-y-1">
          <label className="block text-sm font-medium text-gray-700">
            Exam Paper ID <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            value={examPaperId}
            onChange={e => setExamPaperId(e.target.value)}
            placeholder="UUID of the exam paper"
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 font-mono"
            required
          />
        </div>

        <div className="space-y-1">
          <label className="block text-sm font-medium text-gray-700">
            S3 Upload URL / Object Key
          </label>
          <input
            type="text"
            value={uploadUrl}
            onChange={e => setUploadUrl(e.target.value)}
            placeholder="e.g. uploads/scripts/scan_001.pdf"
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
          />
          <p className="text-xs text-gray-400">
            Upload the PDF scan to S3 first, then paste the object key here.
          </p>
        </div>

        <div className="border border-gray-100 rounded-xl p-4 space-y-4 bg-gray-50">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
            Student Identity (Optional — Admin/Board only)
          </p>

          <div className="space-y-1">
            <label className="block text-sm font-medium text-gray-700">Student User ID</label>
            <input
              type="text"
              value={studentUserId}
              onChange={e => setStudentUserId(e.target.value)}
              placeholder="UUID of student account"
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 font-mono"
            />
          </div>

          <div className="space-y-1">
            <label className="block text-sm font-medium text-gray-700">Roll Number / Reference</label>
            <input
              type="text"
              value={studentRollRef}
              onChange={e => setStudentRollRef(e.target.value)}
              placeholder="e.g. 21CS001"
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
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
          disabled={uploadMut.isPending}
          className="w-full bg-indigo-600 hover:bg-indigo-700 text-white gap-2"
        >
          {uploadMut.isPending
            ? <><Loader2 className="w-4 h-4 animate-spin" /> Uploading…</>
            : <><Upload className="w-4 h-4" /> Register Script &amp; Queue Scoring</>
          }
        </Button>
      </form>
    </div>
  )
}
