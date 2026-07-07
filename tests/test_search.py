from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from economics_daily.search import search_queries, tavily_search


class SearchTest(unittest.TestCase):
    def test_tavily_search_without_api_key_returns_empty(self) -> None:
        with patch.dict(os.environ, {"TAVILY_API_KEY": ""}, clear=False):
            self.assertEqual(tavily_search("test query"), [])

    @patch("economics_daily.search.requests.post")
    def test_tavily_search_parses_results(self, post_mock) -> None:
        post_mock.return_value.json.return_value = {
            "results": [
                {"title": "WMO update", "url": "https://wmo.int", "content": "El Niño warning"},
            ]
        }
        post_mock.return_value.raise_for_status.return_value = None
        with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}, clear=False):
            results = tavily_search("WMO El Niño warning")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "WMO update")
        self.assertEqual(results[0]["snippet"], "El Niño warning")
        post_mock.assert_called_once()

    @patch("economics_daily.search.tavily_search")
    def test_search_queries_respects_limit(self, search_mock) -> None:
        search_mock.return_value = [{"title": "a", "url": "u", "snippet": "s"}]
        with patch.dict(os.environ, {"SEARCH_MAX_QUERIES": "2"}, clear=False):
            evidence = search_queries(["q1", "q2", "q3"])

        self.assertEqual(len(evidence), 2)
        self.assertEqual(evidence[0]["query"], "q1")
        self.assertEqual(evidence[1]["query"], "q2")


if __name__ == "__main__":
    unittest.main()
