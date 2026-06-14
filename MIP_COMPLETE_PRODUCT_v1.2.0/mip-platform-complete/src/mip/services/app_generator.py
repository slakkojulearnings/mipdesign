from __future__ import annotations

import re
from pathlib import Path
from textwrap import dedent
from typing import Any

from mip.persistence import SQLiteRepository
from mip.services.brd import BRDGenerator
from mip.services.capability import CapabilityDiscoveryService


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or "generated_capability"


class ApplicationSkeletonGenerator:
    """Generate separated Python and Java function skeletons for a capability."""

    def __init__(self, repository: SQLiteRepository, run_id: str | None = None) -> None:
        self.repository = repository
        self.run_id = run_id or repository.latest_run_id()

    def generate_capability_app(
        self,
        capability: str,
        output_root: Path,
        *,
        card_domain: bool = False,
    ) -> dict[str, Any]:
        slug = slugify(capability)
        base = output_root / slug
        python_dir = base / "python_functions"
        java_root = base / "java_functions" / "src" / "main" / "java" / "com" / "mip" / "generated"
        java_dir = java_root / slug
        test_dir = (
            base / "java_functions" / "src" / "test" / "java" / "com" / "mip" / "generated" / slug
        )
        python_dir.mkdir(parents=True, exist_ok=True)
        java_dir.mkdir(parents=True, exist_ok=True)
        test_dir.mkdir(parents=True, exist_ok=True)

        discovery = CapabilityDiscoveryService(self.repository, self.run_id).discover_capability(
            capability
        )
        brd = BRDGenerator(self.repository, self.run_id).from_capability(
            capability, base / "BRD.md"
        )

        (python_dir / "README.md").write_text(self._python_readme(capability), encoding="utf-8")
        (python_dir / "domain.py").write_text(self._python_domain(card_domain), encoding="utf-8")
        (python_dir / "service.py").write_text(
            self._python_service(slug, card_domain), encoding="utf-8"
        )
        (python_dir / "test_service.py").write_text(
            self._python_test(card_domain, slug), encoding="utf-8"
        )

        (java_root / "DomainModels.java").write_text(
            self._java_domain(card_domain), encoding="utf-8"
        )
        (java_dir / f"{self._java_class(slug)}Service.java").write_text(
            self._java_service(slug, card_domain), encoding="utf-8"
        )
        (test_dir / f"{self._java_class(slug)}ServiceTest.java").write_text(
            self._java_test(slug, card_domain), encoding="utf-8"
        )
        (base / "README.md").write_text(self._root_readme(capability, brd), encoding="utf-8")
        return {
            "capability": capability,
            "output_root": str(base),
            "python_functions": str(python_dir),
            "java_functions": str(base / "java_functions"),
            "asset_count": len(discovery["assets"]),
            "brd": brd["output_path"],
        }

    @staticmethod
    def _java_class(slug: str) -> str:
        return "".join(part.capitalize() for part in slug.split("_"))

    @staticmethod
    def _root_readme(capability: str, brd: dict[str, Any]) -> str:
        return f"""# Generated Application Skeleton — {capability.title()}

This directory contains separate Python and Java function skeletons generated from MIP metadata.

- `BRD.md`: generated business requirements document
- `python_functions/`: Python service functions
- `java_functions/`: Java service functions

This is a starting point. Complete implementation requires approved source evidence, fixtures, and equivalence tests.

BRD source asset count: {brd["asset_count"]}
"""

    @staticmethod
    def _python_readme(capability: str) -> str:
        return f"""# Python Functions — {capability.title()}

These functions are intentionally framework-free so they can be tested before being wrapped by FastAPI, batch, or event consumers.
"""

    @staticmethod
    def _python_domain(card_domain: bool) -> str:
        if card_domain:
            return (
                dedent("""
                from __future__ import annotations

                from dataclasses import dataclass, field
                from decimal import Decimal


                @dataclass(frozen=True)
                class CardProductConfig:
                    bank_id: str
                    product_id: str
                    card_type: str  # CREDIT or DEBIT
                    daily_limit: Decimal
                    per_transaction_limit: Decimal
                    allow_international: bool = False
                    interest_rate_apr: Decimal = Decimal("0")
                    fee_table: dict[str, Decimal] = field(default_factory=dict)


                @dataclass(frozen=True)
                class CardTransactionRequest:
                    card_id: str
                    amount: Decimal
                    currency: str
                    merchant_category: str
                    country: str
                    available_balance: Decimal
                    card_status: str


                @dataclass(frozen=True)
                class AuthorizationDecision:
                    approved: bool
                    reason_code: str
                    approved_amount: Decimal
            """).strip()
                + "\n"
            )
        return (
            dedent("""
            from __future__ import annotations

            from dataclasses import dataclass
            from decimal import Decimal
            from typing import Any


            @dataclass(frozen=True)
            class CapabilityRequest:
                payload: dict[str, Any]


            @dataclass(frozen=True)
            class CapabilityResult:
                success: bool
                reason_code: str
                payload: dict[str, Any]
        """).strip()
            + "\n"
        )

    @staticmethod
    def _python_service(slug: str, card_domain: bool) -> str:
        if card_domain:
            return (
                dedent('''
                from __future__ import annotations

                from decimal import Decimal

                from domain import AuthorizationDecision, CardProductConfig, CardTransactionRequest


                def authorize_card_transaction(
                    request: CardTransactionRequest,
                    config: CardProductConfig,
                    spent_today: Decimal = Decimal("0"),
                ) -> AuthorizationDecision:
                    """Configurable credit/debit card authorization function.

                    Bank-specific behavior belongs in CardProductConfig and external rule tables,
                    not hardcoded branches.
                    """
                    if request.card_status.upper() != "ACTIVE":
                        return AuthorizationDecision(False, "CARD_NOT_ACTIVE", Decimal("0"))
                    if request.amount <= 0:
                        return AuthorizationDecision(False, "INVALID_AMOUNT", Decimal("0"))
                    if request.amount > config.per_transaction_limit:
                        return AuthorizationDecision(False, "PER_TXN_LIMIT_EXCEEDED", Decimal("0"))
                    if spent_today + request.amount > config.daily_limit:
                        return AuthorizationDecision(False, "DAILY_LIMIT_EXCEEDED", Decimal("0"))
                    if request.country.upper() != "HOME" and not config.allow_international:
                        return AuthorizationDecision(False, "INTERNATIONAL_NOT_ALLOWED", Decimal("0"))
                    if config.card_type.upper() == "DEBIT" and request.amount > request.available_balance:
                        return AuthorizationDecision(False, "INSUFFICIENT_FUNDS", Decimal("0"))
                    return AuthorizationDecision(True, "APPROVED", request.amount)
            ''').strip()
                + "\n"
            )
        return (
            dedent(f'''
            from __future__ import annotations

            from domain import CapabilityRequest, CapabilityResult


            def execute_{slug}(request: CapabilityRequest) -> CapabilityResult:
                """Execute the generated capability function.

                Replace this placeholder with rule-by-rule implementation from BRD.md and
                equivalence fixtures. Keep this function deterministic and side-effect free.
                """
                return CapabilityResult(success=True, reason_code="PLACEHOLDER", payload=request.payload)
        ''').strip()
            + "\n"
        )

    @staticmethod
    def _python_test(card_domain: bool, slug: str) -> str:
        if card_domain:
            return (
                dedent("""
                from decimal import Decimal

                from domain import CardProductConfig, CardTransactionRequest
                from service import authorize_card_transaction


                def test_debit_authorization_rejects_insufficient_funds():
                    config = CardProductConfig("BANK1", "DEBIT-STD", "DEBIT", Decimal("1000"), Decimal("500"))
                    request = CardTransactionRequest("CARD1", Decimal("200"), "USD", "5411", "HOME", Decimal("100"), "ACTIVE")
                    assert authorize_card_transaction(request, config).reason_code == "INSUFFICIENT_FUNDS"


                def test_credit_authorization_approves_within_limits():
                    config = CardProductConfig("BANK1", "CREDIT-STD", "CREDIT", Decimal("1000"), Decimal("500"))
                    request = CardTransactionRequest("CARD1", Decimal("200"), "USD", "5411", "HOME", Decimal("0"), "ACTIVE")
                    assert authorize_card_transaction(request, config).approved is True
            """).strip()
                + "\n"
            )
        return (
            dedent(f"""
            from domain import CapabilityRequest
            from service import execute_{slug}


            def test_placeholder_capability_executes():
                result = execute_{slug}(CapabilityRequest({"sample": True}))
                assert result.success is True
        """).strip()
            + "\n"
        )

    @staticmethod
    def _java_domain(card_domain: bool) -> str:
        if card_domain:
            return (
                dedent("""
                package com.mip.generated;

                import java.math.BigDecimal;
                import java.util.Map;

                public final class DomainModels {
                    public record CardProductConfig(
                        String bankId,
                        String productId,
                        String cardType,
                        BigDecimal dailyLimit,
                        BigDecimal perTransactionLimit,
                        boolean allowInternational,
                        BigDecimal interestRateApr,
                        Map<String, BigDecimal> feeTable
                    ) {}

                    public record CardTransactionRequest(
                        String cardId,
                        BigDecimal amount,
                        String currency,
                        String merchantCategory,
                        String country,
                        BigDecimal availableBalance,
                        String cardStatus
                    ) {}

                    public record AuthorizationDecision(
                        boolean approved,
                        String reasonCode,
                        BigDecimal approvedAmount
                    ) {}
                }
            """).strip()
                + "\n"
            )
        return (
            dedent("""
            package com.mip.generated;

            import java.util.Map;

            public final class DomainModels {
                public record CapabilityRequest(Map<String, Object> payload) {}
                public record CapabilityResult(boolean success, String reasonCode, Map<String, Object> payload) {}
            }
        """).strip()
            + "\n"
        )

    def _java_service(self, slug: str, card_domain: bool) -> str:
        class_name = self._java_class(slug)
        if card_domain:
            return (
                dedent(f"""
                package com.mip.generated.{slug};

                import static com.mip.generated.DomainModels.*;
                import java.math.BigDecimal;

                public final class {class_name}Service {{
                    public AuthorizationDecision authorizeCardTransaction(
                        CardTransactionRequest request,
                        CardProductConfig config,
                        BigDecimal spentToday
                    ) {{
                        if (!"ACTIVE".equalsIgnoreCase(request.cardStatus())) {{
                            return new AuthorizationDecision(false, "CARD_NOT_ACTIVE", BigDecimal.ZERO);
                        }}
                        if (request.amount().compareTo(BigDecimal.ZERO) <= 0) {{
                            return new AuthorizationDecision(false, "INVALID_AMOUNT", BigDecimal.ZERO);
                        }}
                        if (request.amount().compareTo(config.perTransactionLimit()) > 0) {{
                            return new AuthorizationDecision(false, "PER_TXN_LIMIT_EXCEEDED", BigDecimal.ZERO);
                        }}
                        if (spentToday.add(request.amount()).compareTo(config.dailyLimit()) > 0) {{
                            return new AuthorizationDecision(false, "DAILY_LIMIT_EXCEEDED", BigDecimal.ZERO);
                        }}
                        if (!"HOME".equalsIgnoreCase(request.country()) && !config.allowInternational()) {{
                            return new AuthorizationDecision(false, "INTERNATIONAL_NOT_ALLOWED", BigDecimal.ZERO);
                        }}
                        if ("DEBIT".equalsIgnoreCase(config.cardType()) && request.amount().compareTo(request.availableBalance()) > 0) {{
                            return new AuthorizationDecision(false, "INSUFFICIENT_FUNDS", BigDecimal.ZERO);
                        }}
                        return new AuthorizationDecision(true, "APPROVED", request.amount());
                    }}
                }}
            """).strip()
                + "\n"
            )
        return (
            dedent(f"""
            package com.mip.generated.{slug};

            import static com.mip.generated.DomainModels.*;

            public final class {class_name}Service {{
                public CapabilityResult execute(CapabilityRequest request) {{
                    return new CapabilityResult(true, "PLACEHOLDER", request.payload());
                }}
            }}
        """).strip()
            + "\n"
        )

    def _java_test(self, slug: str, card_domain: bool) -> str:
        class_name = self._java_class(slug)
        if card_domain:
            return (
                dedent(f"""
                package com.mip.generated.{slug};

                import static org.junit.jupiter.api.Assertions.*;
                import static com.mip.generated.DomainModels.*;
                import java.math.BigDecimal;
                import java.util.Map;
                import org.junit.jupiter.api.Test;

                class {class_name}ServiceTest {{
                    @Test
                    void approvesCreditWithinLimits() {{
                        var service = new {class_name}Service();
                        var config = new CardProductConfig("BANK1", "CREDIT", "CREDIT", new BigDecimal("1000"), new BigDecimal("500"), false, BigDecimal.ZERO, Map.of());
                        var request = new CardTransactionRequest("CARD1", new BigDecimal("200"), "USD", "5411", "HOME", BigDecimal.ZERO, "ACTIVE");
                        assertTrue(service.authorizeCardTransaction(request, config, BigDecimal.ZERO).approved());
                    }}
                }}
            """).strip()
                + "\n"
            )
        return (
            dedent(f"""
            package com.mip.generated.{slug};

            import static org.junit.jupiter.api.Assertions.*;
            import static com.mip.generated.DomainModels.*;
            import java.util.Map;
            import org.junit.jupiter.api.Test;

            class {class_name}ServiceTest {{
                @Test
                void executesPlaceholderCapability() {{
                    var service = new {class_name}Service();
                    assertTrue(service.execute(new CapabilityRequest(Map.of("sample", true))).success());
                }}
            }}
        """).strip()
            + "\n"
        )
