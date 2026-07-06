import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { sisApi, MarksComponent } from '@/lib/api/sis'

export function PublishComponentDialog({
  component, onClose, onPublished,
}: { component: MarksComponent | null; onClose: () => void; onPublished?: () => void }) {
  const qc = useQueryClient()
  const publishMutation = useMutation({
    mutationFn: (id: string) => sisApi.publishMarksComponent(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['marks-components-my'] })
      qc.invalidateQueries({ queryKey: ['marks-components'] })
      onClose()
      onPublished?.()
    },
  })

  return (
    <Dialog open={!!component} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>Publish Component</DialogTitle></DialogHeader>
        <div className="flex gap-2 items-start rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
          Publishing <strong>{component?.name}</strong> makes it visible to students and requires a reason for future mark edits.
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={() => component && publishMutation.mutate(component.id)} disabled={publishMutation.isPending}>
            {publishMutation.isPending ? 'Publishing…' : 'Publish'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function DeleteComponentDialog({
  component, onClose, onDeleted,
}: { component: MarksComponent | null; onClose: () => void; onDeleted?: () => void }) {
  const qc = useQueryClient()
  const deleteMutation = useMutation({
    mutationFn: (id: string) => sisApi.deleteMarksComponent(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['marks-components-my'] })
      qc.invalidateQueries({ queryKey: ['marks-components'] })
      onClose()
      onDeleted?.()
    },
  })

  return (
    <Dialog open={!!component} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>Delete Component</DialogTitle></DialogHeader>
        <p className="text-sm text-muted-foreground">Delete <strong>{component?.name}</strong>? This cannot be undone.</p>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button variant="destructive" onClick={() => component && deleteMutation.mutate(component.id)} disabled={deleteMutation.isPending}>
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
