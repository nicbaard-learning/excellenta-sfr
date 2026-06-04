"""
Semantic Risk Matching Engine

Translates business language risk queries (e.g. "vendor data leakage", "ransomware")
into SCF risk catalog matches using a multi-strategy pipeline:

    1.  Direct match (ILIKE)
    2.  Synonym expansion
    3.  Token overlap scoring
    4.  Category/grouping matching
    5.  Fallback with closest grouping

No external dependencies — uses Python stdlib only.
"""

from __future__ import annotations

import difflib
import logging
import re
from collections import Counter
from typing import Any

logger = logging.getLogger(__name__)

# ── Risk Synonym Dictionary ──────────────────────────────────────────
# Maps business / natural-language risk terms to SCF risk catalog terms.
# Structure: { business_term: { "grouping": ..., "keywords": [...], "category": ... } }

RISK_SYNONYMS: dict[str, dict[str, Any]] = {
    # ── Access Control ──────────────────────────────────────────────
    "credential theft": {
        "grouping": "Access Control",
        "keywords": ["credential", "authentication", "access", "privilege", "password", "account takeover"],
        "category": "security",
    },
    "credential stuffing": {
        "grouping": "Access Control",
        "keywords": ["credential", "authentication", "access", "brute force", "login"],
        "category": "security",
    },
    "password spraying": {
        "grouping": "Access Control",
        "keywords": ["credential", "authentication", "access", "password", "account"],
        "category": "security",
    },
    "unauthorized access": {
        "grouping": "Access Control",
        "keywords": ["access", "unauthorized", "privilege escalation", "authentication bypass"],
        "category": "security",
    },
    "privilege escalation": {
        "grouping": "Access Control",
        "keywords": ["privilege", "access", "elevation", "authorization", "least privilege"],
        "category": "security",
    },
    "insider threat": {
        "grouping": "Access Control",
        "keywords": ["insider", "internal", "employee", "privilege", "access abuse", "data exfiltration"],
        "category": "security",
    },
    "role based access": {
        "grouping": "Access Control",
        "keywords": ["rbac", "role", "access control", "authorization", "permission", "segregation of duties"],
        "category": "security",
    },
    "segregation of duties": {
        "grouping": "Access Control",
        "keywords": ["segregation", "duties", "sod", "conflict of interest", "separation of duties"],
        "category": "security",
    },
    "identity theft": {
        "grouping": "Access Control",
        "keywords": ["identity", "theft", "fraud", "impersonation", "account"],
        "category": "security",
    },
    "multi factor authentication": {
        "grouping": "Access Control",
        "keywords": ["mfa", "2fa", "authentication", "login security", "multi factor"],
        "category": "security",
    },
    "access control failure": {
        "grouping": "Access Control",
        "keywords": ["access control", "authorization", "permission", "acl", "identity", "accountability"],
        "category": "security",
    },
    "authorization failure": {
        "grouping": "Access Control",
        "keywords": ["authorization", "access", "permission", "rights", "entitlement"],
        "category": "security",
    },
    "session hijacking": {
        "grouping": "Access Control",
        "keywords": ["session", "hijack", "token theft", "authentication bypass", "man in the middle"],
        "category": "security",
    },

    # ── Asset Management ────────────────────────────────────────────
    "cloud misconfiguration": {
        "grouping": "Asset Management",
        "keywords": ["cloud", "misconfiguration", "s3 bucket", "storage", "asset inventory"],
        "category": "security",
    },
    "shadow it": {
        "grouping": "Asset Management",
        "keywords": ["shadow it", "unauthorized asset", "unsanctioned cloud", "inventory gap"],
        "category": "security",
    },
    "asset management failure": {
        "grouping": "Asset Management",
        "keywords": ["asset", "inventory", "hardware", "software", "configuration management", "cmdb"],
        "category": "security",
    },
    "unmanaged devices": {
        "grouping": "Asset Management",
        "keywords": ["unmanaged device", "shadow it", "inventory gap", "byod", "iot"],
        "category": "security",
    },
    "software licensing": {
        "grouping": "Asset Management",
        "keywords": ["license", "software asset", "compliance", "entitlement", "software audit"],
        "category": "compliance",
    },
    "inventory integrity": {
        "grouping": "Asset Management",
        "keywords": ["inventory", "asset register", "discovery", "inaccuracy", "incomplete"],
        "category": "security",
    },

    # ── Business Continuity ─────────────────────────────────────────
    "ransomware": {
        "grouping": "Business Continuity",
        "keywords": ["ransomware", "backup", "recovery", "disaster recovery", "bcdr", "business continuity"],
        "category": "security",
    },
    "denial of service": {
        "grouping": "Business Continuity",
        "keywords": ["dos", "ddos", "availability", "service disruption", "outage"],
        "category": "security",
    },
    "business continuity failure": {
        "grouping": "Business Continuity",
        "keywords": ["bcm", "business continuity", "disaster recovery", "downtime", "availability"],
        "category": "security",
    },
    "supply chain disruption": {
        "grouping": "Business Continuity",
        "keywords": ["supplier", "vendor outage", "third party", "continuity", "disruption"],
        "category": "security",
    },
    "data center outage": {
        "grouping": "Business Continuity",
        "keywords": ["data center", "power outage", "cooling failure", "facility", "downtime"],
        "category": "security",
    },
    "service continuity": {
        "grouping": "Business Continuity",
        "keywords": ["continuity", "bcm", "disaster", "downtime", "availability", "bcdr"],
        "category": "security",
    },

    # ── Data Protection / Exposure ─────────────────────────────────
    "third party data leakage": {
        "grouping": "Exposure",
        "keywords": ["vendor", "third party", "data leakage", "supplier", "data breach", "data exfiltration"],
        "category": "security",
    },
    "data breach": {
        "grouping": "Exposure",
        "keywords": ["breach", "data exposure", "exfiltration", "unauthorized disclosure", "data loss"],
        "category": "security",
    },
    "data exfiltration": {
        "grouping": "Exposure",
        "keywords": ["exfiltration", "data theft", "data loss", "unauthorized transfer", "dataloss"],
        "category": "security",
    },
    "data leakage": {
        "grouping": "Exposure",
        "keywords": ["leakage", "data loss", "exposure", "confidential data", "dlp"],
        "category": "security",
    },
    "sensitive data exposure": {
        "grouping": "Exposure",
        "keywords": ["pii", "personal data", "sensitive", "confidential", "data classification"],
        "category": "privacy",
    },
    "privacy breach": {
        "grouping": "Exposure",
        "keywords": ["privacy", "pii", "gdpr", "personal data", "breach", "data subject"],
        "category": "privacy",
    },
    "intellectual property theft": {
        "grouping": "Exposure",
        "keywords": ["ip theft", "intellectual property", "trade secret", "data theft", "exfiltration"],
        "category": "security",
    },

    # ── Governance ──────────────────────────────────────────────────
    "compliance failure": {
        "grouping": "Governance",
        "keywords": ["compliance", "regulatory", "audit", "noncompliance", "standard", "framework"],
        "category": "compliance",
    },
    "regulatory penalty": {
        "grouping": "Governance",
        "keywords": ["penalty", "regulatory", "fine", "sanction", "enforcement", "noncompliance"],
        "category": "compliance",
    },
    "policy violation": {
        "grouping": "Governance",
        "keywords": ["policy", "violation", "procedure", "standard", "governance"],
        "category": "compliance",
    },
    "audit failure": {
        "grouping": "Governance",
        "keywords": ["audit", "assurance", "compliance", "internal audit", "exceptions"],
        "category": "compliance",
    },
    "risk management failure": {
        "grouping": "Governance",
        "keywords": ["risk", "risk assessment", "risk appetite", "residual risk", "risk register"],
        "category": "governance",
    },
    "third party risk": {
        "grouping": "Governance",
        "keywords": ["third party", "vendor", "supplier", "outsourcing", "tprm", "supplier risk"],
        "category": "compliance",
    },
    "vendor risk": {
        "grouping": "Governance",
        "keywords": ["vendor", "third party", "supplier", "tprm", "due diligence", "outsourcing"],
        "category": "compliance",
    },

    # ── Incident Response ──────────────────────────────────────────
    "phishing": {
        "grouping": "Incident Response",
        "keywords": ["phishing", "social engineering", "email fraud", "spear phishing", "whaling", "smishing"],
        "category": "security",
    },
    "malware": {
        "grouping": "Incident Response",
        "keywords": ["malware", "virus", "trojan", "ransomware", "spyware", "worm"],
        "category": "security",
    },
    "social engineering": {
        "grouping": "Incident Response",
        "keywords": ["social engineering", "phishing", "pretexting", "baiting", "tailgating", "manipulation"],
        "category": "security",
    },
    "incident response failure": {
        "grouping": "Incident Response",
        "keywords": ["incident", "response", "containment", "eradication", "remediation", "soc"],
        "category": "security",
    },
    "security operations": {
        "grouping": "Incident Response",
        "keywords": ["soc", "security operations", "monitoring", "alerting", "siem", "detection"],
        "category": "security",
    },
    "threat detection": {
        "grouping": "Incident Response",
        "keywords": ["detection", "threat", "monitoring", "alert", "siem", "edr"],
        "category": "security",
    },
    "forensic investigation": {
        "grouping": "Incident Response",
        "keywords": ["forensic", "investigation", "evidence", "chain of custody", "breach analysis"],
        "category": "security",
    },

    # ── Situational Awareness ─────────────────────────────────────
    "vulnerability management": {
        "grouping": "Situational Awareness",
        "keywords": ["vulnerability", "patch", "cve", "scanning", "remediation", "patching"],
        "category": "security",
    },
    "threat intelligence": {
        "grouping": "Situational Awareness",
        "keywords": ["threat intel", "cti", "threat intelligence", "ioc", "ttps", "threat actor"],
        "category": "security",
    },
    "patch management": {
        "grouping": "Situational Awareness",
        "keywords": ["patch", "update", "hotfix", "vulnerability", "cve", "bug fix"],
        "category": "security",
    },
    "security awareness": {
        "grouping": "Situational Awareness",
        "keywords": ["awareness", "training", "culture", "education", "phishing simulation", "human factor"],
        "category": "security",
    },
    "penetration testing": {
        "grouping": "Situational Awareness",
        "keywords": ["pentest", "penetration test", "red team", "security testing", "ethical hacking", "offensive"],
        "category": "security",
    },

    # ── Supply Chain ──────────────────────────────────────────────
    "supply chain risk": {
        "grouping": "Supply Chain",
        "keywords": ["supply chain", "supplier", "vendor", "third party", "outsource", "procurement"],
        "category": "compliance",
    },
    "vendor data leakage": {  # Duplicate — maps to both Exposure and Supply Chain
        "grouping": "Supply Chain",
        "keywords": ["vendor", "third party", "data leakage", "supplier", "data breach"],
        "category": "security",
    },
    "software supply chain": {
        "grouping": "Supply Chain",
        "keywords": ["software supply chain", "dependency", "open source", "sbom", "third party code", "log4j"],
        "category": "security",
    },
    "third party breach": {
        "grouping": "Supply Chain",
        "keywords": ["third party breach", "vendor breach", "supplier compromise", "supply chain attack"],
        "category": "security",
    },

    # ── Cross-cutting / general ────────────────────────────────────
    "zero day exploit": {
        "grouping": None,  # Cross-cutting: matches multiple groupings
        "keywords": ["zero day", "0day", "unpatched", "unknown vulnerability", "exploit"],
        "category": "security",
    },
    "api security": {
        "grouping": None,
        "keywords": ["api", "rest", "web service", "endpoint", "api gateway", "owasp"],
        "category": "security",
    },
    "encryption failure": {
        "grouping": None,
        "keywords": ["encryption", "cryptography", "tls", "ssl", "cipher", "key management"],
        "category": "security",
    },
    "logging failure": {
        "grouping": None,
        "keywords": ["logging", "audit trail", "monitoring", "telemetry", "observability"],
        "category": "security",
    },
}


def _tokenize(text: str) -> set[str]:
    """Split text into lowercased tokens, removing punctuation and short words."""
    words = re.findall(r"[a-z]+(?:[_-][a-z]+)*", text.lower())
    return {w for w in words if len(w) > 2}


def _token_overlap(query_tokens: set[str], target_tokens: set[str]) -> float:
    """Compute Jaccard similarity between two token sets."""
    if not query_tokens or not target_tokens:
        return 0.0
    intersection = query_tokens & target_tokens
    union = query_tokens | target_tokens
    return len(intersection) / max(len(union), 1)


class SemanticRiskMatcher:
    """Multi-strategy semantic risk matcher with confidence scoring.

    Pipeline:
        1. Direct match — tries configured synonyms first
        2. Token overlap — scores against all risk catalog entries
        3. Grouping match — falls back to risk grouping categories
        4. Fuzzy fallback — difflib against groupings as last resort
    """

    def __init__(self, session):
        self.session = session
        # Load all risks at class level once
        self._all_risks: list[Any] | None = None
        self._grouping_risks: dict[str, list[Any]] | None = None

    def _get_all_risks(self) -> list[Any]:
        """Lazy-load risks from the database."""
        if self._all_risks is None:
            from app.models.risk import Risk
            self._all_risks = (
                self.session.query(Risk)
                .order_by(Risk.risk_number)
                .all()
            )
        return self._all_risks

    def _get_grouping_risks(self) -> dict[str, list[Any]]:
        """Lazy-load risks grouped by risk_grouping."""
        if self._grouping_risks is None:
            from app.models.risk import Risk
            risks = self._get_all_risks()
            groups: dict[str, list[Any]] = {}
            for r in risks:
                g = r.risk_grouping or "Uncategorized"
                if g not in groups:
                    groups[g] = []
                groups[g].append(r)
            self._grouping_risks = groups
        return self._grouping_risks

    # ── Strategy 1: Synonym Direct Match ────────────────────────────

    def _match_by_synonym(self, query: str) -> list[dict]:
        """Check if the query matches a configured synonym entry."""
        query_lower = query.strip().lower()

        # Check for exact synonym match
        if query_lower in RISK_SYNONYMS:
            synonym = RISK_SYNONYMS[query_lower]
            grouping = synonym["grouping"]
            keywords = synonym["keywords"]
            return self._find_risks_by_grouping_and_keywords(grouping, keywords)

        # Check for partial synonym match (query contains synonym or vice versa)
        for term, synonym in RISK_SYNONYMS.items():
            if term in query_lower or query_lower in term:
                grouping = synonym["grouping"]
                keywords = synonym["keywords"]
                return self._find_risks_by_grouping_and_keywords(grouping, keywords)

        return []

    def _find_risks_by_grouping_and_keywords(
        self, grouping: str | None, keywords: list[str]
    ) -> list[dict]:
        """Find risks matching a grouping and keyword set."""
        from app.models.risk import Risk
        from sqlalchemy import or_

        conditions = []
        if grouping:
            conditions.append(Risk.risk_grouping.ilike(f"%{grouping}%"))

        # Keyword expansion
        for kw in keywords:
            conditions.append(Risk.risk_title.ilike(f"%{kw}%"))
            conditions.append(Risk.risk_description.ilike(f"%{kw}%"))

        risks = (
            self.session.query(Risk)
            .filter(or_(*conditions))
            .order_by(Risk.risk_number)
            .limit(20)
            .all()
        )
        return self._to_result_list(risks, confidence=0.85, method="synonym")

    # ── Strategy 2: Token Overlap Scoring ───────────────────────────

    def _match_by_token_overlap(self, query: str) -> list[dict]:
        """Score all risks by token overlap with the query."""
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        # Expand query with synonyms
        expanded_tokens = set(query_tokens)
        for term, synonym in RISK_SYNONYMS.items():
            term_tokens = _tokenize(term)
            if term_tokens & query_tokens:
                expanded_tokens.update(_tokenize(" ".join(synonym["keywords"])))
                if synonym.get("grouping"):
                    expanded_tokens.update(_tokenize(synonym["grouping"]))

        scored = []
        for risk in self._get_all_risks():
            risk_text = f"{risk.risk_title or ''} {risk.risk_grouping or ''} {risk.risk_description or ''}"
            risk_tokens = _tokenize(risk_text)
            score = _token_overlap(expanded_tokens, risk_tokens)
            if score > 0:
                scored.append((score, risk))

        scored.sort(key=lambda x: -x[0])

        # Return only above threshold
        threshold = 0.05
        results = []
        for score, risk in scored:
            if score < threshold:
                break
            confidence = min(0.95, score * 3)  # Scale up but cap at 0.95
            results.append(self._risk_to_dict(risk, confidence=round(confidence, 2), method="token_overlap"))

        return results[:15]

    # ── Strategy 3: Grouping Match ──────────────────────────────────

    def _match_by_grouping(self, query: str) -> list[dict]:
        """Match query tokens against risk grouping names."""
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        groups = self._get_grouping_risks()
        scored = []

        for group_name, risks_in_group in groups.items():
            group_tokens = _tokenize(group_name)
            score = _token_overlap(query_tokens, group_tokens)

            if score > 0:
                scored.append((score, group_name, risks_in_group))

        scored.sort(key=lambda x: -x[0])

        results = []
        seen_ids = set()
        for score, group_name, risks_in_group in scored:
            for risk in risks_in_group:
                if risk.id not in seen_ids:
                    seen_ids.add(risk.id)
                    confidence = min(0.7, score * 2)
                    results.append(self._risk_to_dict(risk, confidence=round(confidence, 2), method="grouping"))
            if len(results) >= 10:
                break

        return results

    # ── Strategy 4: Fuzzy Fallback ─────────────────────────────────

    def _match_by_fuzzy_fallback(self, query: str) -> list[dict]:
        """Use difflib to find closest risk groupings as last resort."""
        groups = list(self._get_grouping_risks().keys())
        query_lower = query.strip().lower()

        # Find closest matching groupings
        matches = difflib.get_close_matches(query_lower, [g.lower() for g in groups], n=3, cutoff=0.3)
        matched_groups = []
        for g_lower in matches:
            for original in groups:
                if original.lower() == g_lower:
                    matched_groups.append(original)
                    break

        results = []
        seen_ids = set()
        for group_name in matched_groups:
            for risk in self._get_grouping_risks().get(group_name, []):
                if risk.id not in seen_ids:
                    seen_ids.add(risk.id)
                    results.append(self._risk_to_dict(risk, confidence=0.3, method="fuzzy_fallback"))

        return results[:10]

    # ── Main Matching Pipeline ─────────────────────────────────────

    def match(self, query: str) -> dict:
        """Run the full matching pipeline and return results with confidence.

        Args:
            query: Natural language risk query (e.g. "vendor data leakage", "ransomware").

        Returns:
            Dict with matched risks, confidence scores, and metadata.
        """
        if not query or not query.strip():
            return {
                "matched_risks": [],
                "total_matched": 0,
                "confidence": 0,
                "method": "none",
                "interpretation": "No query provided.",
            }

        seen_ids: set[int] = set()
        all_results: list[dict] = []
        best_method = "none"
        best_confidence = 0.0

        # Pipeline: try strategies in order, accumulate results
        pipeline = [
            ("synonym", self._match_by_synonym),
            ("token_overlap", self._match_by_token_overlap),
            ("grouping", self._match_by_grouping),
            ("fuzzy_fallback", self._match_by_fuzzy_fallback),
        ]

        for method_name, strategy_fn in pipeline:
            strategy_results = strategy_fn(query)
            for r in strategy_results:
                if r.get("risk_id") not in seen_ids:
                    seen_ids.add(r["risk_id"])
                    all_results.append(r)
                    if r.get("confidence", 0) > best_confidence:
                        best_confidence = r["confidence"]
                        best_method = r.get("match_method", method_name)

        # Sort by confidence descending
        all_results.sort(key=lambda x: -x.get("confidence", 0))

        # Determine overall confidence tier
        if best_confidence >= 0.8:
            confidence_tier = "HIGH"
            interpretation = f"Strong match found — {best_method} strategy"
        elif best_confidence >= 0.5:
            confidence_tier = "MEDIUM"
            interpretation = f"Moderate match — {best_method} strategy; verify results"
        elif best_confidence >= 0.2:
            confidence_tier = "LOW"
            interpretation = f"Weak match — expanded search via {best_method}; results may need refinement"
        else:
            confidence_tier = "NO_MATCH"
            interpretation = "No direct match found — showing closest available risk categories"

        # Build result
        result = {
            "matched_risks": all_results[:20],
            "total_matched": len(all_results),
            "query": query,
            "confidence": {
                "tier": confidence_tier,
                "score": round(best_confidence, 2),
                "method": best_method,
                "interpretation": interpretation,
            },
        }

        # Add fallback info if confidence is low
        if best_confidence < 0.5:
            result["fallback"] = self._generate_fallback(query, all_results)

        return result

    # ── Fallback Generation ────────────────────────────────────────

    def _generate_fallback(self, query: str, results: list[dict]) -> dict:
        """Generate fallback recommendations when no good match is found."""
        groups = list(self._get_grouping_risks().keys())
        query_tokens = _tokenize(query)

        # Score all groupings
        scored_groups = []
        for g in groups:
            gt = _tokenize(g)
            score = _token_overlap(query_tokens, gt)
            scored_groups.append((score, g))

        scored_groups.sort(key=lambda x: -x[0])

        # If no group scored, return all groups sorted alphabetically
        if not scored_groups or scored_groups[0][0] == 0:
            scored_groups = [(0.01, g) for g in sorted(groups)]

        return {
            "suggestion": "No exact risk match found. Consider reviewing these risk categories:",
            "suggested_groupings": [g for s, g in scored_groups[:5] if s > 0 or len(scored_groups) <= 8],
            "recommendation": "Try a more specific query, or browse the risk catalog by category.",
        }

    # ── Helpers ─────────────────────────────────────────────────────

    def _to_result_list(self, risks: list, confidence: float, method: str) -> list[dict]:
        """Convert a list of risk ORM objects to result dicts."""
        return [self._risk_to_dict(r, confidence, method) for r in risks]

    def _risk_to_dict(self, risk, confidence: float, method: str) -> dict:
        """Convert a risk ORM object to a standardized result dict."""
        return {
            "risk_id": risk.id,
            "risk_number": risk.risk_number or "",
            "grouping": risk.risk_grouping or "",
            "title": risk.risk_title or "",
            "description": risk.risk_description or "",
            "nist_csf_function": risk.nist_csf_function or "",
            "materiality": risk.materiality_considerations or "",
            "confidence": confidence,
            "match_method": method,
        }
