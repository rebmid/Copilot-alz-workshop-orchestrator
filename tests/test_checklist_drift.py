"""Tests for ALZ checklist drift detection and stale-ID reporting.

Validates that:
  - ``detect_checklist_drift()`` correctly identifies added/removed areas  
  - ``report_stale_checklist_ids()`` catches orphaned checklist references  
  - ``get_live_design_areas()`` extracts areas from checklist items  
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from alz.loader import (
    ALZ_DESIGN_AREAS,
    detect_checklist_drift,
    get_live_design_areas,
    report_stale_checklist_ids,
)


# ── Fixtures ──────────────────────────────────────────────────────

_MOCK_ITEMS = [
    {"id": "A01.01", "guid": "aaa-111", "text": "t", "severity": "High",
     "category": "Azure Billing and Microsoft Entra ID Tenants", "subcategory": "s"},
    {"id": "B01.01", "guid": "bbb-111", "text": "t", "severity": "High",
     "category": "Identity and Access Management", "subcategory": "s"},
    {"id": "C01.01", "guid": "ccc-111", "text": "t", "severity": "High",
     "category": "Resource Organization", "subcategory": "s"},
    {"id": "D01.01", "guid": "ddd-111", "text": "t", "severity": "High",
     "category": "Network Topology and Connectivity", "subcategory": "s"},
    {"id": "E01.01", "guid": "eee-111", "text": "t", "severity": "High",
     "category": "Governance", "subcategory": "s"},
    {"id": "F01.01", "guid": "fff-111", "text": "t", "severity": "High",
     "category": "Management", "subcategory": "s"},
    {"id": "G01.01", "guid": "ggg-111", "text": "t", "severity": "High",
     "category": "Security", "subcategory": "s"},
    {"id": "H01.01", "guid": "hhh-111", "text": "t", "severity": "High",
     "category": "Platform Automation and DevOps", "subcategory": "s"},
]


# ── get_live_design_areas ─────────────────────────────────────────

class TestGetLiveDesignAreas:
    def test_extracts_areas_from_items(self):
        with patch("alz.loader.get_checklist_items", return_value=_MOCK_ITEMS):
            areas = get_live_design_areas()
        assert set(areas) == set(ALZ_DESIGN_AREAS)

    def test_fallback_on_exception(self):
        with patch("alz.loader.get_checklist_items", side_effect=RuntimeError("offline")):
            areas = get_live_design_areas()
        assert areas == ALZ_DESIGN_AREAS

    def test_detects_new_area(self):
        extra = _MOCK_ITEMS + [
            {"id": "I01.01", "guid": "iii-111", "text": "t", "severity": "High",
             "category": "FinOps", "subcategory": "s"},
        ]
        with patch("alz.loader.get_checklist_items", return_value=extra):
            areas = get_live_design_areas()
        assert "FinOps" in areas


# ── detect_checklist_drift ────────────────────────────────────────

class TestDetectChecklistDrift:
    def test_aligned_when_identical(self):
        with patch("alz.loader.get_live_design_areas", return_value=list(ALZ_DESIGN_AREAS)):
            result = detect_checklist_drift()
        assert result["aligned"] is True
        assert result["added"] == []
        assert result["removed"] == []

    def test_detects_added_area(self):
        live = list(ALZ_DESIGN_AREAS) + ["FinOps"]
        with patch("alz.loader.get_live_design_areas", return_value=live):
            result = detect_checklist_drift()
        assert result["aligned"] is False
        assert "FinOps" in result["added"]
        assert result["removed"] == []

    def test_detects_removed_area(self):
        live = [a for a in ALZ_DESIGN_AREAS if a != "Security"]
        with patch("alz.loader.get_live_design_areas", return_value=live):
            result = detect_checklist_drift()
        assert result["aligned"] is False
        assert "Security" in result["removed"]
        assert result["added"] == []

    def test_detects_renamed_area(self):
        live = [a if a != "Management" else "Management and Monitoring"
                for a in ALZ_DESIGN_AREAS]
        with patch("alz.loader.get_live_design_areas", return_value=live):
            result = detect_checklist_drift()
        assert result["aligned"] is False
        assert "Management and Monitoring" in result["added"]
        assert "Management" in result["removed"]


# ── report_stale_checklist_ids ────────────────────────────────────

class TestReportStaleChecklistIds:
    def test_no_stale_when_all_resolve(self):
        controls = {
            "ctrl1": {
                "name": "Test", "checklist_ids": ["A01.01"],
                "checklist_guids": ["aaa-111"],
            },
        }
        with patch("alz.loader.get_checklist_items", return_value=_MOCK_ITEMS):
            stale = report_stale_checklist_ids(controls)
        assert stale == []

    def test_detects_stale_id(self):
        controls = {
            "ctrl1": {
                "name": "Test", "checklist_ids": ["Z99.99"],
                "checklist_guids": [],
            },
        }
        with patch("alz.loader.get_checklist_items", return_value=_MOCK_ITEMS):
            stale = report_stale_checklist_ids(controls)
        assert len(stale) == 1
        assert stale[0]["field"] == "checklist_ids"
        assert stale[0]["value"] == "Z99.99"

    def test_detects_stale_guid(self):
        controls = {
            "ctrl1": {
                "name": "Test", "checklist_ids": [],
                "checklist_guids": ["deadbeef-0000-0000-0000-000000000000"],
            },
        }
        with patch("alz.loader.get_checklist_items", return_value=_MOCK_ITEMS):
            stale = report_stale_checklist_ids(controls)
        assert len(stale) == 1
        assert stale[0]["field"] == "checklist_guids"

    def test_empty_controls_no_stale(self):
        with patch("alz.loader.get_checklist_items", return_value=_MOCK_ITEMS):
            stale = report_stale_checklist_ids({})
        assert stale == []

    def test_mixed_valid_and_stale(self):
        controls = {
            "ctrl1": {
                "name": "Good", "checklist_ids": ["A01.01"],
                "checklist_guids": ["aaa-111"],
            },
            "ctrl2": {
                "name": "Bad ID", "checklist_ids": ["Z99.99"],
                "checklist_guids": ["aaa-111"],
            },
            "ctrl3": {
                "name": "Bad GUID", "checklist_ids": ["A01.01"],
                "checklist_guids": ["bad-guid"],
            },
        }
        with patch("alz.loader.get_checklist_items", return_value=_MOCK_ITEMS):
            stale = report_stale_checklist_ids(controls)
        assert len(stale) == 2
        stale_cids = {s["control_id"] for s in stale}
        assert stale_cids == {"ctrl2", "ctrl3"}
