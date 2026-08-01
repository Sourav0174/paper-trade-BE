"""
Unit tests for app/stocks/service.py price fetching and DataFrame normalization.

Tests:
1. Single symbol batch download MultiIndex normalization
2. Multiple symbol batch download MultiIndex normalization
3. Layout agnostic extraction for single and multiple symbols
"""

import unittest
from unittest.mock import patch
import pandas as pd

from app.stocks.service import extract_ticker_dataframe, fetch_multiple_prices


class TestStocksService(unittest.TestCase):

    def test_extract_ticker_dataframe_single_symbol_multiindex(self):
        """Test normalization for single-symbol MultiIndex dataframe layout [('ACC.NS', 'Close')]."""
        columns = pd.MultiIndex.from_tuples([
            ("ACC.NS", "Open"),
            ("ACC.NS", "High"),
            ("ACC.NS", "Low"),
            ("ACC.NS", "Close"),
        ])
        raw_df = pd.DataFrame([
            [100.0, 110.0, 95.0, 105.0],
            [105.0, 115.0, 100.0, 112.0],
        ], columns=columns)

        extracted = extract_ticker_dataframe(raw_df, "ACC")
        self.assertFalse(extracted.empty)
        self.assertIn("Close", extracted.columns)
        self.assertEqual(float(extracted["Close"].iloc[-1]), 112.0)

    def test_extract_ticker_dataframe_multi_symbol_multiindex(self):
        """Test normalization for multi-symbol MultiIndex dataframe layout."""
        columns = pd.MultiIndex.from_tuples([
            ("RELIANCE.NS", "Close"),
            ("TCS.NS", "Close"),
        ])
        raw_df = pd.DataFrame([
            [2500.0, 3500.0],
            [2550.0, 3600.0],
        ], columns=columns)

        rel_df = extract_ticker_dataframe(raw_df, "RELIANCE")
        tcs_df = extract_ticker_dataframe(raw_df, "TCS")

        self.assertIn("Close", rel_df.columns)
        self.assertIn("Close", tcs_df.columns)
        self.assertEqual(float(rel_df["Close"].iloc[-1]), 2550.0)
        self.assertEqual(float(tcs_df["Close"].iloc[-1]), 3600.0)

    @patch("app.stocks.service.yf.download")
    def test_fetch_multiple_prices_single_symbol_mock(self, mock_download):
        """Test fetch_multiple_prices correctly processes single-symbol downloads."""
        columns = pd.MultiIndex.from_tuples([
            ("ACC.NS", "Open"),
            ("ACC.NS", "Close"),
        ])
        mock_df = pd.DataFrame([
            [100.0, 100.0],
            [105.0, 110.0],
        ], columns=columns)
        mock_download.return_value = mock_df

        prices = fetch_multiple_prices(["ACC"])

        self.assertIn("ACC", prices)
        curr, change_val, change_pct = prices["ACC"]
        self.assertEqual(curr, 110.0)
        self.assertEqual(change_val, 10.0)
        self.assertEqual(change_pct, 10.0)

    @patch("app.stocks.service.yf.download")
    def test_fetch_multiple_prices_multi_symbol_mock(self, mock_download):
        """Test fetch_multiple_prices correctly processes multi-symbol downloads."""
        columns = pd.MultiIndex.from_tuples([
            ("RELIANCE.NS", "Close"),
            ("TCS.NS", "Close"),
        ])
        mock_df = pd.DataFrame([
            [2000.0, 3000.0],
            [2100.0, 3150.0],
        ], columns=columns)
        mock_download.return_value = mock_df

        prices = fetch_multiple_prices(["RELIANCE", "TCS"])

        self.assertEqual(prices["RELIANCE"][0], 2100.0)
        self.assertEqual(prices["RELIANCE"][1], 100.0)
        self.assertEqual(prices["TCS"][0], 3150.0)
        self.assertEqual(prices["TCS"][1], 150.0)


if __name__ == "__main__":
    unittest.main()
