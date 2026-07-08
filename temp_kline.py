class BinanceFutureKline(BaseModel):
    """币安合约 K 线数据。"""

    open_time: int
    open_price: str
    high_price: str
    low_price: str
    close_price: str
    volume: str
    close_time: int
    quote_volume: str
    trade_count: int
    taker_buy_base_volume: str
    taker_buy_quote_volume: str
    ignore: str

    @classmethod
    def from_list(cls, kline_data: list) -> "BinanceFutureKline":
        """从币安 API 返回的数组创建 K 线实例。

        Args:
            kline_data: [open_time, open, high, low, close, volume, close_time,
                         quote_volume, trade_count, taker_buy_base, taker_buy_quote, ignore]

        Returns:
            BinanceFutureKline: K 线数据实例
        """
        return cls(
            open_time=kline_data[0],
            open_price=kline_data[1],
            high_price=kline_data[2],
            low_price=kline_data[3],
            close_price=kline_data[4],
            volume=kline_data[5],
            close_time=kline_data[6],
            quote_volume=kline_data[7],
            trade_count=kline_data[8],
            taker_buy_base_volume=kline_data[9],
            taker_buy_quote_volume=kline_data[10],
            ignore=kline_data[11],
        )

    @property
    def open_price_float(self) -> float:
        """开盘价（数值型）。"""
        return float(self.open_price)

    @property
    def high_price_float(self) -> float:
        """最高价（数值型）。"""
        return float(self.high_price)

    @property
    def low_price_float(self) -> float:
        """最低价（数值型）。"""
        return float(self.low_price)

    @property
    def close_price_float(self) -> float:
        """收盘价（数值型）。"""
        return float(self.close_price)

    @property
    def volume_float(self) -> float:
        """成交量（基础货币，数值型）。"""
        return float(self.volume)

    @property
    def quote_volume_float(self) -> float:
        """成交额（计价货币，数值型）。"""
        return float(self.quote_volume)

    @property
    def taker_buy_base_volume_float(self) -> float:
        """主动买入量（基础货币，数值型）。"""
        return float(self.taker_buy_base_volume)

    @property
    def taker_buy_quote_volume_float(self) -> float:
        """主动买入额（计价货币，数值型）。"""
        return float(self.taker_buy_quote_volume)

    @property
    def is_up(self) -> bool:
        """是否上涨（收盘价 >= 开盘价）。"""
        return self.close_price_float >= self.open_price_float

    @property
    def is_down(self) -> bool:
        """是否下跌（收盘价 < 开盘价）。"""
        return self.close_price_float < self.open_price_float
