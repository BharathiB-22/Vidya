// M10 Bell Curve Normaliser — Fairness PDF report download
import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { ChevronLeft, FileDown, Loader2, AlertTriangle, Info, CheckCircle2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { downloadFairnessReport } from '@/lib/api/bellCurve'
import { getErrorMessage } from '@/lib/api'

export default function FairnessReportPage() {
  const navigate       = useNavigate()
  const [search]       = useSearchParams()
  const [paperId, setPaperId] = useState(search.get('paper') ?? '')
  const [isDownloading, setIsDownloading] = useState(false)
  const [error,    setError]    = useState<string | null>(null)
  const [success,  setSuccess]  = useState(false)

  async function handleDownload() {
    setError(null)
    setSuccess(false)
    setIsDownloading(true)
    try {
      const blob = await downloadFairnessReport(paperId.trim() || undefined)
      const url  = URL.createObjectURL(blob)
      const a    = document.createElement('a')
      a.href     = url
      a.download = 'bell_curve_fairness_report.pdf'
      a.click()
      URL.revokeObjectURL(url)
      setSuccess(true)
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setIsDownloading(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-6">

      {/* Header */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate('/bell-curve')}>
          <ChevronLeft className="w-5 h-5" />
        </Button>
        <div>
          <h1 className="text-xl font-bold text-gray-900">Bell Curve Fairness Report</h1>
          <p className="text-xs text-gray-400 mt-0.5">
            Generates a PDF summarising bell curve analyses and Board decisions.
          </p>
        </div>
      </div>

      {/* Advisory */}
      <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 flex gap-3 text-sm text-blue-800">
        <Info className="w-4 h-4 shrink-0 mt-0.5 text-blue-600" />
        <span>
          This report covers bell curve analyses and Board ratification decisions. Raw M09 scores
          are referenced for context only and are not modified by this report.
        </span>
      </div>

      {/* Filter */}
      <div className="rounded-xl border border-gray-200 bg-white p-5 space-y-4">
        <p className="text-sm font-semibold text-gray-700">Report options</p>

        <div className="space-y-1">
          <label className="text-xs font-medium text-gray-600">
            Exam paper UUID (leave blank for all papers)
          </label>
          <input
            type="text"
            value={paperId}
            onChange={e => setPaperId(e.target.value)}
            placeholder="Optional: filter to a single exam paper…"
            className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
          />
        </div>

        {error && (
          <div className="flex gap-2 bg-red-50 border border-red-200 rounded-lg p-3 text-xs text-red-600">
            <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
            {error}
          </div>
        )}

        {success && (
          <div className="flex gap-2 bg-green-50 border border-green-200 rounded-lg p-3 text-xs text-green-700">
            <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
            Report downloaded successfully.
          </div>
        )}

        <Button
          className="w-full bg-indigo-600 hover:bg-indigo-700 text-white gap-2"
          onClick={handleDownload}
          disabled={isDownloading}
        >
          {isDownloading
            ? <Loader2 className="w-4 h-4 animate-spin" />
            : <FileDown className="w-4 h-4" />}
          {isDownloading ? 'Generating PDF…' : 'Download Fairness Report (PDF)'}
        </Button>
      </div>

      <p className="text-xs text-gray-400 text-center">
        The report is generated on the server and served synchronously.
        Large datasets may take a few seconds.
      </p>
    </div>
  )
}
