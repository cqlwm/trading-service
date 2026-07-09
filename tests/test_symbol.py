"""测试 Symbol 交易对工具类。

TDD 红阶段：覆盖构造、解析、多场景拼接格式、相等性、边界条件。
"""
from __future__ import annotations

import pytest

from trading_service.utils.symbol import Symbol


class TestSymbolConstruct:
    """测试 Symbol 构造。"""

    def test_construct_with_base_and_quote(self) -> None:
        """正常路径：显式传入 base 和 quote 构造。"""
        symbol = Symbol("BTC", "USDT")
        assert symbol.base == "BTC"
        assert symbol.quote == "USDT"

    def test_default_quote_is_usdt(self) -> None:
        """正常路径：quote 默认为 USDT。"""
        symbol = Symbol("ETH")
        assert symbol.base == "ETH"
        assert symbol.quote == "USDT"

    def test_construct_lower_case_normalized(self) -> None:
        """正常路径：大小写归一化为大写。"""
        symbol = Symbol("btc", "usdt")
        assert symbol.base == "BTC"
        assert symbol.quote == "USDT"


class TestSymbolParse:
    """测试 Symbol.parse 多格式解析。"""

    def test_parse_binance_format(self) -> None:
        """边界：解析币安原生格式（无分隔符）BTCUSDT。"""
        symbol = Symbol.parse("BTCUSDT")
        assert symbol.base == "BTC"
        assert symbol.quote == "USDT"

    def test_parse_ccxt_format(self) -> None:
        """正常路径：解析 ccxt 斜杠格式 BTC/USDT。"""
        symbol = Symbol.parse("BTC/USDT")
        assert symbol.base == "BTC"
        assert symbol.quote == "USDT"

    def test_parse_dash_format(self) -> None:
        """正常路径：解析横杠格式 BTC-USDT。"""
        symbol = Symbol.parse("BTC-USDT")
        assert symbol.base == "BTC"
        assert symbol.quote == "USDT"

    def test_parse_underscore_format(self) -> None:
        """正常路径：解析下划线格式 BTC_USDT。"""
        symbol = Symbol.parse("BTC_USDT")
        assert symbol.base == "BTC"
        assert symbol.quote == "USDT"

    def test_parse_case_insensitive(self) -> None:
        """正常路径：解析时大小写不敏感。"""
        symbol = Symbol.parse("btc/usdt")
        assert symbol.base == "BTC"
        assert symbol.quote == "USDT"

    def test_parse_btc_quote(self) -> None:
        """正常路径：解析 BTC 计价交易对。"""
        symbol = Symbol.parse("ETHBTC")
        assert symbol.base == "ETH"
        assert symbol.quote == "BTC"

    def test_parse_unrecognized_raises(self) -> None:
        """异常场景：无法识别的格式应抛出 ValueError。"""
        with pytest.raises(ValueError, match="Cannot parse symbol"):
            Symbol.parse("UNKNOWNXYZ123")


class TestSymbolFormat:
    """测试多场景拼接格式输出。"""

    def test_binance_format(self) -> None:
        """正常路径：binance() 返回无分隔符的币安原生格式。"""
        assert Symbol("BTC", "USDT").binance() == "BTCUSDT"

    def test_ccxt_format(self) -> None:
        """正常路径：ccxt() 返回斜杠分隔的 ccxt 格式（修复点：曾错误返回 BTCUSDT）。"""
        assert Symbol("BTC", "USDT").ccxt() == "BTC/USDT"

    def test_str_returns_binance_format(self) -> None:
        """正常路径：__str__ 默认返回 binance 原生格式（DB 存储格式）。"""
        assert str(Symbol("BTC", "USDT")) == "BTCUSDT"

    def test_round_trip_parse_binance(self) -> None:
        """幂等性：parse(binance()) 往返一致。"""
        original = Symbol("SOL", "USDT")
        assert Symbol.parse(original.binance()) == original

    def test_round_trip_parse_ccxt(self) -> None:
        """幂等性：parse(ccxt()) 往返一致。"""
        original = Symbol("SOL", "USDT")
        assert Symbol.parse(original.ccxt()) == original


class TestSymbolEquality:
    """测试 Symbol 相等性与哈希。"""

    def test_equal_same_base_quote(self) -> None:
        """正常路径：相同 base/quote 的 Symbol 相等。"""
        assert Symbol("BTC", "USDT") == Symbol("BTC", "USDT")

    def test_not_equal_different_base(self) -> None:
        """隔离：不同 base 的 Symbol 不相等。"""
        assert Symbol("BTC", "USDT") != Symbol("ETH", "USDT")

    def test_not_equal_different_quote(self) -> None:
        """隔离：不同 quote 的 Symbol 不相等。"""
        assert Symbol("BTC", "USDT") != Symbol("BTC", "BTC")

    def test_not_equal_to_non_symbol(self) -> None:
        """边界：与非 Symbol 类型比较返回 False，不抛异常。"""
        assert Symbol("BTC", "USDT") != "BTCUSDT"
        assert Symbol("BTC", "USDT") != 42

    def test_hash_consistent_with_eq(self) -> None:
        """正常路径：相等的 Symbol 哈希一致（可用于 set/dict key）。"""
        s1 = Symbol("BTC", "USDT")
        s2 = Symbol("BTC", "USDT")
        assert hash(s1) == hash(s2)

    def test_usable_in_set(self) -> None:
        """正常路径：Symbol 可作为 set 元素去重。"""
        symbols = {Symbol("BTC", "USDT"), Symbol("BTC", "USDT"), Symbol("ETH", "USDT")}
        assert len(symbols) == 2

    def test_repr_is_informative(self) -> None:
        """可维护性：repr 包含 base 和 quote 信息。"""
        repr_str = repr(Symbol("BTC", "USDT"))
        assert "BTC" in repr_str
        assert "USDT" in repr_str
