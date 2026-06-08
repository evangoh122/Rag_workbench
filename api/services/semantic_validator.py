import logging
import statistics
from typing import Optional

from api.models.eval_types import ExtractionResult, ValidationResult, ReasonCode
from api.services.companyfacts_client import CompanyFactsClient

logger = logging.getLogger(__name__)

IDENTITY_TOLERANCE = 0.01      # 1% tolerance for accounting identity checks
PLAUSIBILITY_STD_DEVS = 3.0   # flag if z-score > 3 from company historical mean
MIN_HISTORY_POINTS = 3         # minimum data points needed for plausibility check


class SemanticValidator:
    """Layer-2 semantic validation: accounting identities, referential integrity, plausibility."""

    def __init__(self, client: CompanyFactsClient = None):
        self.client = client or CompanyFactsClient()

    def validate(self, result: ExtractionResult, validation_state: ValidationResult) -> None:
        """Validates semantic correctness of result; modifies validation_state in-place."""
        self._check_accounting_identities(result, validation_state)
        self._check_referential_integrity(result, validation_state)
        self._check_plausibility(result, validation_state)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_numeric(self, result: ExtractionResult, *names: str) -> Optional[float]:
        """Returns the first numeric field value whose name OR concept matches any of the given names."""
        for name in names:
            field = next(
                (f for f in result.fields if f.name == name or f.concept == name), None
            )
            if field is not None and field.value is not None:
                try:
                    return float(field.value)
                except (ValueError, TypeError):
                    continue
        return None

    def _flag_invalid(self, vs: ValidationResult, code: ReasonCode) -> None:
        if code not in vs.reason_codes:
            vs.reason_codes.append(code)
        vs.is_valid = False

    # ------------------------------------------------------------------
    # Check 1: Accounting identities (REQ-SEM-01, REQ-SEM-04)
    # ------------------------------------------------------------------

    def _check_accounting_identities(
        self, result: ExtractionResult, vs: ValidationResult
    ) -> None:
        violations = []

        # Balance sheet: Assets ≈ Liabilities + StockholdersEquity
        assets = self._get_numeric(result, "Assets")
        liabilities = self._get_numeric(result, "Liabilities")
        equity = self._get_numeric(
            result, "StockholdersEquity", "StockholdersEquityNetOfTreasuryStock"
        )

        if assets is not None and liabilities is not None and equity is not None:
            expected = liabilities + equity
            if abs(expected) > 0:
                diff_pct = abs(assets - expected) / abs(expected)
                if diff_pct > IDENTITY_TOLERANCE:
                    violations.append({
                        "check": "balance_sheet",
                        "assets": assets,
                        "liabilities_plus_equity": expected,
                        "diff_pct": round(diff_pct, 6),
                    })

        # Income: GrossProfit ≈ Revenues − CostOfRevenue
        gross_profit = self._get_numeric(result, "GrossProfit")
        revenues = self._get_numeric(
            result,
            "Revenue",
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
        )
        cogs = self._get_numeric(result, "CostOfRevenue", "CostOfGoodsAndServicesSold")

        if gross_profit is not None and revenues is not None and cogs is not None:
            expected_gp = revenues - cogs
            if abs(expected_gp) > 0:
                diff_pct = abs(gross_profit - expected_gp) / abs(expected_gp)
                if diff_pct > IDENTITY_TOLERANCE:
                    violations.append({
                        "check": "gross_profit",
                        "gross_profit": gross_profit,
                        "revenues_minus_cogs": expected_gp,
                        "diff_pct": round(diff_pct, 6),
                    })

        if violations:
            self._flag_invalid(vs, ReasonCode.IDENTITY_VIOLATION)
            vs.details["identity_violations"] = violations

    # ------------------------------------------------------------------
    # Check 2: Referential integrity (REQ-SEM-02)
    # ------------------------------------------------------------------

    def _check_referential_integrity(
        self, result: ExtractionResult, vs: ValidationResult
    ) -> None:
        name_field = next(
            (
                f
                for f in result.fields
                if f.name in ("EntityRegistrantName", "CompanyName", "company_name")
            ),
            None,
        )
        if name_field is None or name_field.value is None:
            return

        try:
            company = self.client._get_company_object(result.cik)
            if not (company and hasattr(company, "name") and company.name):
                return

            extracted = str(name_field.value).lower().strip()
            canonical = str(company.name).lower().strip()

            # Accept substring match to handle common truncation/formatting differences
            if extracted not in canonical and canonical not in extracted:
                self._flag_invalid(vs, ReasonCode.REFERENTIAL)
                violations = vs.details.setdefault("referential_violations", [])
                violations.append({
                    "check": "cik_company_name",
                    "extracted": name_field.value,
                    "canonical": company.name,
                })
        except Exception as e:
            logger.warning(
                "Referential integrity check failed for CIK %s: %s", result.cik, e
            )

    # ------------------------------------------------------------------
    # Check 3: Plausibility vs company history (REQ-SEM-03)
    # ------------------------------------------------------------------

    def _check_plausibility(
        self, result: ExtractionResult, vs: ValidationResult
    ) -> None:
        violations = []

        for f in result.fields:
            if f.concept is None or f.value is None:
                continue
            if f.concept not in CompanyFactsClient.HIGH_SIGNAL_CONCEPTS:
                continue

            try:
                current_val = float(f.value)
            except (ValueError, TypeError):
                continue

            try:
                historical = self.client.get_historical_values(result.cik, f.concept)
            except Exception as e:
                logger.warning(
                    "Could not fetch historical values for %s/%s: %s",
                    result.cik,
                    f.concept,
                    e,
                )
                continue

            if len(historical) < MIN_HISTORY_POINTS:
                continue

            mean = statistics.mean(historical)
            try:
                stdev = statistics.stdev(historical)
            except statistics.StatisticsError:
                continue

            if stdev == 0:
                continue

            z_score = abs(current_val - mean) / stdev
            if z_score > PLAUSIBILITY_STD_DEVS:
                logger.warning(
                    "Plausibility violation: %s %s z=%.2f (mean=%.2f, stdev=%.2f, value=%.2f)",
                    f.name,
                    f.concept,
                    z_score,
                    mean,
                    stdev,
                    current_val,
                )
                violations.append({
                    "field": f.name,
                    "concept": f.concept,
                    "value": current_val,
                    "mean": round(mean, 2),
                    "stdev": round(stdev, 2),
                    "z_score": round(z_score, 2),
                })
                self._flag_invalid(vs, ReasonCode.OUT_OF_RANGE)

        if violations:
            vs.details["plausibility_violations"] = violations
