from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CapabilityPattern:
    label: str
    domain: str
    java_service: str
    drivers: tuple[str, ...] = ()
    programs: tuple[str, ...] = ()
    tables_written: tuple[str, ...] = ()
    tables_read: tuple[str, ...] = ()
    tables_any: tuple[str, ...] = ()
    fields: tuple[str, ...] = ()
    copybooks: tuple[str, ...] = ()
    jobs: tuple[str, ...] = ()
    transactions: tuple[str, ...] = ()
    datasets: tuple[str, ...] = ()
    queues: tuple[str, ...] = ()
    paragraphs: tuple[str, ...] = ()
    relationships: tuple[str, ...] = ()
    evidence_boost: float = 0.0


CARD_PATTERNS = (
    CapabilityPattern(
        "Authorization & Decisioning",
        "Card Payments",
        "CardAuthorizationService",
        drivers=("AUTH", "AUTHTRAN", "AUTHDRV"),
        programs=("AUTH", "AUTHVAL", "AUTHCHECK", "LIMIT", "DECISION"),
        tables_read=("CARD_MASTER", "ACCOUNT", "LIMIT", "FRAUD", "VELOCITY"),
        fields=("AUTH", "APPROVE", "DECLINE", "CREDIT_LIMIT", "AVAILABLE", "MCC", "MERCHANT", "PAN"),
        transactions=("AUTH",),
        paragraphs=("AUTHORIZE", "APPROVE", "DECLINE", "LIMIT"),
        relationships=("READS_TABLE", "STARTS_TRANSACTION"),
        evidence_boost=2.0,
    ),
    CapabilityPattern(
        "Posting & Balance Management",
        "Card Account Servicing",
        "CardPostingService",
        drivers=("CRDPOST", "POST", "POSTDRV", "DAILYCRD"),
        programs=("CRDPOST", "BALUPD", "POST", "LEDGER"),
        tables_written=("CARD_MASTER", "ACCOUNT", "BALANCE", "LEDGER"),
        tables_read=("CARD_MASTER", "ACCOUNT"),
        fields=("BAL", "BALANCE", "CURRENT_BALANCE", "AVAILABLE_BALANCE", "ACCT", "ACCOUNT"),
        copybooks=("CARDREC", "ACCTREC"),
        paragraphs=("POST", "BALANCE", "LEDGER", "UPDATE"),
        relationships=("WRITES_TABLE", "WRITES_FILE", "WRITES_DATASET"),
        evidence_boost=2.5,
    ),
    CapabilityPattern(
        "Payment Processing",
        "Card Account Servicing",
        "CardPaymentService",
        drivers=("PAYDRV", "PAYPROC", "PAYMENT"),
        programs=("PAY", "PMT", "REMIT", "AUTOPAY"),
        tables_written=("PAYMENT", "CARD_MASTER", "ACCOUNT", "LEDGER"),
        tables_read=("PAYMENT", "ACH", "ACCOUNT"),
        fields=("PAYMENT", "PMT", "AMOUNT", "DUE", "AUTOPAY", "ACH", "BANK_ACCOUNT"),
        copybooks=("PAYREC",),
        paragraphs=("PAY", "REMIT", "APPLY", "AUTOPAY"),
        relationships=("READS_TABLE", "WRITES_TABLE"),
        evidence_boost=2.0,
    ),
    CapabilityPattern(
        "Statement & Billing",
        "Card Account Servicing",
        "StatementBillingService",
        drivers=("STMTDRV", "STMTGEN", "BILLING"),
        programs=("STMT", "BILL", "CYCLE"),
        tables_written=("STATEMENT", "BILLING", "CYCLE", "CARD_MASTER"),
        tables_read=("TRANSACTION", "PAYMENT", "CARD_MASTER", "INTEREST"),
        fields=("STATEMENT", "STMT", "BILL", "CYCLE", "DUE", "MINPAY", "MINIMUM_PAYMENT"),
        paragraphs=("STATEMENT", "BILL", "CYCLE", "MINIMUM"),
        relationships=("READS_TABLE", "WRITES_TABLE", "WRITES_DATASET"),
        evidence_boost=2.0,
    ),
    CapabilityPattern(
        "Interest & Fee Calculation",
        "Card Account Servicing",
        "InterestFeeService",
        drivers=("INTDRV", "INTCALC", "FEE"),
        programs=("INT", "INTEREST", "APR", "FEE", "RATE"),
        tables_written=("INTEREST", "FEE", "CARD_MASTER", "ACCOUNT"),
        tables_read=("RATE", "APR", "ACCOUNT", "CARD_MASTER"),
        fields=("APR", "RATE", "INTEREST", "FEE", "CHARGE", "FINANCE_CHARGE"),
        paragraphs=("INTEREST", "ACCRUE", "FEE", "CHARGE", "RATE"),
        relationships=("READS_TABLE", "WRITES_TABLE"),
        evidence_boost=1.8,
    ),
    CapabilityPattern(
        "Settlement & Clearing",
        "Card Network Processing",
        "SettlementClearingService",
        drivers=("SETTLE", "CLEAR", "NETWORK"),
        programs=("SETTLE", "CLEAR", "VISA", "MASTERCARD", "NETWORK"),
        tables_written=("SETTLEMENT", "CLEARING", "NETWORK", "INTERCHANGE"),
        tables_read=("TRANSACTION", "MERCHANT", "NETWORK"),
        fields=("SETTLEMENT", "CLEARING", "INTERCHANGE", "MERCHANT", "MCC", "NETWORK"),
        datasets=("VISA", "MASTERCARD", "NETWORK", "SETTLE"),
        paragraphs=("SETTLE", "CLEAR", "INTERCHANGE"),
        relationships=("READS_DATASET", "WRITES_DATASET"),
        evidence_boost=2.0,
    ),
    CapabilityPattern(
        "Dispute & Chargeback",
        "Card Operations",
        "DisputeChargebackService",
        drivers=("DISPUTE", "CHGBK", "CLAIM"),
        programs=("DISPUTE", "DSPT", "CHARGEBACK", "CHGBK", "CLAIM"),
        tables_written=("DISPUTE", "CHARGEBACK", "CLAIM", "CASE"),
        tables_read=("TRANSACTION", "CARD_MASTER", "MERCHANT"),
        fields=("DISPUTE", "CHARGEBACK", "CLAIM", "CASE", "REASON", "REPRESENTMENT"),
        paragraphs=("DISPUTE", "CLAIM", "CHARGEBACK", "REPRESENT"),
        relationships=("READS_TABLE", "WRITES_TABLE"),
        evidence_boost=1.8,
    ),
    CapabilityPattern(
        "Fraud & Risk Controls",
        "Card Risk",
        "FraudRiskService",
        drivers=("FRAUD", "RISK"),
        programs=("FRAUD", "RISK", "SCORE", "VERIFY", "VELOCITY"),
        tables_written=("FRAUD", "RISK", "VELOCITY", "ALERT"),
        tables_read=("TRANSACTION", "CARD_MASTER", "MERCHANT", "DEVICE"),
        fields=("FRAUD", "RISK", "SCORE", "VELOCITY", "BLOCK", "DEVICE", "IP", "MCC"),
        queues=("FRAUD", "RISK", "ALERT"),
        paragraphs=("SCORE", "VERIFY", "BLOCK", "ALERT"),
        relationships=("USES_QUEUE", "READS_TABLE", "WRITES_TABLE"),
        evidence_boost=2.0,
    ),
    CapabilityPattern(
        "Cardholder Account Management",
        "Customer Servicing",
        "CardholderAccountService",
        drivers=("CUST", "CARDHOLDER", "ACCT"),
        programs=("CUST", "CUSTOMER", "CARDHOLDER", "PROFILE", "ADDRESS"),
        tables_written=("CUSTOMER", "CARDHOLDER", "ACCOUNT", "ADDRESS"),
        tables_read=("CUSTOMER", "CARDHOLDER", "ACCOUNT"),
        fields=("CUSTOMER", "CUST", "CARDHOLDER", "PROFILE", "ADDRESS", "PHONE", "EMAIL", "ACCT"),
        copybooks=("CUSTREC", "ACCTREC", "CARDREC"),
        paragraphs=("CUSTOMER", "PROFILE", "ADDRESS", "ACCOUNT"),
        relationships=("READS_TABLE", "WRITES_TABLE"),
        evidence_boost=1.5,
    ),
    CapabilityPattern(
        "Card Issuance & Maintenance",
        "Card Operations",
        "CardMaintenanceService",
        drivers=("ISSUE", "CARDMNT", "EMBOSS"),
        programs=("ISSUE", "ISSUANCE", "EMBOSS", "PIN", "REPLACE", "CARDMNT"),
        tables_written=("CARD", "PLASTIC", "PIN", "CARD_MASTER"),
        tables_read=("CUSTOMER", "ACCOUNT", "PRODUCT"),
        fields=("ISSUE", "EMBOSS", "PIN", "REPLACE", "EXPIRY", "PLASTIC", "PAN"),
        paragraphs=("ISSUE", "EMBOSS", "REPLACE", "PIN"),
        relationships=("READS_TABLE", "WRITES_TABLE", "WRITES_DATASET"),
        evidence_boost=1.7,
    ),
    CapabilityPattern(
        "Rewards & Loyalty",
        "Card Value Added Services",
        "RewardsLoyaltyService",
        drivers=("REWARD", "LOYALTY"),
        programs=("REWARD", "LOYALTY", "POINT", "CASHBACK", "MILES"),
        tables_written=("REWARD", "POINT", "LOYALTY", "CASHBACK"),
        tables_read=("TRANSACTION", "CARD_MASTER", "MERCHANT"),
        fields=("REWARD", "POINT", "LOYALTY", "CASHBACK", "MILES", "EARN", "REDEEM"),
        paragraphs=("EARN", "REDEEM", "REWARD", "POINT"),
        relationships=("READS_TABLE", "WRITES_TABLE"),
        evidence_boost=1.7,
    ),
    CapabilityPattern(
        "Collections & Delinquency",
        "Card Collections",
        "CollectionsService",
        drivers=("COLL", "DELINQ", "DELQ"),
        programs=("COLL", "COLLECT", "DELINQ", "DELQ", "DUNNING"),
        tables_written=("COLLECTION", "DELINQUENCY", "DUNNING", "ACCOUNT"),
        tables_read=("CARD_MASTER", "PAYMENT", "STATEMENT", "ACCOUNT"),
        fields=("COLLECT", "DELINQ", "DELQ", "PASTDUE", "DUNNING", "PROMISE_TO_PAY"),
        paragraphs=("COLLECT", "DELINQ", "DUNNING", "PAST-DUE"),
        relationships=("READS_TABLE", "WRITES_TABLE"),
        evidence_boost=1.7,
    ),
    CapabilityPattern(
        "Debit Card Access & ATM/POS Processing",
        "Debit Card Processing",
        "DebitCardAccessService",
        drivers=("DEBIT", "ATM", "POS"),
        programs=("DEBIT", "ATM", "POS", "PIN", "DDA"),
        tables_written=("DDA", "CHECKING", "DEBIT", "ATM", "POS"),
        tables_read=("DDA", "CHECKING", "BALANCE", "PIN"),
        fields=("DEBIT", "ATM", "POS", "PIN", "DDA", "CHECKING", "OVERDRAFT"),
        paragraphs=("PIN", "ATM", "POS", "DEBIT"),
        relationships=("READS_TABLE", "WRITES_TABLE"),
        evidence_boost=2.0,
    ),
)

PRODUCT_SIGNALS = (
    ("Debit Card", ("DEBIT", "ATM", "POS", "DDA", "CHECKING")),
    ("Credit Card", ("CREDIT", "APR", "STATEMENT", "BILL", "MINPAY", "REVOLVE")),
    ("Card", ("CARD", "CRD", "PAN", "PLASTIC")),
)

GENERIC_ACTIONS = (
    ("Authorization", ("AUTH", "APPROVE", "DECLINE", "LIMIT")),
    ("Posting", ("POST", "LEDGER", "JOURNAL")),
    ("Payment", ("PAY", "PMT", "REMIT")),
    ("Statement", ("STMT", "STATEMENT", "BILL")),
    ("Interest", ("INT", "INTEREST", "APR", "RATE")),
    ("Customer", ("CUST", "CUSTOMER", "CARDHOLDER")),
    ("Account", ("ACCT", "ACCOUNT")),
)


def name_card_capability(
    assets: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
) -> dict[str, Any]:
    profile = build_codebase_profile(assets, relationships)
    candidates = [_score_pattern(pattern, profile) for pattern in CARD_PATTERNS]
    candidates = [candidate for candidate in candidates if candidate["score"] > 0]
    candidates.sort(key=lambda item: (-item["score"], item["label"]))
    product = _product_context(profile)
    if not candidates:
        fallback = _derive_generic_name(profile, product)
        return {
            "name": fallback["name"],
            "domain": fallback["domain"],
            "java_service": fallback["java_service"],
            "confidence": fallback["confidence"],
            "validation_status": "needs_review",
            "matched_signals": fallback["matched_signals"],
            "candidate_capabilities": [],
            "naming_method": "codebase_profile_no_taxonomy_match",
            "codebase_profile": profile,
        }

    winner = candidates[0]
    second = candidates[1]["score"] if len(candidates) > 1 else 0.0
    margin = winner["score"] - second
    evidence_kinds = len({signal["kind"] for signal in winner["matched_signals"]})
    confidence = min(0.96, 0.45 + winner["score"] / 38.0 + min(margin, 10.0) / 55.0)
    confidence += min(evidence_kinds, 5) * 0.025
    confidence = min(confidence, 0.97)
    if margin < 2.0 and len(candidates) > 1:
        confidence = min(confidence, 0.74)
    name = _compose_name(product, winner["label"])
    return {
        "name": name,
        "domain": winner["domain"],
        "java_service": winner["java_service"],
        "confidence": round(confidence, 3),
        "validation_status": "inferred" if confidence >= 0.65 else "needs_review",
        "matched_signals": winner["matched_signals"],
        "candidate_capabilities": candidates[:5],
        "naming_method": "codebase_profile_plus_card_domain_ontology",
        "codebase_profile": profile,
    }


def build_codebase_profile(
    assets: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
) -> dict[str, Any]:
    profile: dict[str, set[str] | dict[str, int]] = {
        "drivers": set(),
        "programs": set(),
        "jobs": set(),
        "transactions": set(),
        "tables_read": set(),
        "tables_written": set(),
        "tables_any": set(),
        "datasets": set(),
        "copybooks": set(),
        "queues": set(),
        "maps": set(),
        "fields": set(),
        "paragraphs": set(),
        "relationship_types": set(),
        "asset_types": set(),
        "terms": set(),
        "crud_counts": {},
    }
    incoming_call_targets = {
        str(rel.get("target") or rel.get("target_asset_id") or "")
        for rel in relationships
        if _rel_type(rel) in {"CALLS", "DYNAMIC_CALL"}
    }
    entry_targets = {
        str(rel.get("target") or rel.get("target_asset_id") or "")
        for rel in relationships
        if _rel_type(rel) in {"EXECUTES", "STARTS_PROGRAM", "STARTS_TRANSACTION", "TRIGGERS"}
    }
    for asset in assets[:1000]:
        asset_type = str(asset.get("asset_type") or asset.get("type") or "").upper()
        name = _clean(asset.get("technical_name") or asset.get("label") or asset.get("display_name") or "")
        asset_id = str(asset.get("asset_id") or asset.get("id") or "")
        if not name:
            continue
        _add(profile, "asset_types", asset_type)
        _add(profile, "terms", name)
        _add(profile, "terms", asset.get("folder_path"))
        _add(profile, "terms", asset.get("relative_path"))
        if asset_type == "PROGRAM":
            _add(profile, "programs", name)
            if asset_id in entry_targets or asset_id not in incoming_call_targets:
                _add(profile, "drivers", name)
        elif asset_type == "JOB":
            _add(profile, "jobs", name)
        elif asset_type == "TRANSACTION":
            _add(profile, "transactions", name)
        elif asset_type == "COPYBOOK":
            _add(profile, "copybooks", name)
        elif asset_type in {"TABLE", "DB2_TABLE", "IMS_SEGMENT"}:
            _add(profile, "tables_any", name)
        elif asset_type in {"DATASET", "FILE"}:
            _add(profile, "datasets", name)
        elif asset_type == "MQ_QUEUE":
            _add(profile, "queues", name)
        elif asset_type == "MAP":
            _add(profile, "maps", name)
        attributes = asset.get("attributes") or {}
        ast = attributes.get("ast_summary") or {}
        for paragraph in ast.get("paragraphs", [])[:250]:
            _add(profile, "paragraphs", paragraph)
            _add(profile, "terms", paragraph)
        tree = attributes.get("ast_tree") or {}
        _collect_tree_terms(tree, profile)
    for rel in relationships[:3000]:
        rel_type = _rel_type(rel)
        source = _clean(rel.get("source_name") or "")
        target = _clean(rel.get("target_name") or "")
        target_type = str(rel.get("target_type") or "").upper()
        _add(profile, "relationship_types", rel_type)
        _add(profile, "terms", source)
        _add(profile, "terms", target)
        if rel_type in {"READS_TABLE"} or (rel_type == "READS" and target_type in {"TABLE", "DB2_TABLE"}):
            _add(profile, "tables_read", target)
            _add(profile, "tables_any", target)
            _inc(profile, "crud_counts", "read")
        elif rel_type in {"WRITES_TABLE"} or (rel_type == "WRITES" and target_type in {"TABLE", "DB2_TABLE"}):
            _add(profile, "tables_written", target)
            _add(profile, "tables_any", target)
            _inc(profile, "crud_counts", "write")
        elif rel_type in {"READS_DATASET", "WRITES_DATASET", "READS_FILE", "WRITES_FILE"}:
            _add(profile, "datasets", target)
        elif rel_type == "USES_COPYBOOK":
            _add(profile, "copybooks", target)
        elif rel_type == "USES_QUEUE":
            _add(profile, "queues", target)
        elif rel_type == "USES_MAP":
            _add(profile, "maps", target)
        elif rel_type in {"STARTS_TRANSACTION", "TRIGGERS"}:
            _add(profile, "transactions", target)
    return {
        key: dict(value) if isinstance(value, dict) else sorted(value)
        for key, value in profile.items()
    }


def _score_pattern(pattern: CapabilityPattern, profile: dict[str, Any]) -> dict[str, Any]:
    matched = []
    score = pattern.evidence_boost
    score += _match_group(matched, "driver_program", profile["drivers"], pattern.drivers, 5.0)
    score += _match_group(matched, "program", profile["programs"], pattern.programs, 3.5)
    score += _match_group(matched, "table_written", profile["tables_written"], pattern.tables_written, 5.5)
    score += _match_group(matched, "table_read", profile["tables_read"], pattern.tables_read, 3.0)
    score += _match_group(matched, "table", profile["tables_any"], pattern.tables_any, 2.2)
    score += _match_group(matched, "field_or_data_item", profile["fields"], pattern.fields, 2.6)
    score += _match_group(matched, "copybook", profile["copybooks"], pattern.copybooks, 2.0)
    score += _match_group(matched, "job", profile["jobs"], pattern.jobs, 2.2)
    score += _match_group(matched, "transaction", profile["transactions"], pattern.transactions, 3.0)
    score += _match_group(matched, "dataset", profile["datasets"], pattern.datasets, 2.0)
    score += _match_group(matched, "queue", profile["queues"], pattern.queues, 2.0)
    score += _match_group(matched, "paragraph", profile["paragraphs"], pattern.paragraphs, 1.8)
    score += _match_group(matched, "relationship", profile["relationship_types"], pattern.relationships, 1.3)
    crud = profile.get("crud_counts", {})
    if pattern.tables_written and int(crud.get("write", 0)) > 0:
        score += 2.0
        matched.append({"kind": "crud_behavior", "value": "write-path", "matched": "WRITES"})
    return {
        "label": pattern.label,
        "domain": pattern.domain,
        "java_service": pattern.java_service,
        "score": round(score, 3),
        "matched_signals": matched,
    }


def _match_group(
    matched: list[dict[str, str]],
    kind: str,
    observed: list[str],
    expected: tuple[str, ...],
    weight: float,
) -> float:
    total = 0.0
    for token in expected:
        hits = [value for value in observed if _contains_term(value, token)]
        if hits:
            hit = hits[0]
            matched.append({"kind": kind, "value": hit, "matched": token})
            total += weight
    return total


def _derive_generic_name(profile: dict[str, Any], product: str) -> dict[str, Any]:
    terms = " ".join(profile.get("terms", [])).upper()
    actions = [label for label, tokens in GENERIC_ACTIONS if any(_contains_term(terms, token) for token in tokens)]
    subject = product or ("Card" if any(_contains_term(terms, token) for token in ("CARD", "CRD", "PAN")) else "")
    if actions and subject:
        name = f"{subject} {' & '.join(actions[:2])}"
        java = "".join(part for part in re.sub(r"[^A-Za-z0-9 ]", " ", name).title().split()) + "Service"
        return {
            "name": name,
            "domain": "Card Processing" if subject else "Legacy Application",
            "java_service": java,
            "confidence": 0.45,
            "matched_signals": actions[:2],
        }
    return {
        "name": "Needs Review",
        "domain": "Unknown",
        "java_service": "NeedsReviewService",
        "confidence": 0.25,
        "matched_signals": [],
    }


def _compose_name(product: str, label: str) -> str:
    if not product:
        product = "Card"
    if label.startswith(product) or label.startswith("Cardholder"):
        return label
    return f"{product} {label}"


def _product_context(profile: dict[str, Any]) -> str:
    terms = " ".join(profile.get("terms", [])).upper()
    for label, tokens in PRODUCT_SIGNALS:
        if any(_contains_term(terms, token) for token in tokens):
            return label
    return ""


def _collect_tree_terms(node: dict[str, Any], profile: dict[str, Any]) -> None:
    if not isinstance(node, dict):
        return
    node_type = str(node.get("type") or "").lower()
    label = node.get("label")
    if node_type in {"data_item", "field"}:
        _add(profile, "fields", label)
    elif node_type == "paragraph":
        _add(profile, "paragraphs", label)
    _add(profile, "terms", label)
    for child in node.get("children", [])[:300]:
        _collect_tree_terms(child, profile)


def _rel_type(rel: dict[str, Any]) -> str:
    return str(rel.get("type") or rel.get("relationship_type") or "").upper()


def _add(profile: dict[str, Any], key: str, value: Any) -> None:
    clean = _clean(value)
    if clean:
        profile[key].add(clean)


def _inc(profile: dict[str, Any], key: str, value: str) -> None:
    bucket = profile[key]
    bucket[value] = int(bucket.get(value, 0)) + 1


def _clean(value: Any) -> str:
    return str(value or "").strip().strip("'\"()[],.").upper()


def _contains_term(value: str, token: str) -> bool:
    text = _clean(value)
    term = _clean(token)
    if not text or not term:
        return False
    escaped = re.escape(term)
    if re.search(rf"(?<![A-Z0-9]){escaped}(?![A-Z0-9])", text):
        return True
    if term in {"CARD", "CRD", "AUTH", "PAY", "PMT", "STMT", "BAL", "ACCT", "CUST", "INT"}:
        return term in text
    return False
