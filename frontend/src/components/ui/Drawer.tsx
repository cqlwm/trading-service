import { X } from 'lucide-react'
import { useEffect, type ReactNode } from 'react'

import { cn } from '@/lib/cn'

/** 右侧抽屉 -- 用于持仓详情 */
export function Drawer({
  open,
  onClose,
  children,
  title,
  width = 'max-w-lg',
}: {
  open: boolean
  onClose: () => void
  children: ReactNode
  title?: ReactNode
  width?: string
}) {
  // ESC 关闭
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* 遮罩 */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />
      {/* 抽屉内容 */}
      <div
        className={cn(
          'relative flex h-full w-full flex-col border-l border-border bg-card shadow-xl',
          width,
        )}
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <div className="text-base font-medium">{title}</div>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <X size={18} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">{children}</div>
      </div>
    </div>
  )
}
