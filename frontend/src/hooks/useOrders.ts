import { useInfiniteQuery } from '@tanstack/react-query'

import { apiGet, buildQuery } from '@/api/client'
import { ENDPOINTS, PAGE_SIZE } from '@/lib/constants'
import type { Order, OrderType, PaginatedResponse } from '@/types'

interface OrdersParams {
  symbol?: string
  orderType?: OrderType
}

/**
 * 订单流水 -- useInfiniteQuery 实现加载更多。
 * 后端返回 {data, total}，total 为符合筛选条件的总数。
 */
export function useOrders(params: OrdersParams = {}) {
  return useInfiniteQuery<PaginatedResponse<Order>>({
    queryKey: ['orders', params.symbol, params.orderType],
    queryFn: ({ pageParam }) =>
      apiGet<PaginatedResponse<Order>>(
        ENDPOINTS.orders +
          buildQuery({
            symbol: params.symbol,
            order_type: params.orderType,
            limit: PAGE_SIZE,
            offset: (pageParam as number) ?? 0,
          }),
      ),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      // 已加载总数 >= total，说明到底
      const loaded = allPages.reduce((sum, p) => sum + p.data.length, 0)
      if (loaded >= lastPage.total) return undefined
      return loaded
    },
  })
}
