import { ShieldCheck, ShieldAlert, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useSyllabusCompliance } from '@/hooks/syllabuses'

interface Props {
  syllabusId: string
}

export function CompliancePanel({ syllabusId }: Props) {
  const { data, isLoading, isError, refetch, isFetching } = useSyllabusCompliance(syllabusId)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">Compliance Check</h3>
        <Button
          size="sm"
          variant="outline"
          onClick={() => refetch()}
          disabled={isFetching}
        >
          <RefreshCw className={`h-4 w-4 mr-1 ${isFetching ? 'animate-spin' : ''}`} />
          {isFetching ? 'Checking…' : 'Run Check'}
        </Button>
      </div>

      {isLoading && (
        <p className="text-sm text-gray-400 py-4 text-center">Running compliance check…</p>
      )}

      {isError && (
        <p className="text-sm text-red-500 py-4">Failed to load compliance results.</p>
      )}

      {data && (
        <div className="space-y-3">
          <div className={`flex items-center gap-2 rounded-lg px-4 py-3 border ${
            data.passed
              ? 'bg-green-50 border-green-200 text-green-700'
              : 'bg-red-50 border-red-200 text-red-700'
          }`}>
            {data.passed
              ? <ShieldCheck className="h-5 w-5 shrink-0" />
              : <ShieldAlert className="h-5 w-5 shrink-0" />}
            <span className="text-sm font-semibold">
              {data.passed ? 'All checks passed' : `${data.violations.length} issue${data.violations.length !== 1 ? 's' : ''} found`}
            </span>
          </div>

          {data.violations.length > 0 && (
            <div className="divide-y divide-gray-100 rounded-lg border border-gray-200">
              {data.violations.map((v, i) => (
                <div key={i} className="flex items-start gap-3 px-4 py-3">
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded-full shrink-0 ${
                    v.severity === 'ERROR'
                      ? 'bg-red-100 text-red-700'
                      : 'bg-yellow-100 text-yellow-700'
                  }`}>
                    {v.severity}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-mono text-gray-500">{v.code}</p>
                    <p className="text-sm text-gray-700">{v.message}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
