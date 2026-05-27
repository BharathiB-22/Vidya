interface PageShellProps {
  children: React.ReactNode
  /**
   * 'sm' = max-w-3xl  (narrow forms / settings)
   * 'lg' = max-w-5xl  (tables / lists — default)
   */
  width?: 'sm' | 'lg'
}

export function PageShell({ children, width = 'lg' }: PageShellProps) {
  const maxW = width === 'sm' ? 'max-w-3xl' : 'max-w-5xl'
  return (
    <div className={`${maxW} mx-auto px-6 py-6 space-y-6`}>
      {children}
    </div>
  )
}
