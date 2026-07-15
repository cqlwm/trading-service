"""信号检测器包"""

from trading_service.detectors.base import SignalDetector, SignalResult
from trading_service.detectors.breakout import BreakoutDetector
from trading_service.detectors.consecutive_candle import ConsecutiveCandleDetector
from trading_service.detectors.price_change import PriceChangeDetector
from trading_service.detectors.technical import TechnicalSignalDetector
from trading_service.detectors.volume_surge import VolumeSurgeDetector

__all__ = [
    "SignalDetector",
    "SignalResult",
    "BreakoutDetector",
    "ConsecutiveCandleDetector",
    "PriceChangeDetector",
    "TechnicalSignalDetector",
    "VolumeSurgeDetector",
]
