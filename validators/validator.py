"""
Validation suite for the YottaFlex Supply Chain Shortage Prioritization System.

Implements Step 8 of the data generation specification:
  - Primary-key uniqueness
  - Foreign-key integrity
  - Allowed enum values
  - Date ordering
  - Arithmetic reconciliation
  - Lifecycle transition validity
  - Duplicate checks

Returns a structured validation report (list of dicts).
"""

import pandas as pd
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


# ──────────────────────────────── helpers ────────────────────────────────

class ValidationResult:
    """Container for a single validation check result."""

    def __init__(self, check_name: str, entity: str, status: str,
                 message: str, details: str = ""):
        self.check_name = check_name
        self.entity = entity
        self.status = status          # PASS / FAIL / WARN
        self.message = message
        self.details = details

    def to_dict(self):
        return {
            "check_name": self.check_name,
            "entity": self.entity,
            "status": self.status,
            "message": self.message,
            "details": self.details,
            "timestamp": datetime.now().isoformat(),
        }


def _check_pk_unique(df: pd.DataFrame, pk_col: str, entity: str,
                      known_anomaly_ids: set = None) -> ValidationResult:
    """Check primary-key uniqueness, distinguishing deliberate edge cases from data corruption."""
    n_dups = df[pk_col].duplicated().sum()
    if n_dups == 0:
        return ValidationResult(
            "pk_uniqueness", entity, "PASS",
            f"All {len(df)} {pk_col} values are unique."
        )
    dup_ids = set(df.loc[df[pk_col].duplicated(keep=False), pk_col].unique())
    known_anomaly_ids = known_anomaly_ids or set()
    unaccounted_dups = dup_ids - known_anomaly_ids

    if len(unaccounted_dups) == 0:
        return ValidationResult(
            "pk_uniqueness", entity, "WARN",
            f"{n_dups} duplicate {pk_col} values found, matching labeled 'inbound_counted_twice' edge cases in ground truth.",
            f"Labeled duplicate IDs: {list(dup_ids)[:10]}"
        )

    return ValidationResult(
        "pk_uniqueness", entity, "FAIL",
        f"{n_dups} duplicate {pk_col} values found ({len(unaccounted_dups)} unaccounted for in ground truth).",
        f"Unaccounted duplicates: {list(unaccounted_dups)[:10]}"
    )



def _check_fk_integrity(child_df: pd.DataFrame, child_col: str,
                         parent_df: pd.DataFrame, parent_col: str,
                         child_entity: str, parent_entity: str,
                         allow_null: bool = False) -> ValidationResult:
    """Check foreign-key referential integrity."""
    child_vals = child_df[child_col].dropna() if allow_null else child_df[child_col]
    parent_vals = set(parent_df[parent_col])
    orphans = child_vals[~child_vals.isin(parent_vals)]
    if len(orphans) == 0:
        return ValidationResult(
            "fk_integrity", f"{child_entity}.{child_col}→{parent_entity}.{parent_col}",
            "PASS",
            f"All {len(child_vals)} foreign keys resolve."
        )
    sample = list(orphans.unique()[:10])
    return ValidationResult(
        "fk_integrity", f"{child_entity}.{child_col}→{parent_entity}.{parent_col}",
        "FAIL",
        f"{len(orphans)} orphan foreign keys found.",
        f"Sample orphans: {sample}"
    )


def _check_enum(df: pd.DataFrame, col: str, allowed: list,
                entity: str) -> ValidationResult:
    """Check that a column contains only allowed enum values."""
    actual = set(df[col].dropna().unique())
    invalid = actual - set(allowed)
    if not invalid:
        return ValidationResult(
            "enum_values", f"{entity}.{col}", "PASS",
            f"All values in allowed set: {allowed}"
        )
    return ValidationResult(
        "enum_values", f"{entity}.{col}", "FAIL",
        f"Invalid values found: {invalid}",
        f"Allowed: {allowed}"
    )


def _check_positive(df: pd.DataFrame, col: str,
                     entity: str, allow_zero: bool = True) -> ValidationResult:
    """Check that numeric column has positive (or non-negative) values."""
    if allow_zero:
        bad = df[df[col] < 0]
    else:
        bad = df[df[col] <= 0]
    if len(bad) == 0:
        return ValidationResult(
            "positive_values", f"{entity}.{col}", "PASS",
            f"All {len(df)} values are {'non-negative' if allow_zero else 'positive'}."
        )
    return ValidationResult(
        "positive_values", f"{entity}.{col}", "FAIL",
        f"{len(bad)} negative/zero values found.",
        f"Min value: {df[col].min()}"
    )


def _check_lifecycle_transitions(pos: pd.DataFrame, prod: pd.DataFrame) -> list[ValidationResult]:
    """Verify lifecycle state consistency and transition rules."""
    results = []
    if not pos.empty and "status" in pos.columns:
        received = pos[pos["status"] == "RECEIVED"]
        missing_delivery = received["actual_delivery_date"].isna().sum() if "actual_delivery_date" in received.columns else 0
        results.append(ValidationResult(
            "lifecycle_transition", "PurchaseOrder.RECEIVED",
            "PASS" if missing_delivery == 0 else "FAIL",
            f"All {len(received)} RECEIVED orders have recorded delivery dates." if missing_delivery == 0
            else f"{missing_delivery} RECEIVED orders lack actual_delivery_date."
        ))

        unreceived = pos[pos["status"].isin(["OPEN", "CONFIRMED"])]
        premature_delivery = unreceived["actual_delivery_date"].notna().sum() if "actual_delivery_date" in unreceived.columns else 0
        results.append(ValidationResult(
            "lifecycle_transition", "PurchaseOrder.OPEN_or_CONFIRMED",
            "PASS" if premature_delivery == 0 else "WARN",
            f"All {len(unreceived)} pending orders have null actual_delivery_date." if premature_delivery == 0
            else f"{premature_delivery} pending orders have premature delivery dates."
        ))

    if not prod.empty and "status" in prod.columns:
        completed = prod[prod["status"] == "COMPLETED"]
        missing_actual = completed["actual_quantity"].isna().sum() if "actual_quantity" in completed.columns else 0
        results.append(ValidationResult(
            "lifecycle_transition", "ProductionPlan.COMPLETED",
            "PASS" if missing_actual == 0 else "FAIL",
            f"All {len(completed)} COMPLETED production plans have recorded actual_quantity." if missing_actual == 0
            else f"{missing_actual} COMPLETED plans lack actual_quantity."
        ))

    return results


def _check_date_order(df: pd.DataFrame, col_before: str, col_after: str,
                       entity: str) -> ValidationResult:
    """Check that col_before <= col_after."""
    # Convert to datetime if needed
    before = pd.to_datetime(df[col_before], errors='coerce')
    after = pd.to_datetime(df[col_after], errors='coerce')
    valid = before.notna() & after.notna()
    violations = (before[valid] > after[valid]).sum()
    if violations == 0:
        return ValidationResult(
            "date_order", f"{entity}.{col_before}<={col_after}", "PASS",
            f"All date orderings valid ({valid.sum()} checked)."
        )
    return ValidationResult(
        "date_order", f"{entity}.{col_before}<={col_after}", "FAIL",
        f"{violations} date ordering violations."
    )


# ──────────────────────────── main validator ────────────────────────────

def run_validation(data: dict) -> list[dict]:
    """
    Run all validation checks on the generated data.

    Parameters
    ----------
    data : dict
        Dictionary of entity name → pandas DataFrame.

    Returns
    -------
    list[dict]
        List of validation results, each as a dictionary.
    """
    results: list[ValidationResult] = []
    skus = data.get("skus", pd.DataFrame())
    locations = data.get("locations", pd.DataFrame())
    suppliers = data.get("suppliers", pd.DataFrame())
    supplier_caps = data.get("supplier_capacities", pd.DataFrame())
    lead_times = data.get("lead_times", pd.DataFrame())
    demand = data.get("forecast_demand", pd.DataFrame())
    inventory = data.get("inventory", pd.DataFrame())
    pos = data.get("purchase_orders", pd.DataFrame())
    prod = data.get("production_plans", pd.DataFrame())
    shortages = data.get("shortages", pd.DataFrame())
    mitigations = data.get("mitigations", pd.DataFrame())
    ground_truth = data.get("ground_truth", pd.DataFrame())

    known_dup_pos = set()
    if not ground_truth.empty and "issue_type" in ground_truth.columns and "record_id" in ground_truth.columns:
        known_dup_pos = set(ground_truth[ground_truth["issue_type"] == "inbound_counted_twice"]["record_id"])

    # ── 1. Primary-key uniqueness ──────────────────────────────────────
    pk_checks = [
        (skus, "sku_id", "SKU"),
        (locations, "location_id", "Location"),
        (suppliers, "supplier_id", "Supplier"),
        (supplier_caps, "supplier_capacity_id", "SupplierCapacity"),
        (lead_times, "lead_time_id", "LeadTime"),
        (demand, "demand_id", "ForecastDemand"),
        (inventory, "inventory_id", "Inventory"),
        (pos, "po_id", "PurchaseOrder"),
        (prod, "production_plan_id", "ProductionPlan"),
    ]
    if not shortages.empty:
        pk_checks.append((shortages, "shortage_id", "Shortage"))
    if not mitigations.empty:
        pk_checks.append((mitigations, "mitigation_id", "MitigationOption"))

    for df, pk, entity in pk_checks:
        if not df.empty and pk in df.columns:
            anomalies = known_dup_pos if entity == "PurchaseOrder" else None
            results.append(_check_pk_unique(df, pk, entity, anomalies))


    # ── 2. Foreign-key integrity ───────────────────────────────────────
    fk_checks = [
        # SupplierCapacity
        (supplier_caps, "supplier_id", suppliers, "supplier_id", "SupplierCapacity", "Supplier"),
        (supplier_caps, "sku_id", skus, "sku_id", "SupplierCapacity", "SKU"),
        # LeadTime
        (lead_times, "supplier_id", suppliers, "supplier_id", "LeadTime", "Supplier"),
        (lead_times, "location_id", locations, "location_id", "LeadTime", "Location"),
        # ForecastDemand
        (demand, "sku_id", skus, "sku_id", "ForecastDemand", "SKU"),
        (demand, "location_id", locations, "location_id", "ForecastDemand", "Location"),
        # Inventory
        (inventory, "sku_id", skus, "sku_id", "Inventory", "SKU"),
        (inventory, "location_id", locations, "location_id", "Inventory", "Location"),
        # PurchaseOrder
        (pos, "supplier_id", suppliers, "supplier_id", "PurchaseOrder", "Supplier"),
        (pos, "sku_id", skus, "sku_id", "PurchaseOrder", "SKU"),
        (pos, "location_id", locations, "location_id", "PurchaseOrder", "Location"),
        # ProductionPlan
        (prod, "sku_id", skus, "sku_id", "ProductionPlan", "SKU"),
        (prod, "location_id", locations, "location_id", "ProductionPlan", "Location"),
    ]
    # Substitute SKU FK (nullable)
    if not skus.empty and "substitute_sku_id" in skus.columns:
        has_sub = skus[skus["substitute_sku_id"].notna()]
        if len(has_sub) > 0:
            results.append(_check_fk_integrity(
                has_sub, "substitute_sku_id", skus, "sku_id",
                "SKU", "SKU (substitute)", allow_null=True
            ))

    for child_df, child_col, parent_df, parent_col, child_e, parent_e in fk_checks:
        if not child_df.empty and child_col in child_df.columns and not parent_df.empty:
            results.append(_check_fk_integrity(
                child_df, child_col, parent_df, parent_col, child_e, parent_e
            ))

    # Shortage and Mitigation FKs
    if not shortages.empty:
        results.append(_check_fk_integrity(
            shortages, "sku_id", skus, "sku_id", "Shortage", "SKU"
        ))
        results.append(_check_fk_integrity(
            shortages, "location_id", locations, "location_id", "Shortage", "Location"
        ))
    if not mitigations.empty and not shortages.empty:
        results.append(_check_fk_integrity(
            mitigations, "shortage_id", shortages, "shortage_id",
            "MitigationOption", "Shortage"
        ))

    # ── 3. Enum checks ────────────────────────────────────────────────
    enum_checks = [
        (skus, "category", config.SKU_CATEGORIES, "SKU"),
        (skus, "uom", config.UNITS_OF_MEASURE, "SKU"),
        (skus, "status", ["ACTIVE", "DISCONTINUED", "ON_HOLD"], "SKU"),
        (locations, "type", config.LOCATION_TYPES, "Location"),
        (locations, "region", config.REGIONS, "Location"),
        (suppliers, "payment_terms", config.SUPPLIER_PAYMENT_TERMS, "Supplier"),
        (suppliers, "status", ["ACTIVE", "INACTIVE", "SUSPENDED"], "Supplier"),
        (lead_times, "transport_mode", config.TRANSPORT_MODES, "LeadTime"),
        (demand, "demand_type", ["REGULAR", "PROMOTIONAL"], "ForecastDemand"),
        (pos, "status", config.PO_STATUSES, "PurchaseOrder"),
        (prod, "status", ["PLANNED", "IN_PROGRESS", "COMPLETED", "CANCELLED"], "ProductionPlan"),
    ]
    if not shortages.empty:
        enum_checks.append(
            (shortages, "severity", config.SHORTAGE_SEVERITIES, "Shortage")
        )
    if not mitigations.empty:
        enum_checks.append(
            (mitigations, "mitigation_type", config.MITIGATION_TYPES, "MitigationOption")
        )

    for df, col, allowed, entity in enum_checks:
        if not df.empty and col in df.columns:
            results.append(_check_enum(df, col, allowed, entity))

    # ── 4. Positive / non-negative value checks ───────────────────────
    positive_checks = [
        (demand, "quantity", "ForecastDemand", False),
        (inventory, "on_hand_qty", "Inventory", True),
        (pos, "quantity", "PurchaseOrder", False),
        (supplier_caps, "max_weekly_capacity", "SupplierCapacity", False),
        (supplier_caps, "min_order_qty", "SupplierCapacity", False),
    ]
    for df, col, entity, allow_zero in positive_checks:
        if not df.empty and col in df.columns:
            results.append(_check_positive(df, col, entity, allow_zero))

    # ── 5. Date ordering checks ───────────────────────────────────────
    if not supplier_caps.empty and "effective_from" in supplier_caps.columns:
        results.append(_check_date_order(
            supplier_caps, "effective_from", "effective_to", "SupplierCapacity"
        ))
    if not lead_times.empty and "effective_from" in lead_times.columns:
        results.append(_check_date_order(
            lead_times, "effective_from", "effective_to", "LeadTime"
        ))
    if not pos.empty and "order_date" in pos.columns:
        results.append(_check_date_order(
            pos, "order_date", "expected_delivery_date", "PurchaseOrder"
        ))

    # ── 6. Arithmetic reconciliation ──────────────────────────────────
    if not pos.empty and "unit_cost" in pos.columns and "total_cost" in pos.columns:
        computed = pos["quantity"] * pos["unit_cost"]
        mismatch = (abs(computed - pos["total_cost"]) > 0.01).sum()
        results.append(ValidationResult(
            "arithmetic_reconciliation", "PurchaseOrder.total_cost",
            "PASS" if mismatch == 0 else "WARN",
            f"total_cost = quantity × unit_cost: {mismatch} mismatches out of {len(pos)}."
        ))

    # ── 7. Week range checks ─────────────────────────────────────────
    if not demand.empty and "week" in demand.columns:
        out_of_range = ((demand["week"] < 1) | (demand["week"] > 52)).sum()
        results.append(ValidationResult(
            "week_range", "ForecastDemand.week",
            "PASS" if out_of_range == 0 else "FAIL",
            f"Weeks out of [1,52] range: {out_of_range}"
        ))

    # ── 8. MOQ vs capacity check ──────────────────────────────────────
    if not supplier_caps.empty:
        bad_moq = (supplier_caps["min_order_qty"] > supplier_caps["max_weekly_capacity"]).sum()
        results.append(ValidationResult(
            "moq_vs_capacity", "SupplierCapacity",
            "PASS" if bad_moq == 0 else "WARN",
            f"MOQ > max_weekly_capacity: {bad_moq} records"
        ))

    # ── 9. Supplier reliability range ─────────────────────────────────
    if not suppliers.empty and "reliability_score" in suppliers.columns:
        out_range = ((suppliers["reliability_score"] < 0) |
                     (suppliers["reliability_score"] > 1)).sum()
        results.append(ValidationResult(
            "score_range", "Supplier.reliability_score",
            "PASS" if out_range == 0 else "FAIL",
            f"Values outside [0,1]: {out_range}"
        ))

    # ── 10. Duplicate row check (full row dedup) ──────────────────────
    for entity, df, pk in [("SKU", skus, "sku_id"),
                            ("ForecastDemand", demand, "demand_id"),
                            ("PurchaseOrder", pos, "po_id")]:
        if not df.empty:
            full_dups = df.duplicated().sum()
            results.append(ValidationResult(
                "full_row_duplicates", entity,
                "PASS" if full_dups == 0 else "WARN",
                f"{full_dups} fully duplicated rows."
            ))

    # ── 11. Lifecycle transition checks ───────────────────────────────
    results.extend(_check_lifecycle_transitions(pos, prod))

    return [r.to_dict() for r in results]


def print_validation_report(results: list[dict]):
    """Print a formatted validation report to stdout."""
    print("\n" + "=" * 80)
    print("  VALIDATION REPORT")
    print("=" * 80)

    pass_count = sum(1 for r in results if r["status"] == "PASS")
    fail_count = sum(1 for r in results if r["status"] == "FAIL")
    warn_count = sum(1 for r in results if r["status"] == "WARN")

    print(f"\n  Total checks: {len(results)}")
    print(f"  ✅ PASS: {pass_count}  |  ❌ FAIL: {fail_count}  |  ⚠️  WARN: {warn_count}\n")
    print("-" * 80)

    for r in results:
        icon = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️ "}.get(r["status"], "?")
        print(f"  {icon} [{r['entity']}] {r['check_name']}: {r['message']}")
        if r["details"]:
            print(f"      ↳ {r['details']}")

    print("=" * 80 + "\n")


def export_validation_summary(results: list[dict], output_path: str = None):
    """Export validation results to a markdown file."""
    if output_path is None:
        output_path = os.path.join(config.PROJECT_ROOT, "docs", "validation_summary.md")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    pass_count = sum(1 for r in results if r["status"] == "PASS")
    fail_count = sum(1 for r in results if r["status"] == "FAIL")
    warn_count = sum(1 for r in results if r["status"] == "WARN")

    with open(output_path, "w") as f:
        f.write("# Validation Summary\n\n")
        f.write(f"**Generated**: {datetime.now().isoformat()}\n\n")
        f.write("| Status | Count |\n|--------|-------|\n")
        f.write(f"| ✅ PASS | {pass_count} |\n")
        f.write(f"| ❌ FAIL | {fail_count} |\n")
        f.write(f"| ⚠️  WARN | {warn_count} |\n")
        f.write(f"| **Total** | **{len(results)}** |\n\n")

        f.write("## Detailed Results\n\n")
        f.write("| Status | Entity | Check | Message | Details |\n")
        f.write("|--------|--------|-------|---------|--------|\n")
        for r in results:
            icon = {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️"}.get(r["status"], "?")
            details = r["details"].replace("|", "\\|") if r["details"] else "—"
            msg = r["message"].replace("|", "\\|")
            f.write(f"| {icon} | {r['entity']} | {r['check_name']} | {msg} | {details} |\n")

    print(f"  📄 Validation summary exported to {output_path}")
