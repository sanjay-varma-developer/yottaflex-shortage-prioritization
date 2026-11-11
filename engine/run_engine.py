"""
Run Engine – orchestrates the three engine stages and exports results.

Usage::

    from engine.run_engine import run_engine
    results = run_engine(data)   # data is a dict of DataFrames

Or from the command line::

    python -m engine.run_engine          # loads CSVs from data/ dirs
"""

import os
import sys
import time

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

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
import json


def _ensure_output_dir() -> str:
    """Create the computed output directory if it doesn't exist and return its path."""
    os.makedirs(config.COMPUTED_DIR, exist_ok=True)
    return config.COMPUTED_DIR


def _print_summary(balance_df: pd.DataFrame, shortages_df: pd.DataFrame, mitigations_df: pd.DataFrame) -> None:
    """Print a concise summary of engine results to stdout."""
    print("\n" + "=" * 70)
    print("  YottaFlex Supply-Chain Engine — Run Summary")
    print("=" * 70)

    # Balance summary
    n_rows = len(balance_df)
    n_pairs = balance_df.groupby(["sku_id", "location_id"]).ngroups
    n_shortage_rows = balance_df["is_shortage"].sum()
    n_below_safety = balance_df["is_below_safety"].sum()
    print("\n  Projected Balance:")
    print(f"    Total rows            : {n_rows:>10,}")
    print(f"    SKU-location pairs    : {n_pairs:>10,}")
    print(f"    Shortage week-rows    : {n_shortage_rows:>10,}")
    print(f"    Below-safety rows     : {n_below_safety:>10,}")

    # Shortage summary
    n_shortages = len(shortages_df)
    if n_shortages > 0:
        severity_counts = shortages_df["severity"].value_counts().to_dict()
        root_cause_counts = shortages_df["root_cause"].value_counts().to_dict()
        print(f"\n  Shortages Detected      : {n_shortages:>10,}")
        print("    By severity:")
        for sev in config.SHORTAGE_SEVERITIES:
            print(f"      {sev:<12s}       : {severity_counts.get(sev, 0):>10,}")
        print("    By root cause:")
        for rc, cnt in sorted(root_cause_counts.items(), key=lambda x: -x[1]):
            print(f"      {rc:<24s}: {cnt:>10,}")
    else:
        print(f"\n  Shortages Detected      : {0:>10}")

    # Mitigation summary
    n_mits = len(mitigations_df)
    if n_mits > 0:
        type_counts = mitigations_df["mitigation_type"].value_counts().to_dict()
        n_recommended = mitigations_df["recommended"].sum()
        print(f"\n  Mitigations Generated   : {n_mits:>10,}")
        print(f"    Recommended           : {n_recommended:>10,}")
        print("    By type:")
        for mt, cnt in sorted(type_counts.items(), key=lambda x: -x[1]):
            print(f"      {mt:<24s}: {cnt:>10,}")
    else:
        print(f"\n  Mitigations Generated   : {0:>10}")

    print("\n" + "=" * 70 + "\n")


def run_engine(data: dict) -> dict:
    """
    Execute the full supply-chain shortage analysis pipeline.

    Steps:
      1. Calculate projected available balance (PAB).
      2. Detect and prioritise shortage events.
      3. Generate candidate mitigations for each shortage.
      4. Export results to CSV in the ``computed/`` directory.
      5. Print a human-readable summary.

    Parameters
    ----------
    data : dict
        Dictionary of DataFrames keyed by table name (skus, locations,
        suppliers, supplier_capacities, lead_times, forecast_demand,
        inventory, purchase_orders, production_plans).

    Returns
    -------
    dict
        Keys: ``projected_balance``, ``shortages``, ``mitigations`` —
        each mapping to the corresponding DataFrame.
    """
    out_dir = _ensure_output_dir()

    # ── Stage 1: Projected Balance ──────────────────────────────────────
    print("[Engine] Stage 1/3 — Calculating projected balance …")
    t0 = time.time()
    balance_df = calculate_projected_balance(data)
    t1 = time.time()
    print(f"[Engine]   ✓ {len(balance_df):,} rows in {t1 - t0:.1f}s")

    # ── Stage 2: Shortage Detection ─────────────────────────────────────
    print("[Engine] Stage 2/3 — Detecting shortages …")
    t0 = time.time()
    shortages_df = detect_shortages(balance_df, data)
    t1 = time.time()
    print(f"[Engine]   ✓ {len(shortages_df):,} shortage events in {t1 - t0:.1f}s")

    # ── Stage 3: Mitigation Generation ──────────────────────────────────
    print("[Engine] Stage 3/3 — Generating mitigations …")
    t0 = time.time()
    mitigations_df = generate_mitigations(shortages_df, data)
    t1 = time.time()
    print(f"[Engine]   ✓ {len(mitigations_df):,} mitigation options in {t1 - t0:.1f}s")

    # ── Export to CSV ───────────────────────────────────────────────────
    balance_path = os.path.join(out_dir, "projected_balance.csv")
    shortages_path = os.path.join(out_dir, "shortages.csv")
    mitigations_path = os.path.join(out_dir, "mitigations.csv")

    balance_df.to_csv(balance_path, index=False)
    shortages_df.to_csv(shortages_path, index=False)
    mitigations_df.to_csv(mitigations_path, index=False)

    # ── Stage 4: Event History & Audit Trail (Rule 4) ───────────────────
    print("[Engine] Stage 4/5 — Generating immutable state transition events …")
    engine_data_snapshot = dict(data)
    engine_data_snapshot["shortages"] = shortages_df
    events_df = generate_state_transition_events(engine_data_snapshot)
    events_path = os.path.join(config.TRANSACTION_DIR, "state_transition_events.csv")
    events_df.to_csv(events_path, index=False)
    print(f"[Engine]   ✓ {len(events_df):,} lifecycle events logged to {os.path.relpath(events_path, config.PROJECT_ROOT)}")

    # ── Stage 5: Primary Actor Views (Workflow Spec) ────────────────────
    print("[Engine] Stage 5/5 — Generating tailored Primary Actor views …")
    planner_df = generate_planner_view(shortages_df, mitigations_df)
    planner_path = os.path.join(out_dir, "planner_dashboard.csv")
    planner_df.to_csv(planner_path, index=False)

    logistics_df = generate_logistics_analyst_view(data)
    logistics_path = os.path.join(out_dir, "logistics_report.csv")
    logistics_df.to_csv(logistics_path, index=False)

    supplier_df = generate_supplier_scorecard(data, mitigations_df)
    supplier_path = os.path.join(out_dir, "supplier_scorecard.csv")
    supplier_df.to_csv(supplier_path, index=False)

    warehouse_df = generate_warehouse_schedule(data, balance_df)
    warehouse_path = os.path.join(out_dir, "warehouse_schedule.csv")
    warehouse_df.to_csv(warehouse_path, index=False)

    ops_summary = generate_operations_summary(data, shortages_df, balance_df)
    ops_path = os.path.join(out_dir, "operations_summary.json")
    with open(ops_path, "w") as f:
        json.dump(ops_summary, f, indent=2)

    print(f"[Engine]   ✓ 5 Actor reports exported to {out_dir}/ (Planner, Ops, Logistics, Supplier, Warehouse)")

    # ── Summary ─────────────────────────────────────────────────────────
    _print_summary(balance_df, shortages_df, mitigations_df)

    return {
        "projected_balance": balance_df,
        "shortages": shortages_df,
        "mitigations": mitigations_df,
        "state_transition_events": events_df,
        "planner_dashboard": planner_df,
        "logistics_report": logistics_df,
        "supplier_scorecard": supplier_df,
        "warehouse_schedule": warehouse_df,
        "operations_summary": ops_summary,
    }



# ── CLI entry point ─────────────────────────────────────────────────────

def _load_data_from_csvs() -> dict:
    """
    Load all required DataFrames from the data/ CSV files when running
    the engine standalone from the command line.
    """
    master = config.MASTER_DIR
    txn = config.TRANSACTION_DIR

    data = {
        "skus": pd.read_csv(os.path.join(master, "skus.csv")),
        "locations": pd.read_csv(os.path.join(master, "locations.csv")),
        "suppliers": pd.read_csv(os.path.join(master, "suppliers.csv")),
        "supplier_capacities": pd.read_csv(os.path.join(master, "supplier_capacities.csv")),
        "lead_times": pd.read_csv(os.path.join(master, "lead_times.csv")),
        "forecast_demand": pd.read_csv(os.path.join(txn, "forecast_demand.csv")),
        "inventory": pd.read_csv(os.path.join(txn, "inventory.csv")),
        "purchase_orders": pd.read_csv(os.path.join(txn, "purchase_orders.csv")),
        "production_plans": pd.read_csv(os.path.join(txn, "production_plans.csv")),
    }
    return data


if __name__ == "__main__":
    print("[Engine] Loading data from CSV files …")
    data = _load_data_from_csvs()
    results = run_engine(data)
