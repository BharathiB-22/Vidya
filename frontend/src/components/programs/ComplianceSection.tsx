import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertCircle, AlertTriangle, CheckCircle2, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import * as programsApi from '@/lib/api/programs'
import { programKeys } from '@/hooks/programs'
import type { Program } from '@/types/program'

interface Props {
  program: Program
}

export function ComplianceSection({ program }: Props) {
  const [hasRun, setHasRun] = useState(false)

  const { data: result, isFetching, refetch } = useQuery({
    queryKey: programKeys.compliance(program.id),
    queryFn: () => programsApi.getCompliance(program.id),
    enabled: false,
  })

  function handleRun() {
    setHasRun(true)
    refetch()
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-gray-700">Compliance Check</h3>
        <Button size="sm" variant="outline" onClick={handleRun} disabled={isFetching}>
          <RefreshCw className={`h-4 w-4 mr-1 ${isFetching ? 'animate-spin' : ''}`} />
          {isFetching ? 'Running…' : 'Run Check'}
        </Button>
      </div>

      {!hasRun && !result && (
        <p className="text-sm text-gray-400 text-center py-8">
          Click "Run Check" to validate the program structure.
        </p>
      )}

      {result && (
        <div className="space-y-3">
          <div
            className={`flex items-center gap-2 rounded-md p-3 ${
              result.passed
                ? 'bg-green-50 border border-green-200'
                : 'bg-red-50 border border-red-200'
            }`}
          >
            {result.passed ? (
              <CheckCircle2 className="h-5 w-5 text-green-600 shrink-0" />
            ) : (
              <AlertCircle className="h-5 w-5 text-red-600 shrink-0" />
            )}
            <span
              className={`text-sm font-medium ${
                result.passed ? 'text-green-700' : 'text-red-700'
              }`}
            >
              {result.passed
                ? 'All compliance checks passed'
                : `${result.violations.length} violation(s) found`}
            </span>
          </div>

          {result.violations.length > 0 && (
            <div className="space-y-2">
              {result.violations.map((v, i) => (
                <div
                  key={i}
                  className={`flex items-start gap-2 rounded-md p-3 text-sm ${
                    v.severity === 'ERROR'
                      ? 'bg-red-50 border border-red-200'
                      : 'bg-yellow-50 border border-yellow-200'
                  }`}
                >
                  {v.severity === 'ERROR' ? (
                    <AlertCircle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" />
                  ) : (
                    <AlertTriangle className="h-4 w-4 text-yellow-500 shrink-0 mt-0.5" />
                  )}
                  <div>
                    <span
                      className={`font-semibold ${
                        v.severity === 'ERROR' ? 'text-red-700' : 'text-yellow-700'
                      }`}
                    >
                      [{v.rule_ref}]
                    </span>
                    <span className="ml-1 text-gray-700">{v.message}</span>
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
