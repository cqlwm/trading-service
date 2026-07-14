import { AlertTriangle, Clock, ExternalLink, FileText, Loader2, Send, Terminal } from 'lucide-react'

import { Drawer } from '@/components/ui/Drawer'
import { Badge } from '@/components/ui/Badge'
import { Skeleton } from '@/components/ui/Skeleton'
import { useExecutionDetail } from '@/hooks/useStrategies'
import { usePublishPost } from '@/hooks/useMutations'
import { formatDateTime } from '@/lib/format'
import { cn } from '@/lib/cn'
import type { Post, StrategyActionRecord } from '@/types'

/** action_type 对应的 Badge 颜色 */
function actionTypeBadgeClass(actionType: string): string {
  switch (actionType) {
    case 'open':
      return 'bg-success/15 text-success'
    case 'add':
      return 'bg-warning/15 text-warning'
    case 'close':
      return 'bg-destructive/15 text-destructive'
    case 'content':
      return 'bg-primary/15 text-primary'
    default:
      return 'bg-muted text-muted-foreground'
  }
}

/** 动作记录卡片 */
function ActionCard({ action }: { action: StrategyActionRecord }) {
  const hasData = Object.keys(action.reason_data).length > 0
  const hasSignals = action.signal_ids.length > 0

  return (
    <div className="rounded-md border border-border/60 p-3 text-sm">
      <div className="mb-2 flex items-center gap-2">
        <span
          className={cn(
            'inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium',
            actionTypeBadgeClass(action.action_type),
          )}
        >
          {action.action_type}
        </span>
        <span className="font-mono font-medium">{action.symbol}</span>
        <span className="ml-auto text-xs text-muted-foreground">
          {formatDateTime(action.created_at)}
        </span>
      </div>
      {action.reason && (
        <p className="mb-2 text-xs text-foreground/80">{action.reason}</p>
      )}
      {hasData && (
        <details className="mb-1">
          <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">
            决策数据 (reason_data)
          </summary>
          <pre className="mt-1 max-h-40 overflow-auto rounded bg-muted/50 p-2 text-xs">
            {JSON.stringify(action.reason_data, null, 2)}
          </pre>
        </details>
      )}
      {hasSignals && (
        <div className="flex items-center gap-1 text-xs text-muted-foreground">
          <Terminal size={11} />
          关联信号: {action.signal_ids.join(', ')}
        </div>
      )}
    </div>
  )
}

/** 贴文发布状态 */
function PublishStatusBadge({ post }: { post: Post }) {
  if (post.published_at) {
    return (
      <Badge variant="success" className="text-xs">已发布</Badge>
    )
  }
  if (post.publish_error) {
    return (
      <Badge variant="destructive" className="text-xs" title={post.publish_error}>
        发布失败
      </Badge>
    )
  }
  return <Badge variant="muted" className="text-xs">未发布</Badge>
}

/** 贴文卡片 -- 展示 LLM 正文 + 发布状态 + 可折叠的完整 prompt */
function PostCard({ post }: { post: Post }) {
  const publishMutation = usePublishPost()
  const isPublishing = publishMutation.isPending

  return (
    <div className="rounded-md border border-border/60 p-3">
      <div className="mb-2 flex items-center gap-2">
        <Badge variant="secondary" className="text-xs">{post.style}</Badge>
        <span className="font-mono text-sm font-medium">{post.symbol}</span>
        <PublishStatusBadge post={post} />
        <span className="ml-auto text-xs text-muted-foreground">
          {formatDateTime(post.created_at)}
        </span>
      </div>
      {/* LLM 生成的正文 */}
      <div className="mb-3 rounded-md bg-muted/30 p-3 text-sm leading-relaxed whitespace-pre-wrap">
        {post.post_text}
      </div>
      {/* 发布信息：分享链接 / 错误信息 / 手动发布按钮 */}
      <div className="mb-3 space-y-2">
        {post.share_link && (
          <a
            href={post.share_link}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
          >
            <ExternalLink size={12} />
            {post.share_link}
          </a>
        )}
        {post.publish_error && (
          <p className="text-xs text-destructive/80" title={post.publish_error}>
            错误：{post.publish_error}
          </p>
        )}
        {/* 未发布或发布失败时显示手动发布按钮 */}
        {!post.published_at && (
          <button
            onClick={() => publishMutation.mutate(post.id)}
            disabled={isPublishing}
            className="inline-flex items-center gap-1 rounded-md border border-border/60 px-2.5 py-1 text-xs text-foreground/80 transition-colors hover:bg-muted/50 disabled:opacity-50"
          >
            {isPublishing ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Send size={12} />
            )}
            {post.publish_error ? '重试发布' : '手动发布'}
          </button>
        )}
      </div>
      {/* 可折叠的完整 prompt */}
      <details>
        <summary className="flex cursor-pointer items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
          <FileText size={11} />
          查看完整 Prompt
        </summary>
        <pre className="mt-1 max-h-64 overflow-auto rounded bg-muted/50 p-3 text-xs leading-relaxed whitespace-pre-wrap">
          {post.prompt}
        </pre>
      </details>
    </div>
  )
}

/** 执行详情抽屉 */
export function ExecutionDetailDrawer({
  executionId,
  strategyName,
  onClose,
}: {
  executionId: string | null
  strategyName: string
  onClose: () => void
}) {
  const { data: detail, isLoading, isError } = useExecutionDetail(strategyName, executionId)

  return (
    <Drawer
      open={!!executionId}
      onClose={onClose}
      title="执行详情"
      width="max-w-2xl"
    >
      {isLoading ? (
        <div className="space-y-3 p-5">
          <Skeleton className="h-8" />
          <Skeleton className="h-32" />
          <Skeleton className="h-40" />
        </div>
      ) : isError || !detail ? (
        <div className="flex flex-col items-center gap-3 py-20 text-center">
          <AlertTriangle size={32} className="text-destructive" />
          <p className="text-sm text-destructive">加载执行详情失败</p>
        </div>
      ) : (
        <div className="space-y-6 p-5">
          {/* 执行概要 */}
          <div>
            <div className="mb-3 flex items-center gap-2">
              <Badge variant={detail.success ? 'success' : 'destructive'}>
                {detail.success ? '成功' : '失败'}
              </Badge>
              <span className="font-mono text-sm text-muted-foreground">{detail.id}</span>
            </div>
            <div className="rounded-md border border-border">
              <div className="px-4">
                <div className="flex justify-between border-b border-border/40 py-2 text-sm">
                  <span className="text-muted-foreground">策略</span>
                  <span className="font-medium">{detail.strategy_name}</span>
                </div>
                <div className="flex justify-between border-b border-border/40 py-2 text-sm">
                  <span className="text-muted-foreground">动作数</span>
                  <span className="font-medium">{detail.action_count}</span>
                </div>
                <div className="flex justify-between border-b border-border/40 py-2 text-sm">
                  <span className="text-muted-foreground">开始时间</span>
                  <span className="font-mono text-xs">{formatDateTime(detail.started_at)}</span>
                </div>
                {detail.finished_at && (
                  <div className="flex justify-between border-b border-border/40 py-2 text-sm">
                    <span className="text-muted-foreground">结束时间</span>
                    <span className="font-mono text-xs">{formatDateTime(detail.finished_at)}</span>
                  </div>
                )}
                {detail.error && (
                  <div className="flex justify-between py-2 text-sm">
                    <span className="text-muted-foreground">错误</span>
                    <span className="font-medium text-destructive">{detail.error}</span>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* 动作记录 */}
          <div>
            <h3 className="mb-3 flex items-center gap-1.5 text-sm font-medium">
              <Clock size={14} /> 动作记录 ({detail.actions.length})
            </h3>
            <div className="space-y-2">
              {detail.actions.length === 0 ? (
                <p className="py-4 text-center text-sm text-muted-foreground">
                  暂无动作记录
                </p>
              ) : (
                detail.actions.map((action) => (
                  <ActionCard key={action.id} action={action} />
                ))
              )}
            </div>
          </div>

          {/* 贴文列表 */}
          <div>
            <h3 className="mb-3 flex items-center gap-1.5 text-sm font-medium">
              <FileText size={14} /> 生成贴文 ({detail.posts.length})
            </h3>
            <div className="space-y-2">
              {detail.posts.length === 0 ? (
                <p className="py-4 text-center text-sm text-muted-foreground">
                  暂无贴文
                </p>
              ) : (
                detail.posts.map((post) => (
                  <PostCard key={post.id} post={post} />
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </Drawer>
  )
}
