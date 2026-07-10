"""马丁格尔做空策略。

继承 MartingaleStrategy，仅覆盖 name 和 cron，
direction=SHORT 由 config 传入，加仓逻辑已在基类参数化。
"""

from __future__ import annotations

from trading_service.strategies.martingale import MartingaleStrategy


class MartingaleShortStrategy(MartingaleStrategy):
    """马丁格尔做空策略。

    与做多马丁共用全部执行逻辑，区别仅在：
    - name = "martingale_short"（用于 tag 隔离和调度注册）
    - cron = "*/5 * * * * *"（每 5 分钟，做空不需要太频繁）
    - direction = SHORT 由 config 传入
    """

    name = "martingale_short"
    cron = "0 */5 * * * *"  # 6字段：秒 分 时 日 月 周 = 每5分钟
