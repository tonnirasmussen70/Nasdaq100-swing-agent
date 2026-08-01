import unittest

import numpy as np
import pandas as pd

from swing_agent import atr, detect_pattern, load_config


class SignalTests(unittest.TestCase):
    def test_bullish_engulfing(self):
        data = pd.DataFrame(
            {"Open": [10.0] * 10 + [10.0, 10.7, 9.7], "High": [10.3] * 10 + [10.4, 10.8, 10.9], "Low": [9.8] * 10 + [9.8, 9.6, 9.5], "Close": [10.1] * 10 + [10.2, 9.8, 10.8], "Volume": [1000] * 13}
        )
        self.assertEqual(detect_pattern(data), ("Bullish engulfing", "Reversal"))

    def test_atr_positive(self):
        idx = pd.RangeIndex(20)
        frame = pd.DataFrame({"High": np.arange(20) + 11.0, "Low": np.arange(20) + 9.0, "Close": np.arange(20) + 10.0}, index=idx)
        self.assertGreater(atr(frame, 14).iloc[-1], 0)

    def test_risk_configuration(self):
        from pathlib import Path

        cfg = load_config(Path(__file__).with_name("config.json"))
        self.assertEqual(cfg["account_value_dkk"], 20000)
        self.assertEqual(cfg["risk_per_trade_pct"], 1.5)
        self.assertEqual(cfg["max_open_positions"], 5)


if __name__ == "__main__":
    unittest.main()
