"""tests/test_graph_route.py — Phase C: Evidence-Graph route."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from api.routes import graph


class TestParseChunkId:
    def test_basic(self):
        assert graph._parse_chunk_id("NVDA:000104581024000029:3") == \
            ("NVDA", "000104581024000029", 3)

    def test_accession_with_dashes(self):
        assert graph._parse_chunk_id("MU:0001045810-24-000029:0") == \
            ("MU", "0001045810-24-000029", 0)

    def test_unknown_index(self):
        assert graph._parse_chunk_id("MU:acc:-") == ("MU", "acc", None)

    def test_rejects_too_few_parts(self):
        with pytest.raises(ValueError):
            graph._parse_chunk_id("NVDA:acc")

    def test_rejects_non_integer_index(self):
        with pytest.raises(ValueError):
            graph._parse_chunk_id("NVDA:acc:notanint")

    def test_rejects_empty_ticker(self):
        with pytest.raises(ValueError):
            graph._parse_chunk_id(":acc:0")


class TestEvidenceEndpoint:
    def test_bad_chunk_id_returns_400(self):
        with pytest.raises(HTTPException) as ei:
            graph.evidence("bad")
        assert ei.value.status_code == 400

    def test_not_found_returns_404(self):
        cur = MagicMock()
        cur.fetchone.return_value = None
        with patch.object(graph.db_manager, "execute", return_value=cur):
            with pytest.raises(HTTPException) as ei:
                graph.evidence("NVDA:acc:0")
        assert ei.value.status_code == 404

    def test_happy_path_returns_excerpt(self):
        cur = MagicMock()
        cur.fetchone.return_value = (
            "NVIDIA operates a Data Center segment.", "NVDA", "acc1",
            "item_1", "10-K", "2024-01-28",
        )
        with patch.object(graph.db_manager, "execute", return_value=cur) as ex:
            out = graph.evidence("NVDA:acc1:0")
        # chunk_index present → query includes the AND chunk_index = ? clause
        assert "chunk_index = ?" in ex.call_args[0][0]
        assert out["excerpt"].startswith("NVIDIA operates")
        assert out["ticker"] == "NVDA"
        assert out["section_id"] == "item_1"
        assert out["form_type"] == "10-K"
        assert "sec.gov" in out["edgar_url"]

    def test_unknown_index_omits_chunk_filter(self):
        cur = MagicMock()
        cur.fetchone.return_value = ("text", "MU", "acc", "", "", "")
        with patch.object(graph.db_manager, "execute", return_value=cur) as ex:
            graph.evidence("MU:acc:-")
        assert "chunk_index = ?" not in ex.call_args[0][0]
