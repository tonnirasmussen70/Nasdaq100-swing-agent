import unittest
import numpy as np
import pandas as pd
from other_strategies import indicators, screen


class OtherStrategiesTests(unittest.TestCase):
    def setUp(self):
        n = 120
        close = np.linspace(12, 10, n) + np.sin(np.arange(n) / 7) * .3
        self.data = pd.DataFrame({
            "Open": close - .05, "High": close + .2,
            "Low": close - .2, "Close": close, "Volume": np.full(n, 100000),
        }, index=pd.bdate_range("2026-01-01", periods=n))

    def test_indicators(self):
        d = indicators(self.data)
        self.assertTrue(np.isfinite(d.iloc[-1][["RSI14", "MA20", "MA50", "ATR14", "MACD"]].to_numpy(dtype=float)).all())

    def test_watchlist_status_and_risk(self):
        r = screen(self.data)
        self.assertIn(r["status"], ("WAIT", "BUY"))
        self.assertGreater(r["entry"], r["stop"])
        self.assertGreater(r["target"], r["entry"])
        self.assertEqual(r["reward_risk"], 2.0)

    def test_owned_status(self):
        r = screen(self.data, has_position=True)
        self.assertIn(r["status"], ("HOLD", "SELL"))

    def test_insufficient_history(self):
        with self.assertRaises(ValueError):
            screen(self.data.head(20))


if __name__ == "__main__":
    unittest.main()
