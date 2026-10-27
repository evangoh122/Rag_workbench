"""Real-code tests for prospectus (S-1 / 424B4) extraction, canonical accessions
and DuckDB vector search.

Nothing here mocks bs4 or the section splitter. (``tests/test_scripts.py``
stubs ``bs4`` in ``sys.modules`` at import time; this file sorts before it and
imports the real modules first, so ``scripts.embed_edgar`` keeps real BeautifulSoup.)
"""
import sys
from unittest.mock import MagicMock, patch

import bs4
import duckdb
import pytest

from api.services import hybrid_retriever
from scripts import embed_edgar
from scripts.embed_edgar import (
    _canonical_accession,
    _ensure_schema,
    _extract_prospectus_sections,
    parse_prospectus_file,
    run_embed_edgar_etl,
)

_REAL_BS4 = bs4


@pytest.fixture(autouse=True)
def _real_bs4(monkeypatch):
    # tests/test_scripts.py replaces sys.modules["bs4"] with a MagicMock when it is
    # collected, which would break bs4's own lazy submodule imports mid-suite.
    monkeypatch.setitem(sys.modules, "bs4", _REAL_BS4)


RISK_TOPICS = [
    ("Competition", "We face intense competition from well-funded companies and the competition may intensify."),
    ("Regulatory", "Regulatory scrutiny of artificial intelligence could impose regulatory compliance costs."),
    ("Cybersecurity", "A cybersecurity incident or data breach could harm our reputation and results."),
    ("Intellectual property", "We may be unable to protect our intellectual property or may face infringement claims."),
]
# A wrapped body line that STARTS with a section word and is short (the old
# "heading + up to 80 chars" matcher took it for a Business heading).
FALSE_HEADING = "business, financial condition, and results of operations could be materially harmed."


def _paragraph(topic: str, sentence: str, n: int) -> str:
    return f"{topic} risk {n}. {sentence} " + ("Our operating history is limited and uncertain. " * 8)


def _risk_body(target_chars: int) -> str:
    parts, n = [], 0
    while sum(len(p) for p in parts) < target_chars:
        topic, sentence = RISK_TOPICS[n % len(RISK_TOPICS)]
        parts.append(_paragraph(topic, sentence, n))
        if n % 25 == 0:
            parts.append(FALSE_HEADING)
        n += 1
    return "\n".join(parts)


def _filler(label: str, n_chars: int) -> str:
    sentence = f"{label} discussion of our operations, customers and strategy. "
    return "\n".join([sentence * 4] * max(1, n_chars // (len(sentence) * 4)))


def _anthropic_style_text(risk_chars: int = 320_000) -> str:
    toc = "\n".join([
        "Prospectus Summary", "Risk Factors", "Use of Proceeds", "Dividend Policy", "Capitalization",
        "Dilution", "Business", "Management",
    ])
    offering = "\n".join([
        "The Offering", "Use of proceeds", "We intend to use the net proceeds for general corporate purposes.",
        "Risk factors", "See Risk Factors for a discussion of risks you should consider.",
    ])
    return "\n".join([
        "Prospectus", toc,
        "Prospectus Summary", offering, _filler("Summary", 3000),
        "Risk Factors", _risk_body(risk_chars),
        "Special Note Regarding Forward-Looking Statements", _filler("Forward-looking", 1000),
        "Use of Proceeds", _filler("Proceeds", 2000),
        "Dividend Policy", _filler("Dividend", 1000),
        "Capitalization", _filler("Capitalization", 1500),
        "Dilution", _filler("Dilution", 1500),
        "Management's Discussion and Analysis of Financial Condition and Results of Operations",
        _filler("MD&A", 4000),
        "Business", _filler("Business", 5000),
        "Management", _filler("Board", 3000),
        "Underwriting", _filler("Underwriting", 2000),
    ])


@pytest.fixture(scope="module")
def anth_sections():
    return dict(_extract_prospectus_sections(_anthropic_style_text()))


def test_risk_factors_not_truncated(anth_sections):
    risk = anth_sections["risk_factors"]
    assert len(risk) > 300_000
    for word in ("competition", "regulatory", "cybersecurity", "intellectual property"):
        assert word in risk.lower()


def test_false_business_heading_stays_inside_risk_factors(anth_sections):
    # Every injected "business, financial condition..." body line is still in Risk Factors,
    # and Business holds none of them (it is the real, later Business section).
    assert anth_sections["risk_factors"].count(FALSE_HEADING) >= 10
    assert FALSE_HEADING not in anth_sections["business"]
    assert anth_sections["business"].startswith("Business")
    assert "Competition risk" not in anth_sections["business"]


def test_sections_are_bounded_by_the_next_main_heading(anth_sections):
    assert list(anth_sections) == [
        "prospectus_summary", "risk_factors", "use_of_proceeds", "capitalization", "dilution",
        "md_and_a", "business",
    ]
    # TOC / "The Offering" rows did not become the Use of Proceeds / Risk Factors body.
    assert "Proceeds discussion" in anth_sections["use_of_proceeds"]
    assert "Dividend discussion" not in anth_sections["use_of_proceeds"]
    assert "Board discussion" not in anth_sections["business"]
    assert "Underwriting discussion" not in anth_sections["business"]
    assert "Forward-looking discussion" not in anth_sections["risk_factors"]


def test_no_headings_falls_back_to_full_text():
    assert _extract_prospectus_sections("just some text without headings") == [
        ("full_text", "just some text without headings")
    ]


def _positioned_html(fragments_per_line):
    """PDF-style SEC HTML: one <div> per visual line, one <font> per fragment."""
    lines = []
    for frags in fragments_per_line:
        fonts = "".join(
            f'<font style="left:{left}pt;width:{width}pt">{word}</font>' for word, left, width in frags
        )
        lines.append(f"<div>{fonts}</div>")
    return "<html><body>" + "".join(lines) + "</body></html>"


def test_font_fragments_are_joined_into_heading_lines(tmp_path):
    body = "Our proceeds will fund research and compute. " * 10
    html = _positioned_html([
        [("Use", 72, 20), ("of", 96, 12), ("Proceeds", 112, 50)],     # visibly apart -> spaces
        [("We", 72, 10), ("intend", 85, 30), ("to", 118, 8)],
        [(body, 72, 400)],
        [("Pro", 72, 15), ("spectus", 87, 40)],                       # touching -> no space
    ])
    f = tmp_path / "primary-document.html"
    f.write_text(html, encoding="utf-8")

    text, raw = parse_prospectus_file(str(f))

    lines = text.split("\n")
    assert "Use of Proceeds" in lines
    assert "Prospectus" in lines
    assert raw == html
    # Never one fragment per line.
    assert "Use" not in lines and "Proceeds" not in lines


def test_plain_text_prospectus_is_used_as_is(tmp_path):
    f = tmp_path / "primary-document.html"
    f.write_text("Table of Contents\nRisk Factors\n  body   text \n", encoding="utf-8")
    text, _ = parse_prospectus_file(str(f))
    assert text == "Risk Factors\nbody text"


@pytest.mark.parametrize("raw", ["0001628280-26-067168", "000162828026067168"])
def test_canonical_accession_is_dashed(raw):
    assert _canonical_accession(raw) == "0001628280-26-067168"


def test_canonical_accession_leaves_unrecognised_values():
    assert _canonical_accession(" weird ") == "weird"


# ── Vector search against a real DuckDB FLOAT[] column ───────────────────────

class _FakeEmbeddings:
    def embed_query(self, _q):
        return [1.0, 0.0, 0.0, 0.0]


@pytest.mark.parametrize("ticker", ["", "ANTH"])
def test_vector_search_real_duckdb_variable_length_column(ticker):
    conn = duckdb.connect(":memory:")
    conn.execute("""
        CREATE TABLE edgar_embeddings (
            ticker VARCHAR, text VARCHAR, accession VARCHAR, section_id VARCHAR,
            chunk_index INTEGER, period_of_report VARCHAR, form_type VARCHAR, embedding FLOAT[]
        )""")
    rows = [
        ("ANTH", "far", "a1", "risk_factors", 0, "2026", "S-1", [0.0, 1.0, 0.0, 0.0]),
        ("ANTH", "near", "a1", "risk_factors", 1, "2026", "S-1", [0.9, 0.1, 0.0, 0.0]),
        ("NVDA", "other-ticker", "n1", "item_1a", 0, "2026", "10-K", [1.0, 0.0, 0.0, 0.0]),
    ]
    conn.executemany("INSERT INTO edgar_embeddings VALUES (?,?,?,?,?,?,?,?)", rows)
    manager = MagicMock()
    manager.get_connection.return_value = conn
    cfg = MagicMock(EMBEDDING_DIM=4)
    with patch.object(hybrid_retriever, "db_manager", manager), \
         patch.object(hybrid_retriever, "Config", cfg), \
         patch.object(hybrid_retriever, "get_embeddings", return_value=_FakeEmbeddings()):
        docs = hybrid_retriever.vector_search("q", top_k=3, ticker=ticker)

    assert docs, "vector search returned nothing (Binder Error swallowed?)"
    texts = [d.page_content for d in docs]
    if ticker:
        assert texts == ["near", "far"]
    else:
        assert texts == ["other-ticker", "near", "far"]
    assert docs[0].metadata["distance"] <= docs[-1].metadata["distance"]


# ── Re-ingest replaces rows whichever accession form wrote them ──────────────

def _run_etl_into(tmp_path, db_path, accession_dir):
    filing = tmp_path / "sec-edgar-filings" / "ANTH" / "S-1" / accession_dir / "primary-document.html"
    filing.parent.mkdir(parents=True)
    filing.write_text("x", encoding="utf-8")
    text = _anthropic_style_text(risk_chars=3000)
    model = MagicMock()
    model.embed_documents.side_effect = lambda texts: [[0.1] * 4 for _ in texts]
    with patch.object(embed_edgar, "DB_PATH", str(db_path)), \
         patch.object(embed_edgar, "_DOWNLOAD_DIR", tmp_path / "dl"), \
         patch.object(embed_edgar, "_get_model", return_value=model), \
         patch.object(embed_edgar, "Config", MagicMock(EMBEDDING_DIM=4)), \
         patch.object(embed_edgar, "_fetch_filing_with_downloader", return_value=(str(filing), "S-1")), \
         patch.object(embed_edgar, "parse_prospectus_file", return_value=(text, "<html/>")):
        return run_embed_edgar_etl(tickers=["ANTH"], batch_size=50)


@pytest.mark.parametrize("old_accession", ["000162828026067168", "0001628280-26-067168"])
def test_reingest_replaces_rows_across_accession_forms(tmp_path, old_accession):
    db_path = tmp_path / "t.duckdb"
    with duckdb.connect(str(db_path)) as conn:
        _ensure_schema(conn)
        conn.execute(
            "INSERT INTO edgar_embeddings (ticker, accession, text, embedding) VALUES "
            "('ANTH', ?, 'STALE', [0.1, 0.1, 0.1, 0.1]::FLOAT[])", [old_accession])
        conn.execute(
            "INSERT INTO edgar_embeddings (ticker, accession, text, embedding) VALUES "
            "('ANTH', '0000000000-00-000001', 'KEEP', [0.1, 0.1, 0.1, 0.1]::FLOAT[])")
        conn.commit()

    stored = _run_etl_into(tmp_path, db_path, "0001628280-26-067168")
    assert stored > 0

    with duckdb.connect(str(db_path)) as conn:
        texts = {r[0] for r in conn.execute("SELECT text FROM edgar_embeddings").fetchall()}
        accs = {r[0] for r in conn.execute(
            "SELECT DISTINCT accession FROM edgar_embeddings WHERE text <> 'KEEP'").fetchall()}
    assert "STALE" not in texts
    assert "KEEP" in texts
    assert accs == {"0001628280-26-067168"}


@pytest.mark.parametrize("other_dim", [3, 4])
def test_ingest_never_deletes_other_tickers_or_dimensions(tmp_path, other_dim):
    db_path = tmp_path / "t.duckdb"
    with duckdb.connect(str(db_path)) as conn:
        _ensure_schema(conn)
        conn.execute(
            "INSERT INTO edgar_embeddings (ticker, accession, text, embedding) VALUES "
            "('NVDA', '0000000000-00-000009', 'OTHER', ?::FLOAT[])", [[0.1] * other_dim])
        conn.commit()

    assert _run_etl_into(tmp_path, db_path, "0001628280-26-067168") > 0

    with duckdb.connect(str(db_path)) as conn:
        nvda = conn.execute(
            "SELECT text, len(embedding) FROM edgar_embeddings WHERE ticker = 'NVDA'").fetchall()
    assert nvda == [("OTHER", other_dim)]


def test_summary_survives_offering_table_rows_when_longer_than_risk_factors():
    text = _anthropic_style_text(risk_chars=12_000).replace(
        _filler("Summary", 3000), _filler("Summary", 20_000))
    sections = dict(_extract_prospectus_sections(text))
    assert "Summary discussion" in sections["prospectus_summary"]
    assert "Summary discussion" not in sections["risk_factors"]
    assert "Competition risk" in sections["risk_factors"]


@pytest.mark.parametrize("title", ["Business", "Business Overview"])
def test_business_heading_variants(title):
    text = _anthropic_style_text(risk_chars=6000).replace("\nBusiness\n", f"\n{title}\n")
    sections = dict(_extract_prospectus_sections(text))
    assert sections["business"].startswith(title)
    assert "Business discussion" in sections["business"]
    assert "Business discussion" not in sections["md_and_a"]
