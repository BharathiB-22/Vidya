import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { queryClient } from '@/lib/queryClient'
import { AuthProvider } from '@/lib/auth'
import { AdminAuthProvider } from '@/lib/adminAuth'
import { BrandingProvider } from '@/lib/branding'
import { WorkspaceProvider } from '@/lib/workspace'
import { GovernanceProvider } from '@/lib/governance'
import { Toaster } from '@/components/ui/Toaster'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AdminAuthProvider>
          <BrandingProvider>
            <AuthProvider>
              {/* Governance vocabulary (Board vs University Members) is tenant-wide
                  and read once per session; it must sit inside AuthProvider because
                  the lookup is authenticated. */}
              <GovernanceProvider>
                <WorkspaceProvider>
                  <App />
                  <Toaster />
                </WorkspaceProvider>
              </GovernanceProvider>
            </AuthProvider>
          </BrandingProvider>
        </AdminAuthProvider>
      </BrowserRouter>
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  </React.StrictMode>,
)
