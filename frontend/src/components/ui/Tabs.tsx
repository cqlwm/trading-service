import { cn } from '@/lib/cn'

/** 简易 Tabs -- 用于状态筛选 */
export interface TabItem<T extends string> {
  value: T
  label: string
  count?: number
}

export function Tabs<T extends string>({
  items,
  value,
  onChange,
}: {
  items: TabItem<T>[]
  value: T
  onChange: (v: T) => void
}) {
  return (
    <div className="flex gap-1 border-b border-border">
      {items.map((item) => (
        <button
          key={item.value}
          onClick={() => onChange(item.value)}
          className={cn(
            'relative px-4 py-2.5 text-sm font-medium transition-colors',
            value === item.value
              ? 'text-primary'
              : 'text-muted-foreground hover:text-foreground',
          )}
        >
          {item.label}
          {item.count !== undefined && (
            <span className="ml-1.5 rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
              {item.count}
            </span>
          )}
          {value === item.value && (
            <span className="absolute inset-x-0 -bottom-px h-0.5 bg-primary" />
          )}
        </button>
      ))}
    </div>
  )
}
