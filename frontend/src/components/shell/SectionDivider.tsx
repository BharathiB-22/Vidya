interface SectionDividerProps {
  label: string
}

export function SectionDivider({ label }: SectionDividerProps) {
  return (
    <div className="flex items-center gap-3">
      <h2 className="text-xs font-bold text-foreground uppercase tracking-widest whitespace-nowrap">
        {label}
      </h2>
      <div className="flex-1 h-px bg-gray-100" />
    </div>
  )
}
