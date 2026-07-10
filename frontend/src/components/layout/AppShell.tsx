import { NavLink, Outlet } from 'react-router-dom'
import {
  Activity,
  LayoutDashboard,
  ListOrdered,
  Megaphone,
  Radio,
  TrendingUp,
} from 'lucide-react'

import { cn } from '@/lib/cn'

const navItems: { to: string; label: string; icon: typeof Activity; end?: boolean }[] = [
  { to: '/', label: '仪表盘', icon: LayoutDashboard, end: true },
  { to: '/positions', label: '持仓', icon: TrendingUp },
  { to: '/orders', label: '订单', icon: ListOrdered },
  { to: '/signals', label: '信号', icon: Megaphone },
  { to: '/strategies', label: '策略', icon: Activity },
  { to: '/timeline', label: '时间线', icon: Radio },
]

export function AppShell() {
  return (
    <div className="flex h-screen overflow-hidden">
      {/* 侧边栏 */}
      <aside className="flex w-16 flex-col border-r border-border bg-card lg:w-56">
        <div className="flex h-14 items-center gap-2 border-b border-border px-4">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-xs font-bold text-primary-foreground">
            TS
          </div>
          <span className="hidden text-sm font-semibold lg:inline">
            Trading Service
          </span>
        </div>
        <nav className="flex-1 space-y-1 p-2">
          {navItems.map((item) => {
            const Icon = item.icon
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-primary/15 text-primary'
                      : 'text-muted-foreground hover:bg-accent hover:text-foreground',
                  )
                }
              >
                <Icon size={18} className="shrink-0" />
                <span className="hidden lg:inline">{item.label}</span>
              </NavLink>
            )
          })}
        </nav>
      </aside>

      {/* 主内容区 */}
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  )
}
