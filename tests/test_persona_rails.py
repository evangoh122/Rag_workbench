from api.services.guardrails.persona_rails import check_persona_fit
from api.routes.conjoint import role_guidance_for, ROLES


# ── role_guidance_for: tone vs requirements are both present and labelled ──────

def test_role_guidance_splits_tone_and_requirements():
    g = role_guidance_for("compliance_officer")
    assert g is not None
    assert "Tone & emphasis:" in g
    assert "Requirements (the answer must satisfy these):" in g
    # The persona's JTBD context is still there.
    assert "Compliance Officer" in g


def test_role_guidance_omits_requirements_when_blank():
    # Relationship Manager has no hard requirements -> no Requirements clause.
    g = role_guidance_for("relationship_manager")
    assert g is not None
    assert "Tone & emphasis:" in g
    assert "Requirements (the answer must satisfy these):" not in g


def test_role_guidance_unknown_role_is_none():
    assert role_guidance_for(None) is None
    assert role_guidance_for("") is None
    assert role_guidance_for("not_a_role") is None


def test_every_role_has_requirements_field():
    for r in ROLES:
        assert "answer_requirements" in r


# ── Persona-fit rail: skip / fail-open behaviour ──────────────────────────────

def test_fit_unknown_role_skipped():
    v = check_persona_fit(None, "anything")
    assert v.skipped and v.fit
    v = check_persona_fit("not_a_role", "anything")
    assert v.skipped and v.fit


def test_fit_empty_answer_skipped():
    v = check_persona_fit("compliance_officer", "   ")
    assert v.skipped and v.fit


def test_relationship_manager_has_no_requirements_skipped():
    v = check_persona_fit("relationship_manager", "A clean client-ready summary.")
    assert v.skipped and v.fit


# ── Compliance Officer: needs citation + verification ─────────────────────────

def test_compliance_miss_when_no_citation_or_verification():
    v = check_persona_fit("compliance_officer", "Revenue was strong this year.")
    assert not v.fit
    assert "cite source filing / section" in v.missing
    assert "surface verification status" in v.missing


def test_compliance_fit_with_citation_and_verification_status():
    answer = "Per Item 7 (MD&A) of the 10-K, revenue rose."
    v = check_persona_fit("compliance_officer", answer, verification_status="PASS")
    assert v.fit
    assert v.score == 0.0


def test_compliance_fit_with_inline_verification_language():
    answer = "According to the 10-K filing, the figure was verified against the XBRL facts."
    v = check_persona_fit("compliance_officer", answer)
    assert v.fit


# ── Credit Analyst: figure-conditional requirements ───────────────────────────

def test_credit_no_numbers_no_applicable_requirements_skipped():
    # No figures in the answer -> the number-conditional requirements don't apply.
    v = check_persona_fit("credit_analyst", "The borrower's outlook is discussed qualitatively.")
    assert v.skipped and v.fit


def test_credit_unverified_number_without_caveat_misses():
    answer = "Net income was $1,200 million."
    v = check_persona_fit("credit_analyst", answer, verification_status="FAIL")
    assert not v.fit
    assert "caveat any unverified number" in v.missing


def test_credit_verified_number_fits():
    answer = "Per the 10-K, net income was $1,200 million."
    v = check_persona_fit("credit_analyst", answer, verification_status="PASS")
    assert v.fit


def test_credit_caveated_number_fits():
    answer = "Net income was approximately $1,200 million per the 10-K, though unverified."
    v = check_persona_fit("credit_analyst", answer, verification_status="FAIL")
    assert v.fit


# ── Equity Research Analyst: needs a citation ─────────────────────────────────

def test_equity_requires_citation():
    assert not check_persona_fit("equity_research_analyst", "Margins expanded.").fit
    assert check_persona_fit(
        "equity_research_analyst", "Per Item 1A of the 10-K, margins expanded."
    ).fit
