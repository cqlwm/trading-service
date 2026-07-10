import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { Toaster } from 'sonner'

import { AppShell } from '@/components/layout/AppShell'
import { DashboardPage } from '@/pages/DashboardPage'
import { OrdersPage } from '@/pages/OrdersPage'
import { PositionsPage } from '@/pages/PositionsPage'
import { SignalsPage } from '@/pages/SignalsPage'
import { StrategiesPage } from '@/pages/StrategiesPage'
import { TimelinePage } from '@/pages/TimelinePage'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 10_000,
    },
  },
})

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<DashboardPage />} />
            <Route path="positions" element={<PositionsPage />} />
            <Route path="orders" element={<OrdersPage />} />
            <Route path="signals" element={<SignalsPage />} />
            <Route path="strategies" element={<StrategiesPage />} />
            <Route path="timeline" element={<TimelinePage />} />
          </Route>
        </Routes>
      </BrowserRouter>
      <Toaster
        theme="dark"
        position="top-right"
        richColors
        toastOptions={{
          style: {
            background: 'hsl(222 20% 12%)',
            border: '1px solid hsl(222 16% 20%)',
          },
        }}
      />
    </QueryClientProvider>
  )
}

export default App
