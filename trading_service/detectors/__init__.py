"""信号检测器包"""

from trading_service.detectors.base import SignalDetector, SignalResult
from trading_service.detectors.technical import TechnicalSignalDetector

__all__ = [
    "SignalDetector",
    "SignalResult",
    "TechnicalSignalDetector",
]
