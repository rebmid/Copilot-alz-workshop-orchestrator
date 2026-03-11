"""Tests for verification hint tags in CSA workbook Comments column."""
import pytest
from reporting.csa_workbook import _verification_tag


# ── [AUTO] — telemetry-verified controls ──────────────────────────

@pytest.mark.parametrize("status", ["Pass", "Fail", "Partial"])
def test_auto_tag_for_evaluated_statuses(status):
    assert _verification_tag(status, "resource_graph:vnets", "VNet") == "[AUTO]"


@pytest.mark.parametrize("status", ["Pass", "Fail", "Partial"])
def test_auto_tag_even_without_signal_or_service(status):
    assert _verification_tag(status, "", "") == "[AUTO]"


# ── [AZURE] — signal attempted (error/manual with signal) ────────

def test_azure_tag_signal_error():
    assert _verification_tag("SignalError", "resource_graph:app_service_posture", "") == "[AZURE]"


def test_azure_tag_manual_with_signal():
    assert _verification_tag("Manual", "defender:secure_score", "") == "[AZURE]"


def test_azure_tag_not_applicable_with_signal():
    assert _verification_tag("NotApplicable", "resource_graph:sql_posture", "") == "[AZURE]"


# ── [AZURE] — checklist service implies portal-inspectable ───────

def test_azure_tag_manual_with_service():
    assert _verification_tag("Manual", "", "Firewall") == "[AZURE]"


def test_azure_tag_manual_various_services():
    for svc in ("VNet", "DNS", "NSG", "Defender", "Key Vault", "Bastion"):
        assert _verification_tag("Manual", "", svc) == "[AZURE]", svc


# ── [WORKSHOP] — no signal, no service ───────────────────────────

def test_workshop_tag_plain_manual():
    assert _verification_tag("Manual", "", "") == "[WORKSHOP]"


def test_workshop_tag_na_service():
    assert _verification_tag("Manual", "", "N/A") == "[WORKSHOP]"


def test_workshop_tag_whitespace_service():
    assert _verification_tag("Manual", "", "  ") == "[WORKSHOP]"


def test_workshop_tag_not_verified():
    assert _verification_tag("NotVerified", "", "") == "[WORKSHOP]"


# ── Comment prepending integration ────────────────────────────────

def test_tag_prepended_to_comment():
    """Verify tag + existing comment produces 'TAG existing text'."""
    tag = _verification_tag("Fail", "rg:vnets", "VNet")
    comment_body = "3 VNets missing peering"
    result = f"{tag} {comment_body}" if comment_body else tag
    assert result == "[AUTO] 3 VNets missing peering"


def test_tag_alone_when_no_comment():
    tag = _verification_tag("Manual", "", "")
    comment_body = ""
    result = f"{tag} {comment_body}" if comment_body else tag
    assert result == "[WORKSHOP]"
