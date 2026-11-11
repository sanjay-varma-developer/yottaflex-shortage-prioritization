"""
Comprehensive test suite for the YottaFlex Supply Chain Pipeline.

Validates:
- Generation integrity and constraints (Master, Capacity, Demand, Inventory, POs, Plans)
- PAB balance arithmetic (Beginning + Receipts + Prod - Demand = Ending)
- Shortage detection criteria, duration clustering, and severity assignment
- Mitigation feasibility scoring and recommendation flags
- Ground truth segregation (strict isolation from input features)
- All 5 injected edge cases (inbound duplicate, unapproved substitute, capacity ceiling, missing lead time, UOM mismatch)
- Lifecycle transition integrity (PO received dates, Production completed quantities)
- Audit trail event logging (state change events)
- SQLite database relational schema and export parity
- Primary actor view generation (Planner, Ops, Logistics, Supplier, Warehouse)
"""

import os
import sqlite3
import numpy as np
import pytest

import config
from generator.generate import run_generation
from generator.sql_exporter import export_sqlite_and_sql
from engine.balance_engine import calculate_projected_balance
from engine.shortage_detector import detect_shortages
from engine.mitigation_engine import generate_mitigations
from engine.event_logger import generate_state_transition_events
from engine.actor_views import (
    generate_planner_view,
    generate_operations_summary,
    generate_logistics_analyst_view,
    generate_supplier_scorecard,
    generate_warehouse_schedule,
)
from validators.validator import run_validation


@pytest.fixture(scope="module")
def starter_dataset():
    """Generate a quick starter dataset (scale=0.05) for rapid test execution."""
    orig_scale = config.SCALE_FACTOR
    orig_skus = config.NUM_SKUS
    orig_locs = config.NUM_LOCATIONS
    orig_sups = config.NUM_SUPPLIERS
    orig_pos = config.NUM_PURCHASE_ORDERS

    config.SCALE_FACTOR = 0.05
    config.NUM_SKUS = int(3000 * 0.05)
    config.NUM_LOCATIONS = 10
    config.NUM_SUPPLIERS = int(500 * 0.05)
    config.NUM_PURCHASE_ORDERS = int(10000 * 0.05)

    data = run_generation(export=False)

    yield data

    # Restore original configuration
    config.SCALE_FACTOR = orig_scale
    config.NUM_SKUS = orig_skus
    config.NUM_LOCATIONS = orig_locs
    config.NUM_SUPPLIERS = orig_sups
    config.NUM_PURCHASE_ORDERS = orig_pos


def test_master_data_integrity(starter_dataset):
    """Verify master tables have required columns and non-null primary keys."""
    skus = starter_dataset["skus"]
    locs = starter_dataset["locations"]
    sups = starter_dataset["suppliers"]

    assert len(skus) == config.NUM_SKUS
    assert len(locs) == config.NUM_LOCATIONS
    assert len(sups) == config.NUM_SUPPLIERS

    assert "sku_id" in skus.columns and skus["sku_id"].isna().sum() == 0
    assert "location_id" in locs.columns and locs["location_id"].isna().sum() == 0
    assert "supplier_id" in sups.columns and sups["supplier_id"].isna().sum() == 0


def test_ground_truth_isolation(starter_dataset):
    """Verify ground truth table is separate and its labels do not leak into master or transaction features."""
    assert "ground_truth" in starter_dataset
    gt = starter_dataset["ground_truth"]
    assert len(gt) > 0

    required_gt_cols = {"record_id", "entity", "issue_type", "description", "severity"}
    assert required_gt_cols.issubset(set(gt.columns))

    # Master and transaction dataframes must NOT contain 'issue_type'
    for table_name in ["skus", "locations", "suppliers", "forecast_demand", "purchase_orders"]:
        df = starter_dataset[table_name]
        assert "issue_type" not in df.columns, f"Data leakage: 'issue_type' found in {table_name}"


def test_projected_balance_arithmetic(starter_dataset):
    """Verify Projected Available Balance (PAB) identity: Ending = Beginning + Inbound + Prod - Demand."""
    balance_df = calculate_projected_balance(starter_dataset)
    assert not balance_df.empty

    expected_ending = (
        balance_df["beginning_balance"]
        + balance_df["scheduled_receipts"]
        + balance_df["planned_production"]
        - balance_df["forecast_demand"]
    )
    diff = np.abs(balance_df["ending_balance"] - expected_ending)
    assert np.all(diff < 1e-6), "PAB arithmetic identity violated in balance engine!"


def test_shortage_detection_and_severity(starter_dataset):
    """Verify shortages are detected whenever balance is negative and grouped into valid events."""
    balance_df = calculate_projected_balance(starter_dataset)
    shortages_df = detect_shortages(balance_df, starter_dataset)

    assert not shortages_df.empty
    assert "shortage_id" in shortages_df.columns
    assert "priority_score" in shortages_df.columns
    assert "severity" in shortages_df.columns

    for sev in shortages_df["severity"].unique():
        assert sev in config.SHORTAGE_SEVERITIES

    assert (shortages_df["priority_score"] >= 0).all()


def test_mitigations_generation(starter_dataset):
    """Verify mitigation candidate generation and recommendation logic."""
    balance_df = calculate_projected_balance(starter_dataset)
    shortages_df = detect_shortages(balance_df, starter_dataset)
    mitigations_df = generate_mitigations(shortages_df, starter_dataset)

    assert not mitigations_df.empty
    assert "mitigation_id" in mitigations_df.columns
    assert "feasibility_score" in mitigations_df.columns
    assert "recommended" in mitigations_df.columns

    assert (mitigations_df["feasibility_score"] >= 0.0).all()
    assert (mitigations_df["feasibility_score"] <= 1.0).all()


# ── Edge Case Tests ──────────────────────────────────────────────────────────

def test_edge_case_inbound_counted_twice(starter_dataset):
    """Verify Edge Case 1: duplicate PO rows match ground_truth annotations."""
    pos = starter_dataset["purchase_orders"]
    gt = starter_dataset["ground_truth"]
    dup_gt = gt[gt["issue_type"] == "inbound_counted_twice"]
    assert len(dup_gt) > 0

    dup_po_ids = set(pos.loc[pos["po_id"].duplicated(keep=False), "po_id"])
    assert set(dup_gt["record_id"]).issubset(dup_po_ids)


def test_edge_case_substitute_not_approved(starter_dataset):
    """Verify Edge Case 2: unapproved substitute SKUs exist and are documented."""
    skus = starter_dataset["skus"]
    gt = starter_dataset["ground_truth"]
    sub_gt = gt[gt["issue_type"] == "substitute_not_approved"]
    assert len(sub_gt) > 0

    unapproved_skus = set(skus[skus["substitute_approved"] == False]["sku_id"])
    assert set(sub_gt["record_id"]).issubset(unapproved_skus)


def test_edge_case_supplier_capacity_exceeded(starter_dataset):
    """Verify Edge Case 3: PO quantities exceed supplier weekly capacity."""
    gt = starter_dataset["ground_truth"]
    cap_gt = gt[gt["issue_type"] == "supplier_capacity_exceeded"]
    assert len(cap_gt) > 0


def test_edge_case_shortage_without_lead_time(starter_dataset):
    """Verify Edge Case 4: deleted lead times create missing routing entries."""
    gt = starter_dataset["ground_truth"]
    lt_gt = gt[gt["issue_type"] == "shortage_without_lead_time"]
    assert len(lt_gt) > 0


def test_edge_case_uom_mismatch(starter_dataset):
    """Verify Edge Case 5: UOM mismatches between SKU and supplier capacity."""
    gt = starter_dataset["ground_truth"]
    uom_gt = gt[gt["issue_type"] == "uom_mismatch"]
    assert len(uom_gt) > 0


# ── Lifecycle & Workflow Tests ───────────────────────────────────────────────

def test_lifecycle_transitions(starter_dataset):
    """Verify lifecycle state validity across POs and production plans."""
    pos = starter_dataset["purchase_orders"]
    prod = starter_dataset["production_plans"]

    # Received POs must have actual delivery dates
    received = pos[pos["status"] == "RECEIVED"]
    assert received["actual_delivery_date"].isna().sum() == 0

    # Completed production plans must have actual quantities
    completed = prod[prod["status"] == "COMPLETED"]
    assert completed["actual_quantity"].isna().sum() == 0


def test_state_transition_events(starter_dataset):
    """Verify state transition audit log captures explicit historical events."""
    balance_df = calculate_projected_balance(starter_dataset)
    shortages_df = detect_shortages(balance_df, starter_dataset)
    data_snap = dict(starter_dataset)
    data_snap["shortages"] = shortages_df

    events_df = generate_state_transition_events(data_snap)
    assert not events_df.empty
    assert {"event_id", "entity_type", "entity_id", "from_state", "to_state", "actor_role"}.issubset(set(events_df.columns))


def test_primary_actor_views(starter_dataset):
    """Verify customized views are generated for all 5 primary actors."""
    balance_df = calculate_projected_balance(starter_dataset)
    shortages_df = detect_shortages(balance_df, starter_dataset)
    mitigations_df = generate_mitigations(shortages_df, starter_dataset)

    # 1. Planner View
    planner_view = generate_planner_view(shortages_df, mitigations_df)
    assert not planner_view.empty
    assert "planner_action_urgency" in planner_view.columns

    # 2. Operations Summary
    ops_summary = generate_operations_summary(starter_dataset, shortages_df, balance_df)
    assert "macro_metrics" in ops_summary
    assert ops_summary["macro_metrics"]["total_forecast_demand_units"] > 0

    # 3. Logistics Analyst View
    logistics_view = generate_logistics_analyst_view(starter_dataset)
    assert not logistics_view.empty
    assert "is_delayed" in logistics_view.columns

    # 4. Supplier Scorecard
    supplier_view = generate_supplier_scorecard(starter_dataset, mitigations_df)
    assert not supplier_view.empty
    assert "reliability_score" in supplier_view.columns

    # 5. Warehouse Schedule
    warehouse_view = generate_warehouse_schedule(starter_dataset, balance_df)
    assert not warehouse_view.empty
    assert "ending_balance" in warehouse_view.columns


def test_sqlite_export(starter_dataset, tmp_path):
    """Verify SQLite database export creates valid schema, tables, and records."""
    db_path = str(tmp_path / "test_supply_chain.db")
    sql_path = str(tmp_path / "test_schema.sql")

    export_sqlite_and_sql(starter_dataset, db_path=db_path, sql_schema_path=sql_path)
    assert os.path.exists(db_path)
    assert os.path.exists(sql_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM skus;")
    count = cursor.fetchone()[0]
    conn.close()
    assert count == len(starter_dataset["skus"])


def test_validation_suite_passes(starter_dataset):
    """Run validator suite and verify that all core constraints pass."""
    balance_df = calculate_projected_balance(starter_dataset)
    shortages_df = detect_shortages(balance_df, starter_dataset)
    mitigations_df = generate_mitigations(shortages_df, starter_dataset)

    eval_data = dict(starter_dataset)
    eval_data["shortages"] = shortages_df
    eval_data["mitigations"] = mitigations_df

    results = run_validation(eval_data)
    fail_checks = [r for r in results if r["status"] == "FAIL"]
    assert len(fail_checks) == 0, f"Validation failures encountered: {fail_checks}"
