import { useInfiniteQuery } from '@tanstack/react-query'

import { apiGet, buildQuery } from '@/api/client'
import { ENDPOINTS, PAGE_SIZE } from '@/lib/constants'
import type { Order, OrderType } from '@/types'

interface OrdersParams {
  symbol?: string
  orderType?: OrderType
}

/**
 * 订单流水 -- useInfiniteQuery 实现加载更多。
 * 后端无 total 字段，以返回长度 < limit 判断是否到底。
 */
export function useOrders(params: OrdersParams = {}) {
  return useInfiniteQuery<Order[]>({
    queryKey: ['orders', params.symbol, params.orderType],
    queryFn: ({ pageParam }) =>
      apiGet<Order[]>(
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
      // 返回不足一页，说明到底
      if (lastPage.length < PAGE_SIZE) return undefined
      return allPages.length * PAGE_SIZE
    },
  })
}
