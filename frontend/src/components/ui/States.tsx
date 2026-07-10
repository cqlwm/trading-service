import { Button } from '@/components/ui/Button'
import { cn } from '@/lib/cn'

/** 空状态提示 */
export function EmptyState({
  message = '暂无数据',
  onRetry,
  className,
}: {
  message?: string
  onRetry?: () => void
  className?: string
}) {
  return (
    <div className={cn('flex flex-col items-center justify-center gap-3 py-16 text-center', className)}>
      <p className="text-sm text-muted-foreground">{message}</p>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          重试
        </Button>
      )}
    </div>
  )
}

/** 错误状态提示 */
export function ErrorState({
  message,
  onRetry,
  className,
}: {
  message: string
  onRetry?: () => void
  className?: string
}) {
  return (
    <div className={cn('flex flex-col items-center justify-center gap-3 py-16 text-center', className)}>
      <p className="text-sm text-destructive">{message}</p>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          重试
        </Button>
      )}
    </div>
  )
}

/** 加载更多按钮 -- 适配无 total 的分页 */
export function LoadMoreButton({
  onClick,
  disabled,
  loading,
}: {
  onClick: () => void
  disabled: boolean
  loading: boolean
}) {
  return (
    <div className="flex justify-center py-4">
      <Button variant="outline" size="sm" onClick={onClick} disabled={disabled || loading}>
        {loading ? '加载中...' : disabled ? '没有更多了' : '加载更多'}
      </Button>
    </div>
  )
}
