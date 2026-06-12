// M09.9 — Admin Compliance & Audit dashboard
import { ComplianceView } from '@/components/compliance/ComplianceView'

export default function AdminCompliancePage() {
  return (
    <ComplianceView
      title="Examination Compliance & Audit"
      subtitle="Complete, immutable governance trail — who changed marks, when, why, and who approved"
    />
  )
}
