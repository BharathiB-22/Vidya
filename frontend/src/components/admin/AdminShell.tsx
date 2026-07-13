import { useState } from 'react'
import { Outlet, Link, useLocation } from 'react-router-dom'
import {
  Building2, PlusCircle, ScrollText, Activity, BarChart2,
  Settings, LogOut, X, Shield, LayoutDashboard, Bell, Search, ChevronRight,
  User, Palette, Trash2, Database,
} from 'lucide-react'
import { useAdminAuth } from '@/lib/adminAuth'
import { PlatformThemeProvider, usePlatformTheme } from '@/lib/platformTheme'
import { PlatformThemeSwitcher } from '@/components/admin/PlatformThemeSwitcher'

interface NavItem {
  label: string
  to?: string
  icon: typeof Building2
  soon?: boolean
  end?: boolean
}

interface NavSection {
  heading: string
  items: NavItem[]
}

const NAV_SECTIONS: NavSection[] = [
  {
    heading: 'Platform',
    items: [
      { label: 'Dashboard',       to: '/admin/dashboard',        icon: LayoutDashboard, end: true },
      { label: 'Tenants',         to: '/admin/tenants',          icon: Building2,       end: true },
      { label: 'Deleted Tenants', to: '/admin/deleted-tenants',  icon: Trash2 },
      { label: 'Create Tenant',   to: '/admin/tenants/new',      icon: PlusCircle },
    ],
  },
  {
    heading: 'Operations',
    items: [
      { label: 'Monitoring',         to: '/admin/monitoring',          icon: BarChart2  },
      { label: 'Platform Health',    to: '/admin/health',              icon: Activity   },
      { label: 'Audit Logs',         to: '/admin/audit-logs',          icon: ScrollText },
      { label: 'Tenant Migrations',  to: '/admin/tenant-migrations',   icon: Database   },
    ],
  },
  {
    heading: 'Administration',
    items: [
      { label: 'Branding',   to: '/admin/branding',  icon: Palette  },
      { label: 'Settings',   to: '/admin/settings',  icon: Settings },
      { label: 'My Profile', to: '/admin/profile',   icon: User     },
    ],
  },
]

const BREADCRUMB_MAP: Record<string, string> = {
  '/admin/dashboard':       'Dashboard',
  '/admin/tenants':         'Tenants',
  '/admin/tenants/new':     'New University',
  '/admin/deleted-tenants': 'Deleted Tenants',
  '/admin/monitoring':      'Monitoring',
  '/admin/audit-logs':      'Audit Logs',
  '/admin/settings':        'Settings',
  '/admin/health':          'Platform Health',
  '/admin/profile':         'My Profile',
  '/admin/branding':            'Platform Branding',
  '/admin/tenant-migrations':  'Tenant Migrations',
}

function getBreadcrumb(pathname: string): string {
  if (BREADCRUMB_MAP[pathname]) return BREADCRUMB_MAP[pathname]
  if (pathname.startsWith('/admin/tenants/')) return 'Tenant Detail'
  return 'Platform Console'
}

function isNavActive(to: string, pathname: string, end?: boolean): boolean {
  if (end) return pathname === to
  return pathname === to || pathname.startsWith(to + '/')
}

function AdminSidebar({ onClose }: { onClose: () => void }) {
  const location = useLocation()
  const { logout } = useAdminAuth()

  return (
    <div className="flex flex-col h-full" style={{ background: 'var(--pc-chrome)', borderRight: '1px solid var(--pc-chrome-border)' }}>

      {/* Brand header */}
      <div
        className="relative px-4 py-4 flex items-center justify-between gap-2 overflow-hidden"
        style={{ borderBottom: '1px solid var(--pc-chrome-border)' }}
      >
        <div
          className="absolute top-0 left-0 w-28 h-full pointer-events-none"
          style={{ background: 'radial-gradient(ellipse at left, var(--pc-brand-glow) 0%, transparent 70%)' }}
        />
        <div className="relative flex items-center gap-2.5 min-w-0">
          <img
            src="/branding/sherpavector-logo.png"
            alt="SherpaVector"
            className="w-8 h-8 rounded-full object-contain flex-shrink-0"
            style={{ filter: 'drop-shadow(0 0 6px var(--pc-accent-glow))' }}
          />
          <div className="min-w-0">
            <p className="text-[12px] font-bold text-white leading-none tracking-wide">SherpaVector</p>
            <p className="text-[10px] text-slate-600 truncate mt-0.5">Platform Console</p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="relative p-1 rounded text-slate-600 hover:text-slate-300 hover:bg-white/10 lg:hidden flex-shrink-0"
          aria-label="Close sidebar"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-3 px-2">
        {NAV_SECTIONS.map((section) => (
          <div key={section.heading} className="mb-4">
            <div className="flex items-center gap-2 px-2 mb-1.5">
              <span className="text-[9px] font-bold text-slate-700 uppercase tracking-[0.14em] whitespace-nowrap">
                {section.heading}
              </span>
              <div className="flex-1 h-px" style={{ background: 'var(--pc-t-overlay-04)' }} />
            </div>
            <ul className="space-y-0.5">
              {section.items.map((item) => {
                if (item.soon || !item.to) {
                  return (
                    <li key={item.label}>
                      <span className="flex items-center gap-2.5 px-2.5 py-[7px] rounded-lg text-sm font-medium cursor-not-allowed select-none">
                        <item.icon className="h-[15px] w-[15px] flex-shrink-0 text-slate-700" />
                        <span className="truncate text-slate-600">{item.label}</span>
                        <span
                          className="ml-auto text-[8px] px-1.5 py-0.5 rounded-sm font-semibold uppercase tracking-wider"
                          style={{ background: 'var(--pc-t-overlay-03)', border: '1px solid var(--pc-t-overlay-07)', color: 'var(--pc-slate-700)' }}
                        >
                          soon
                        </span>
                      </span>
                    </li>
                  )
                }

                const active = isNavActive(item.to, location.pathname, item.end)
                return (
                  /* Active nav is the accent, not a status colour — it follows
                     --pc-accent, which is this same emerald in Blue and blue in
                     the White/Black themes. */
                  <li key={item.label} className="relative">
                    {active && (
                      <div
                        className="absolute left-0 top-1 bottom-1 w-[3px] rounded-r-full"
                        style={{ background: 'var(--pc-accent-icon)' }}
                      />
                    )}
                    <Link
                      to={item.to}
                      onClick={onClose}
                      className={`flex items-center gap-2.5 px-2.5 py-[7px] rounded-lg text-sm font-medium transition-all duration-150 ${
                        active ? '' : 'text-slate-500 hover:text-slate-200'
                      }`}
                      style={active
                        ? { background: 'var(--pc-accent-soft)', color: 'var(--pc-accent-text)' }
                        : {}}
                      onMouseEnter={(e) => { if (!active) e.currentTarget.style.background = 'var(--pc-t-overlay-04)' }}
                      onMouseLeave={(e) => { if (!active) e.currentTarget.style.background = '' }}
                    >
                      <item.icon
                        className={`h-[15px] w-[15px] flex-shrink-0 ${active ? '' : 'text-slate-600'}`}
                        style={active ? { color: 'var(--pc-accent-icon)' } : {}}
                      />
                      <span className="truncate">{item.label}</span>
                    </Link>
                  </li>
                )
              })}
            </ul>
          </div>
        ))}

        {/* Sign out */}
        <div className="mb-4">
          <ul>
            <li>
              <button
                onClick={logout}
                className="w-full flex items-center gap-2.5 px-2.5 py-[7px] rounded-lg text-sm font-medium text-slate-600 transition-all duration-150"
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'var(--pc-t-overlay-04)'
                  e.currentTarget.style.color = 'var(--pc-red-400)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = ''
                  e.currentTarget.style.color = ''
                }}
              >
                <LogOut className="h-[15px] w-[15px] flex-shrink-0" />
                <span>Sign out</span>
              </button>
            </li>
          </ul>
        </div>
      </nav>

      {/* Footer */}
      <div className="px-3 py-3" style={{ borderTop: '1px solid var(--pc-chrome-border)' }}>
        <div className="flex items-center gap-2">
          <div
            className="w-7 h-7 rounded-md flex items-center justify-center flex-shrink-0"
            style={{ background: 'var(--pc-accent-soft)', border: '1px solid var(--pc-accent-border)' }}
          >
            <Shield className="h-3.5 w-3.5" style={{ color: 'var(--pc-accent)' }} />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-semibold text-slate-300 leading-tight">Super Admin</p>
            <p className="text-[9px] text-slate-700 leading-tight mt-0.5 uppercase tracking-wide font-medium">
              Platform Owner
            </p>
          </div>
        </div>
        <p className="text-[8px] text-slate-700 mt-2.5 font-bold tracking-[0.18em] uppercase">
          VIDYA AI · Platform Console
        </p>
      </div>

    </div>
  )
}

function AdminTopbar({ onMenuClick }: { onMenuClick: () => void }) {
  const location = useLocation()
  const breadcrumb = getBreadcrumb(location.pathname)

  return (
    <header
      className="h-12 flex items-center px-4 gap-3 flex-shrink-0 sticky top-0 z-10"
      style={{ background: 'var(--pc-chrome)', borderBottom: '1px solid var(--pc-chrome-border)' }}
    >
      {/* Mobile hamburger */}
      <button
        className="p-1.5 rounded-lg text-slate-600 transition-colors lg:hidden"
        style={{}}
        onClick={onMenuClick}
        aria-label="Open navigation"
        onMouseEnter={(e) => {
          e.currentTarget.style.background = 'var(--pc-t-overlay-06)'
          e.currentTarget.style.color = 'var(--pc-slate-300)'
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = ''
          e.currentTarget.style.color = ''
        }}
      >
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      <div className="hidden lg:block w-px h-4 flex-shrink-0" style={{ background: 'var(--pc-t-overlay-08)' }} />

      {/* Breadcrumb */}
      <div className="hidden sm:flex items-center gap-2 flex-1 min-w-0">
        <span className="text-[11px] text-slate-600 font-medium">Platform Console</span>
        <ChevronRight className="h-3 w-3 text-slate-700 flex-shrink-0" />
        <span className="text-[11px] font-semibold text-slate-300">{breadcrumb}</span>
      </div>

      <div className="flex-1 sm:hidden" />

      {/* Search */}
      <button
        className="hidden md:flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm transition-colors w-48 flex-shrink-0"
        style={{ background: 'var(--pc-t-overlay-04)', border: '1px solid var(--pc-t-overlay-08)' }}
      >
        <Search className="h-3.5 w-3.5 text-slate-600 flex-shrink-0" />
        <span className="flex-1 text-left text-[12px] text-slate-600">Search…</span>
      </button>

      {/* Theme */}
      <PlatformThemeSwitcher />

      {/* Bell */}
      <button
        className="p-2 rounded-lg text-slate-600 transition-colors flex-shrink-0"
        onMouseEnter={(e) => {
          e.currentTarget.style.background = 'var(--pc-t-overlay-06)'
          e.currentTarget.style.color = 'var(--pc-slate-300)'
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = ''
          e.currentTarget.style.color = ''
        }}
      >
        <Bell className="h-[17px] w-[17px]" />
      </button>

      <div className="w-px h-4 flex-shrink-0" style={{ background: 'var(--pc-t-overlay-08)' }} />

      {/* SA chip */}
      <div className="flex items-center gap-2 flex-shrink-0">
        <div
          className="h-7 w-7 rounded-full flex items-center justify-center flex-shrink-0"
          style={{
            background: 'linear-gradient(135deg, var(--pc-accent), var(--pc-accent-hover))',
            boxShadow: '0 0 8px color-mix(in srgb, var(--pc-accent) 30%, transparent)',
          }}
        >
          {/* Sits on a saturated fill, so it stays white in every theme — the
              .text-white remap is for text on panels. */}
          <Shield className="h-3.5 w-3.5" style={{ color: 'var(--pc-accent-fg)' }} />
        </div>
        <span
          className="hidden sm:inline-flex text-[9px] font-bold px-2 py-0.5 rounded uppercase tracking-wide"
          style={{
            background: 'var(--pc-accent-soft)',
            color: 'var(--pc-accent-icon)',
            border: '1px solid var(--pc-accent-border)',
          }}
        >
          Super Admin
        </span>
      </div>
    </header>
  )
}

/* The themed root. Everything the console renders — including page content via
   <Outlet /> — lives inside this element, and the [data-pc-theme] rules in
   platform-theme.css apply to exactly this subtree and nothing else. */
function AdminShellInner() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const { theme } = usePlatformTheme()

  return (
    <div data-pc-theme={theme} className="flex h-screen" style={{ background: 'var(--pc-bg)' }}>
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/60 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-30 w-60
          transform transition-transform duration-200 ease-in-out
          lg:translate-x-0 lg:static lg:flex-shrink-0
          ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}`}
      >
        <AdminSidebar onClose={() => setSidebarOpen(false)} />
      </aside>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <AdminTopbar onMenuClick={() => setSidebarOpen(true)} />
        <main className="flex-1 overflow-y-auto" style={{ background: 'var(--pc-bg)' }}>
          <Outlet />
        </main>
      </div>
    </div>
  )
}

export function AdminShell() {
  return (
    <PlatformThemeProvider>
      <AdminShellInner />
    </PlatformThemeProvider>
  )
}
