"""CSA Workbook builder — template-based approach.

Copies a pre-built ``.xlsm`` template that already contains the
Dashboard, charts, formulas, slicers, and pivot tables.  Python only
writes data rows into the **Checklist** sheet  (row 10+, 21 columns).

The Dashboard refreshes automatically because its SUMPRODUCT / FILTER
formulas reference the Checklist data range.

Additional analysis sheets (Executive Summary, 30-60-90 Roadmap,
Risk Analysis) are appended as new tabs in the same workbook.

Usage::

    from reporting.csa_workbook import build_csa_workbook
    build_csa_workbook(
        run_path="out/run.json",
        target_path="out/target_architecture.json",
        output_path="out/CSA_Workbook_v1.xlsm",
    )
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side


# ══════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════

def _load_json(path: str | None) -> dict:
    if not path or not Path(path).exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _safe_get(obj: Any, dotpath: str, default: Any = "") -> Any:
    """Walk a dot-separated path into nested dicts."""
    for key in dotpath.split("."):
        if isinstance(obj, dict):
            obj = obj.get(key, {})
        else:
            return default
    return obj if obj != {} else default


def _join_list(value) -> str:
    if isinstance(value, list):
        return "; ".join(str(v) for v in value if v)
    return str(value) if value else ""


def _status_fill(status: str | None) -> PatternFill | None:
    s = str(status or "").upper()
    if "PASS" in s:
        return PatternFill("solid", fgColor="C6EFCE")
    if "FAIL" in s:
        return PatternFill("solid", fgColor="FFC7CE")
    if "MANUAL" in s:
        return PatternFill("solid", fgColor="FFEB9C")
    if "PARTIAL" in s:
        return PatternFill("solid", fgColor="FFEB9C")
    return None


# ── Shared styles ─────────────────────────────────────────────────
_BOLD = Font(bold=True)
_HEADER_FILL = PatternFill("solid", fgColor="4472C4")
_HEADER_FONT = Font(bold=True, color="FFFFFF")
_SECTION_FONT = Font(bold=True, size=12)
_WRAP = Alignment(wrap_text=True, vertical="top")


def _write_header_row(ws, headers: list[str], row: int = 1):
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=row, column=col, value=h)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL


def _auto_width(ws, min_width: int = 12, max_width: int = 55):
    """Set column widths based on content (capped)."""
    for col in ws.columns:
        col_letter = col[0].column_letter
        lengths = [len(str(cell.value or "")) for cell in col]
        width = min(max(max(lengths, default=min_width), min_width), max_width)
        ws.column_dimensions[col_letter].width = width + 2


# ══════════════════════════════════════════════════════════════════
# Template path + checklist column contract
# ══════════════════════════════════════════════════════════════════

# Resolve template relative to this file's directory
_TEMPLATE_DIR = Path(__file__).resolve().parent
_TEMPLATE_NAME = "Landing_Zone_Assessment.xlsm"
_TEMPLATE_PATH = _TEMPLATE_DIR / _TEMPLATE_NAME

# Checklist sheet schema — row 9 is the header, data starts at row 10.
# These columns are the exact contract that the Dashboard formulas expect.
_CHECKLIST_SHEET = "Checklist"
_CHECKLIST_HEADER_ROW = 9
_CHECKLIST_DATA_START = 10
_CHECKLIST_COLUMNS = [
    # (col_index, header, description)
    (1,  "ID"),              # A  e.g. "A01.01"
    (2,  "Design Area"),     # B  e.g. "Azure Billing and Microsoft Entra ID Tenants"
    (3,  "Sub Area"),        # C  e.g. "Microsoft Entra ID Tenants"
    (4,  "WAF Pillar"),      # D  e.g. "Operations", "Security"
    (5,  "Service"),         # E  e.g. "Entra"
    (6,  "Checklist item"),  # F  full control text
    (7,  "Description"),     # G  optional description
    (8,  "Severity"),        # H  "High" | "Medium" | "Low"
    (9,  "Status"),          # I  "Not verified"|"Open"|"Fulfilled"|"Not required"|"N/A"
    (10, "Comment"),         # J  notes / evidence summary
    (11, "AMMP"),            # K  (reserved)
    (12, "More info"),       # L  Learn link
    (13, "Training"),        # M  Training link
    (14, "Graph Query"),     # N  ARG query name
    (15, "GUID"),            # O  control GUID
    (16, "Secure"),          # P  WAF score (numeric)
    (17, "Cost"),            # Q  WAF score (numeric)
    (18, "Scale"),           # R  WAF score (numeric)
    (19, "Simple"),          # S  WAF score (numeric)
    (20, "HA"),              # T  WAF score (numeric)
    (21, "Source File"),     # U  (reserved)
]

# Map our assessment status → template status vocabulary
_STATUS_MAP: dict[str, str] = {
    "Pass":    "Fulfilled",
    "Fail":    "Open",
    "Manual":  "Not verified",
    "Partial": "Open",
    # Pass through any template-native values unchanged
    "Fulfilled":    "Fulfilled",
    "Open":         "Open",
    "Not verified": "Not verified",
    "Not required": "Not required",
    "N/A":          "N/A",
}


def _map_status(raw: str) -> str:
    """Convert assessment status to template vocabulary."""
    return _STATUS_MAP.get(raw, "Not verified")


# ══════════════════════════════════════════════════════════════════
# Write rows into the Checklist sheet
# ══════════════════════════════════════════════════════════════════

def _write_checklist_rows(
    ws,
    results: list[dict],
    checklist_lookup: dict[str, dict],
) -> int:
    """Populate the Checklist sheet starting at row 10.

    Returns the number of rows written.
    """
    row = _CHECKLIST_DATA_START

    for ctrl in results:
        cid = ctrl.get("control_id", "")
        cl = checklist_lookup.get(cid, {})

        # A: ID (e.g. A01.01)
        ws.cell(row=row, column=1, value=cl.get("id", ""))
        # B: Design Area
        ws.cell(row=row, column=2, value=cl.get(
            "category", ctrl.get("category", ctrl.get("section", ""))))
        # C: Sub Area
        ws.cell(row=row, column=3, value=cl.get("subcategory", ""))
        # D: WAF Pillar
        ws.cell(row=row, column=4, value=cl.get("waf", ""))
        # E: Service
        ws.cell(row=row, column=5, value=cl.get("service", ""))
        # F: Checklist item
        ws.cell(row=row, column=6, value=cl.get(
            "text", ctrl.get("text", ctrl.get("question", ""))))
        # G: Description (optional — use notes or leave blank)
        ws.cell(row=row, column=7, value="")
        # H: Severity
        ws.cell(row=row, column=8, value=ctrl.get(
            "severity", cl.get("severity", "")))
        # I: Status — mapped to template vocabulary
        ws.cell(row=row, column=9, value=_map_status(
            ctrl.get("status", "Manual")))
        # J: Comment
        evidence = ctrl.get("evidence", [])
        comment_parts = []
        notes = ctrl.get("notes", "")
        if notes:
            comment_parts.append(notes)
        for ev in evidence[:2]:
            if isinstance(ev, dict):
                s = ev.get("summary", ev.get("resource_id", ""))
                if s:
                    comment_parts.append(str(s)[:120])
        ws.cell(row=row, column=10, value="\n".join(comment_parts))
        # K: AMMP (reserved)
        ws.cell(row=row, column=11, value="")
        # L: More info (Learn link)
        ws.cell(row=row, column=12, value=cl.get("link", ""))
        # M: Training
        ws.cell(row=row, column=13, value=cl.get("training", ""))
        # N: Graph Query
        ws.cell(row=row, column=14, value=ctrl.get("signal_used", ""))
        # O: GUID
        ws.cell(row=row, column=15, value=cid)
        # P-T: WAF scores (leave as-is from template or blank)
        for col_idx in range(16, 21):
            ws.cell(row=row, column=col_idx, value="")
        # U: Source File
        ws.cell(row=row, column=21, value="lz-assessor")

        row += 1

    return row - _CHECKLIST_DATA_START


def _clear_checklist_data(ws, start_row: int = _CHECKLIST_DATA_START):
    """Clear existing data rows (start_row → max_row) without touching headers."""
    for row in range(start_row, ws.max_row + 1):
        for col in range(1, 22):  # columns A-U
            ws.cell(row=row, column=col).value = None


# ══════════════════════════════════════════════════════════════════
# Risk Analysis sheet builder
# ══════════════════════════════════════════════════════════════════

_SECTION_FILL = PatternFill("solid", fgColor="2F5496")
_SECTION_FONT_WHT = Font(bold=True, size=13, color="FFFFFF")
_SUBSECTION_FILL = PatternFill("solid", fgColor="D6E4F0")
_SUBSECTION_FONT_BLK = Font(bold=True, size=11)
_SEVERITY_FILLS = {
    "High":    PatternFill("solid", fgColor="FFC7CE"),
    "Medium":  PatternFill("solid", fgColor="FFEB9C"),
    "Low":     PatternFill("solid", fgColor="C6EFCE"),
}


def _merge_section(ws, row: int, text: str, max_col: int = 7,
                   fill=None, font=None):
    """Write a merged section header row."""
    ws.merge_cells(start_row=row, start_column=1,
                   end_row=row, end_column=max_col)
    cell = ws.cell(row=row, column=1, value=text)
    cell.font = font or _SECTION_FONT_WHT
    cell.fill = fill or _SECTION_FILL
    cell.alignment = Alignment(vertical="center")


def _merge_text(ws, row: int, text: str, max_col: int = 7):
    """Write a merged multi-line text row."""
    ws.merge_cells(start_row=row, start_column=1,
                   end_row=row, end_column=max_col)
    cell = ws.cell(row=row, column=1, value=text)
    cell.alignment = _WRAP


def _build_risk_analysis_sheet(wb: Workbook, payloads: list[dict]):
    """Add the ``3_Risk_Analysis`` sheet from why-reasoning payloads."""
    ws = wb.create_sheet("3_Risk_Analysis")
    MAX_COL = 7   # merge width
    row = 1

    for idx, payload in enumerate(payloads):
        if "error" in payload:
            continue

        domain = (payload.get("domain") or "Unknown").upper()
        risk = payload.get("risk", {})
        controls = payload.get("failing_controls", [])
        deps = payload.get("dependency_impact", [])
        actions = payload.get("roadmap_actions", [])
        ai = payload.get("ai_explanation", {})

        # ── Domain header ─────────────────────────────────────────
        risk_title = risk.get("title", "")
        _merge_section(ws, row, f"  {domain} — {risk_title}", MAX_COL)
        row += 1

        # ── Root cause ────────────────────────────────────────────
        _merge_section(ws, row, "  Root Cause", MAX_COL,
                       fill=_SUBSECTION_FILL, font=_SUBSECTION_FONT_BLK)
        row += 1
        root_cause = (
            ai.get("root_cause")
            or risk.get("technical_cause", "")
            or risk.get("description", "")
        )
        _merge_text(ws, row, root_cause, MAX_COL)
        row += 2   # blank separator

        # ── Business impact ───────────────────────────────────────
        biz_impact = ai.get("business_impact") or risk.get("business_impact", "")
        if biz_impact:
            _merge_section(ws, row, "  Business Impact", MAX_COL,
                           fill=_SUBSECTION_FILL, font=_SUBSECTION_FONT_BLK)
            row += 1
            _merge_text(ws, row, biz_impact, MAX_COL)
            row += 2

        # ── Failing controls table ────────────────────────────────
        if controls:
            _merge_section(ws, row, "  Failing / Partial Controls", MAX_COL,
                           fill=_SUBSECTION_FILL, font=_SUBSECTION_FONT_BLK)
            row += 1
            ctrl_headers = [
                "Control ID", "Section", "Severity",
                "Status", "Description", "Notes", "",
            ]
            _write_header_row(ws, ctrl_headers, row=row)
            row += 1
            for c in controls:
                cid = c.get("control_id", "")
                short_id = cid[:8] if len(cid) > 8 else cid
                ws.cell(row=row, column=1, value=short_id)
                ws.cell(row=row, column=2, value=c.get("section", ""))
                sev = c.get("severity", "")
                sev_cell = ws.cell(row=row, column=3, value=sev)
                if sev in _SEVERITY_FILLS:
                    sev_cell.fill = _SEVERITY_FILLS[sev]
                status_val = c.get("status", "")
                status_cell = ws.cell(row=row, column=4, value=status_val)
                sfill = _status_fill(status_val)
                if sfill:
                    status_cell.fill = sfill
                ws.cell(row=row, column=5,
                        value=c.get("text", "")).alignment = _WRAP
                ws.cell(row=row, column=6,
                        value=c.get("notes", "")).alignment = _WRAP
                row += 1
            row += 1  # blank separator

        # ── Dependency impact ─────────────────────────────────────
        if deps:
            _merge_section(ws, row, "  Dependency Impact", MAX_COL,
                           fill=_SUBSECTION_FILL, font=_SUBSECTION_FONT_BLK)
            row += 1
            dep_headers = [
                "Failing Control", "Name", "Blocks Count",
                "Blocked Controls", "", "", "",
            ]
            _write_header_row(ws, dep_headers, row=row)
            row += 1
            for d in deps:
                ws.cell(row=row, column=1, value=d.get("control", ""))
                ws.cell(row=row, column=2, value=d.get("name", ""))
                ws.cell(row=row, column=3, value=d.get("blocks_count", 0))
                blocked_str = ", ".join(str(b) for b in d.get("blocks", []))
                ws.cell(row=row, column=4,
                        value=blocked_str).alignment = _WRAP
                row += 1
            row += 1

        # ── Roadmap actions ───────────────────────────────────────
        # Prefer AI fix_sequence when available, fall back to
        # deterministic initiative mapping.
        fix_seq = ai.get("fix_sequence", [])
        if fix_seq:
            _merge_section(ws, row, "  Remediation Roadmap (AI-Prioritized)",
                           MAX_COL, fill=_SUBSECTION_FILL,
                           font=_SUBSECTION_FONT_BLK)
            row += 1
            fix_headers = [
                "Step", "Action", "Why This Order",
                "Phase", "Learn URL", "", "",
            ]
            _write_header_row(ws, fix_headers, row=row)
            row += 1
            total_steps = len(fix_seq)
            for step in fix_seq:
                n = step.get("step", "")
                ws.cell(row=row, column=1, value=n)
                ws.cell(row=row, column=2,
                        value=step.get("action", "")).alignment = _WRAP
                ws.cell(row=row, column=3,
                        value=step.get("why_this_order", "")).alignment = _WRAP
                # Map step to 30/60/90 day phase
                if isinstance(n, int) and total_steps > 0:
                    third = total_steps / 3
                    if n <= third:
                        phase = "30 days"
                    elif n <= 2 * third:
                        phase = "60 days"
                    else:
                        phase = "90 days"
                else:
                    phase = ""
                ws.cell(row=row, column=4, value=phase)
                ws.cell(row=row, column=5,
                        value=step.get("learn_url", "")).alignment = _WRAP
                row += 1
            row += 1
        elif actions:
            _merge_section(ws, row, "  Remediation Roadmap", MAX_COL,
                           fill=_SUBSECTION_FILL, font=_SUBSECTION_FONT_BLK)
            row += 1
            act_headers = [
                "Initiative", "Phase", "Priority",
                "Controls Addressed", "Learn References", "", "",
            ]
            _write_header_row(ws, act_headers, row=row)
            row += 1
            for a in actions:
                ws.cell(row=row, column=1,
                        value=a.get("title", "")).alignment = _WRAP
                ws.cell(row=row, column=2, value=a.get("phase", ""))
                ws.cell(row=row, column=3, value=a.get("priority", ""))
                ws.cell(row=row, column=4,
                        value=_join_list(
                            a.get("controls_addressed", [])
                        )).alignment = _WRAP
                refs = a.get("learn_references", [])
                ref_text = "\n".join(
                    f"{r.get('title', '')}\n{r.get('url', '')}" for r in refs
                )
                ws.cell(row=row, column=5,
                        value=ref_text).alignment = _WRAP
                row += 1
            row += 1

        # ── Cascade effect (AI) ───────────────────────────────────
        cascade = ai.get("cascade_effect", "")
        if cascade:
            _merge_section(ws, row, "  Cascade Effect", MAX_COL,
                           fill=_SUBSECTION_FILL, font=_SUBSECTION_FONT_BLK)
            row += 1
            _merge_text(ws, row, cascade, MAX_COL)
            row += 2

        # ── Separator between domains ─────────────────────────────
        if idx < len(payloads) - 1:
            row += 2   # two blank rows before next domain

    # Column widths
    for col_letter, width in [
        ("A", 16), ("B", 24), ("C", 14), ("D", 18),
        ("E", 55), ("F", 45), ("G", 12),
    ]:
        ws.column_dimensions[col_letter].width = width


# ══════════════════════════════════════════════════════════════════
# Main builder
# ══════════════════════════════════════════════════════════════════

def build_csa_workbook(
    run_path: str = "out/run.json",
    target_path: str = "out/target_architecture.json",
    output_path: str = "out/CSA_Workbook_v1.xlsm",
    why_payloads: list[dict] | None = None,
    template_path: str | None = None,
) -> str:
    """Build the CSA workbook from the pre-built template.

    1. Copies the ``.xlsm`` template (Dashboard + charts + formulas intact).
    2. Writes assessment data into the **Checklist** sheet (row 10+).
    3. Appends analysis sheets (Exec Summary, Roadmap, Risk Analysis).
    4. Saves as ``.xlsm`` — Dashboard refreshes automatically.

    Parameters
    ----------
    template_path : str, optional
        Override the default template location.
    why_payloads : list[dict], optional
        Why-analysis payloads for the Risk Analysis sheet.
    """
    run = _load_json(run_path)
    target = _load_json(target_path)

    # ── Resolve template ──────────────────────────────────────────
    tpl = Path(template_path) if template_path else _TEMPLATE_PATH
    if not tpl.exists():
        raise FileNotFoundError(
            f"Template not found: {tpl}\n"
            f"Place {_TEMPLATE_NAME} in {_TEMPLATE_DIR}/"
        )

    # ── Copy template → output (preserve VBA) ────────────────────
    out = Path(output_path)
    # Force .xlsm extension to preserve macros
    if out.suffix.lower() != ".xlsm":
        out = out.with_suffix(".xlsm")
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(tpl), str(out))

    # ── Open the copy ─────────────────────────────────────────────
    wb = load_workbook(str(out), keep_vba=True)

    # ── Drop the legacy ARG sheet (not used) ──────────────────────
    if "ARG" in wb.sheetnames:
        del wb["ARG"]

    # ── Load ALZ checklist for rich per-control fields ────────────
    checklist_lookup: dict[str, dict] = {}
    try:
        from alz.loader import load_alz_checklist
        cl = load_alz_checklist()
        for item in cl.get("items", []):
            guid = item.get("guid", "")
            if guid:
                checklist_lookup[guid] = item
    except Exception:
        pass  # workbook still works without checklist enrichment

    results = run.get("results", [])

    # ══════════════════════════════════════════════════════════════
    # Write data into the Checklist sheet
    # ══════════════════════════════════════════════════════════════
    if _CHECKLIST_SHEET in wb.sheetnames:
        ws_cl = wb[_CHECKLIST_SHEET]
        _clear_checklist_data(ws_cl)
        n_written = _write_checklist_rows(ws_cl, results, checklist_lookup)
        print(f"  ✓ Checklist: {n_written} rows written (row {_CHECKLIST_DATA_START}–{_CHECKLIST_DATA_START + n_written - 1})")
    else:
        print(f"  ⚠ Sheet '{_CHECKLIST_SHEET}' not found in template — skipping data write")
        n_written = 0

    # ══════════════════════════════════════════════════════════════
    # Append analysis sheets (these don't exist in the template)
    # ══════════════════════════════════════════════════════════════

    # ── Derived values (safe against missing keys) ────────────────
    tenant_id = _safe_get(run, "execution_context.tenant_id", "Unknown") or "Unknown"
    tenant_name = _safe_get(run, "execution_context.tenant_display_name", "") or ""
    timestamp = _safe_get(run, "meta.timestamp", datetime.now(timezone.utc).isoformat())
    scoring = run.get("scoring", {})
    coverage = scoring.get("automation_coverage", {})
    maturity = scoring.get("overall_maturity_percent", "")
    data_driven = coverage.get("data_driven", "")
    customer_input = coverage.get("requires_customer_input", "")
    sub_count = _safe_get(run, "execution_context.subscription_count_visible", "")

    es_readiness = run.get("enterprise_scale_readiness", {})
    readiness_label = (
        "Yes" if es_readiness.get("ready_for_enterprise_scale") else "No"
    ) if es_readiness else "Unknown"
    readiness_score = es_readiness.get("readiness_score", "")

    top_risks = run.get("executive_summary", {}).get("top_business_risks", [])

    # =============================================================
    # Executive Summary  (appended as new sheet)
    # =============================================================
    ws = wb.create_sheet("Executive_Summary")
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 70

    exec_summary = run.get("executive_summary", {})
    risk_areas = ", ".join(
        r.get("title", "")[:60] for r in top_risks[:3]
    ) or "landing zone maturity gaps"

    csa_rows: list[tuple[str, str]] = [
        ("CSA ENGAGEMENT FRAMING", ""),
        ("Engagement Objective",
         "Assess the customer's Azure landing zone maturity, identify "
         "critical gaps, and deliver a prioritised 30-60-90 remediation "
         "roadmap aligned to Microsoft Cloud Adoption Framework."),
        ("Key Message",
         f"This assessment identified {len(results)} controls across "
         f"the tenant. Top risk areas include: {risk_areas}. "
         f"The roadmap ties each action to specific controls and risks, "
         f"making every recommendation defensible and auditable."),
        ("Customer Outcome",
         "A data-driven workbook the customer owns — with scored "
         "controls, a traceable remediation plan, and Microsoft Learn "
         "references — enabling them to drive implementation with or "
         "without further Microsoft engagement."),
        ("", ""),
    ]
    row_num = 1
    for label, val in csa_rows:
        label_cell = ws.cell(row=row_num, column=1, value=label)
        val_cell = ws.cell(row=row_num, column=2, value=val)
        if label == "CSA ENGAGEMENT FRAMING":
            label_cell.font = _SECTION_FONT
        else:
            label_cell.font = _BOLD
            val_cell.alignment = _WRAP
        row_num += 1

    ws.cell(row=row_num, column=1, value="ASSESSMENT METRICS").font = _SECTION_FONT
    row_num += 1

    tenant_label = f"{tenant_name} ({tenant_id})" if tenant_name else str(tenant_id)
    rows: list[tuple[str, str]] = [
        ("Tenant", tenant_label),
        ("Assessment Date", str(timestamp)),
        ("Enterprise-Scale Ready", f"{readiness_label}  (score: {readiness_score})"),
        ("Overall Maturity", f"{maturity}%"),
        ("Data-Driven Controls", str(data_driven)),
        ("Requires Customer Input", str(customer_input)),
        ("Subscriptions Assessed", str(sub_count)),
    ]
    for label, val in rows:
        ws.cell(row=row_num, column=1, value=label).font = _BOLD
        ws.cell(row=row_num, column=2, value=val)
        row_num += 1

    row_num += 1
    ws.cell(row=row_num, column=1, value="Top Risks").font = _SECTION_FONT
    row_num += 1
    _write_header_row(ws, ["Risk", "Business Impact", "Severity"], row_num)
    row_num += 1
    for risk in top_risks[:5]:
        ws.cell(row=row_num, column=1, value=risk.get("title", ""))
        ws.cell(row=row_num, column=2, value=risk.get("business_impact", "")).alignment = _WRAP
        ws.cell(row=row_num, column=3, value=risk.get("severity", ""))
        row_num += 1

    # =============================================================
    # 30-60-90 Roadmap  (appended as new sheet)
    # =============================================================
    ws = wb.create_sheet("Roadmap_30_60_90")
    headers = ["Phase", "Action", "Initiative ID", "CAF Discipline",
               "Owner", "Success Criteria", "Dependencies",
               "Related Controls", "Related Risks"]
    _write_header_row(ws, headers)

    initiative_lookup: dict[str, dict] = {}
    for init in run.get("transformation_plan", {}).get("initiatives", []):
        iid = init.get("initiative_id", "")
        if iid:
            initiative_lookup[iid] = init

    control_to_risks: dict[str, set[str]] = {}
    for risk in top_risks:
        risk_title = risk.get("title", "")
        for cid in risk.get("affected_controls", []):
            control_to_risks.setdefault(cid, set()).add(risk_title)

    def _control_labels(guids: list[str]) -> str:
        labels = []
        for g in guids[:8]:
            cl_item = checklist_lookup.get(g, {})
            labels.append(cl_item.get("id", g[:8]))
        if len(guids) > 8:
            labels.append(f"+{len(guids) - 8} more")
        return ", ".join(labels)

    def _risks_for_controls(guids: list[str]) -> str:
        risk_titles: set[str] = set()
        for g in guids:
            risk_titles |= control_to_risks.get(g, set())
        return "; ".join(sorted(risk_titles))

    roadmap_3060 = _safe_get(run, "transformation_roadmap.roadmap_30_60_90", {})
    if roadmap_3060 and isinstance(roadmap_3060, dict):
        row = 2
        for phase_key, phase_label in [
            ("30_days", "30 Days"),
            ("60_days", "60 Days"),
            ("90_days", "90 Days"),
        ]:
            items = roadmap_3060.get(phase_key, [])
            for item in items:
                iid = item.get("initiative_id", "")
                init = initiative_lookup.get(iid, {})
                control_guids = init.get("controls", [])

                ws.cell(row=row, column=1, value=phase_label)
                ws.cell(row=row, column=2, value=item.get("action", "")).alignment = _WRAP
                ws.cell(row=row, column=3, value=iid)
                ws.cell(row=row, column=4, value=item.get("caf_discipline", ""))
                ws.cell(row=row, column=5, value=item.get("owner_role", ""))
                ws.cell(row=row, column=6, value=item.get("success_criteria", "")).alignment = _WRAP
                ws.cell(row=row, column=7, value=_join_list(item.get("dependency_on", []))).alignment = _WRAP
                ws.cell(row=row, column=8, value=_control_labels(control_guids)).alignment = _WRAP
                ws.cell(row=row, column=9, value=_risks_for_controls(control_guids)).alignment = _WRAP
                row += 1
    else:
        row = 2
        for phase in _safe_get(target, "implementation_plan.phases", []):
            phase_name = phase.get("name", phase.get("phase", ""))
            for eu in phase.get("execution_units", []):
                ws.cell(row=row, column=1, value=phase_name)
                ws.cell(row=row, column=2, value=eu.get("capability", ""))
                ws.cell(row=row, column=3, value="")
                ws.cell(row=row, column=4, value="")
                ws.cell(row=row, column=5, value=eu.get("owner", ""))
                ws.cell(row=row, column=6, value=_join_list(eu.get("success_criteria"))).alignment = _WRAP
                ws.cell(row=row, column=7, value=_join_list(eu.get("depends_on"))).alignment = _WRAP
                ws.cell(row=row, column=8, value="")
                ws.cell(row=row, column=9, value="")
                row += 1
    _auto_width(ws)

    # =============================================================
    # Risk Analysis  (from why-reasoning payloads)
    # =============================================================
    if why_payloads:
        _build_risk_analysis_sheet(wb, why_payloads)

    # ══════════════════════════════════════════════════════════════
    # Ensure Dashboard is the first visible sheet
    # ══════════════════════════════════════════════════════════════
    if "Dashboard" in wb.sheetnames:
        dash_idx = wb.sheetnames.index("Dashboard")
        if dash_idx != 0:
            wb.move_sheet("Dashboard", offset=-dash_idx)
        wb.active = 0

    # ── Save (with fallback if file is locked) ────────────────────
    try:
        wb.save(str(out))
    except PermissionError:
        stem = out.stem
        ts = datetime.now().strftime("%H%M%S")
        fallback = out.with_name(f"{stem}_{ts}.xlsm")
        wb.save(str(fallback))
        print(f"  ⚠ {out.name} is locked (open in Excel?). Saved as {fallback.name}")
        out = fallback
    print(f"  ✓ CSA workbook → {out}  ({n_written} controls written to Checklist)")

    # ── Post-processing enrichment (adds metadata columns) ───────
    from reporting.enrich import enrich_control_details_sheet
    enrich_control_details_sheet(str(out))

    return str(out)