"""One call from readings and sheet lines to the final plan, shared by the app and the tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .findings import Finding
from .identify import Reading
from .plan import Plan, build_plan
from .resolve import Resolver
from .rules import Pack, SectionSource, check_packs, meal_notes, packs_from_readings
from .schedule import Line, Reconciliation, lines_from_rows, reconcile


@dataclass
class Result:
    packs: list[Pack]
    lines: list[Line]
    recon: Reconciliation
    plan: Plan


def manual_pack(cn: str, resolver: Resolver) -> tuple[Pack | None, str]:
    """A pack added by typing the Codigo Nacional printed on the box ('C.N. 848226.9'). Returns (pack, problem)."""
    from . import cn as cn_module
    found = cn_module.find_cn(cn)
    if not found or not cn_module.is_valid(found):
        return None, "The national code is not valid: check the 7 digits (the last one is a check digit)."
    medicine = resolver.by_cn(found)
    if medicine is None:
        return None, f"AEMPS CIMA does not know the national code {found[:6]}."
    return Pack(medicine, "confirmed"), ""


def make_plan(readings: list[Reading], extra_packs: list[Pack], rows: list[dict], smpc: SectionSource | None,
              today: date | None = None) -> Result:
    """`rows` come from the editable sheet; a row is confirmed when its "confirmed" value is true."""
    packs, findings = packs_from_readings(readings)
    seen = {p.medicine.cn for p in packs}
    packs += [p for p in extra_packs if p.medicine.cn not in seen]
    lines, dose_findings = lines_from_rows(rows)
    for line, row in zip(lines, rows):
        line.confirmed = bool(row.get("confirmed"))
    recon = reconcile(lines, packs)
    unknown_expiry = [Finding("expiry_unknown", [p.medicine.name], [p.medicine.cn],
                              "the code that was read carries no usable expiry" if p.state == "verified" else "the pack was added without reading its code",
                              severity="review" if p.state == "verified" else "info") for p in packs if p.expiry is None]
    all_findings: list[Finding] = findings + dose_findings + check_packs(packs, smpc, today) + (meal_notes(packs, smpc) if smpc else []) + unknown_expiry + recon.findings
    plan = build_plan(lines, recon, all_findings, today)
    plan.smpc_used = smpc is not None
    return Result(packs, lines, recon, plan)
