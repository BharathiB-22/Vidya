import { useParams, useNavigate } from 'react-router-dom'
import { PageShell } from '@/components/shell/PageShell'
import { MarkEntryGrid } from '@/components/marks/MarkEntryGrid'

export default function InternalMarkEntryPage() {
  const { componentId } = useParams<{ componentId: string }>()
  const navigate = useNavigate()

  return (
    <PageShell>
      <MarkEntryGrid
        componentId={componentId ?? ''}
        onBack={() => navigate('/sis/marks/setup')}
      />
    </PageShell>
  )
}
