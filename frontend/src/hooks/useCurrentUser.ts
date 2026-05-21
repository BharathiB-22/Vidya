import { useAuth } from '@/lib/auth'
import type { CurrentUser } from '@/lib/auth'

export function useCurrentUser(): CurrentUser | null {
  return useAuth().user
}
