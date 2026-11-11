"""
Edge-case injection module.

Injects five categories of data-quality anomalies into the generated
DataFrames and returns a labelled ground-truth table so the detection
engine can be scored against known issues.
"""

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def inject_edge_cases(
    rng: np.random.RandomState,
    all_data: dict,
) -> tuple:
    """Inject controlled data-quality anomalies and return ground-truth labels.

    Parameters
    ----------
    rng : np.random.RandomState
    all_data : dict
        Keys are table names ("skus", "suppliers", "purchase_orders",
        "supplier_capacities", "lead_times", "forecast_demand",
        "inventory", "production_plans", "sku_location_mapping") mapping
        to pandas DataFrames.  Modified **in-place**.

    Returns
    -------
    tuple[dict, pd.DataFrame]
        The (possibly modified) ``all_data`` dict and a ``ground_truth_df``
        with columns: record_id, entity, issue_type, description,
        affected_field, original_value, injected_value, severity.
    """
    gt_records: list[dict] = []
    rates = config.EDGE_CASE_RATES

    # ──────────────────────────────────────────────────────────────
    # 1. inbound_counted_twice — duplicate some PO rows
    # ──────────────────────────────────────────────────────────────
    po_df = all_data["purchase_orders"]
    n_dup = max(1, int(len(po_df) * rates["inbound_counted_twice"]))
    dup_idx = rng.choice(po_df.index, size=n_dup, replace=False)
    dup_rows = po_df.loc[dup_idx].copy()

    for idx in dup_idx:
        row = po_df.loc[idx]
        gt_records.append(
            {
                "record_id": row["po_id"],
                "entity": "purchase_orders",
                "issue_type": "inbound_counted_twice",
                "description": (
                    f"PO {row['po_id']} duplicated — risk of double-counting "
                    f"inbound qty {row['quantity']}"
                ),
                "affected_field": "po_id",
                "original_value": str(row["po_id"]),
                "injected_value": str(row["po_id"]),
                "severity": "HIGH",
            }
        )

    all_data["purchase_orders"] = pd.concat(
        [po_df, dup_rows], ignore_index=True
    )

    # ──────────────────────────────────────────────────────────────
    # 2. substitute_not_approved
    # ──────────────────────────────────────────────────────────────
    skus_df = all_data["skus"]
    has_sub = skus_df[skus_df["substitute_sku_id"].notna()].index
    n_not_approved = max(1, int(len(has_sub) * rates["substitute_not_approved"]))
    chosen_sub = rng.choice(has_sub, size=n_not_approved, replace=False)

    for idx in chosen_sub:
        orig = skus_df.at[idx, "substitute_approved"]
        skus_df.at[idx, "substitute_approved"] = False
        gt_records.append(
            {
                "record_id": skus_df.at[idx, "sku_id"],
                "entity": "skus",
                "issue_type": "substitute_not_approved",
                "description": (
                    f"SKU {skus_df.at[idx, 'sku_id']} substitute "
                    f"{skus_df.at[idx, 'substitute_sku_id']} marked not approved"
                ),
                "affected_field": "substitute_approved",
                "original_value": str(orig),
                "injected_value": "False",
                "severity": "MEDIUM",
            }
        )
    all_data["skus"] = skus_df

    # ──────────────────────────────────────────────────────────────
    # 3. supplier_capacity_exceeded — PO qty > max_weekly_capacity
    # ──────────────────────────────────────────────────────────────
    po_df = all_data["purchase_orders"]
    sc_df = all_data["supplier_capacities"]
    n_exceed = max(1, int(len(sc_df) * rates["supplier_capacity_exceeded"]))

    # Build a map from (supplier, sku) → max_weekly_capacity
    cap_map = sc_df.set_index(["supplier_id", "sku_id"])["max_weekly_capacity"].to_dict()

    # Find POs where we can inflate quantity
    po_with_cap = po_df.copy()
    po_with_cap["_cap"] = [
        cap_map.get((s, k), None)
        for s, k in zip(po_with_cap["supplier_id"], po_with_cap["sku_id"])
    ]
    eligible = po_with_cap.dropna(subset=["_cap"]).index.tolist()

    n_exceed = min(n_exceed, len(eligible))
    if n_exceed > 0:
        chosen_exceed = rng.choice(eligible, size=n_exceed, replace=False)
        for idx in chosen_exceed:
            orig_qty = po_df.at[idx, "quantity"]
            cap_val = cap_map.get(
                (po_df.at[idx, "supplier_id"], po_df.at[idx, "sku_id"]), orig_qty
            )
            # Set qty to 1.5-3× the capacity
            new_qty = int(cap_val * rng.uniform(1.5, 3.0))
            po_df.at[idx, "quantity"] = new_qty
            po_df.at[idx, "total_cost"] = round(new_qty * po_df.at[idx, "unit_cost"], 2)

            gt_records.append(
                {
                    "record_id": po_df.at[idx, "po_id"],
                    "entity": "purchase_orders",
                    "issue_type": "supplier_capacity_exceeded",
                    "description": (
                        f"PO {po_df.at[idx, 'po_id']} qty {new_qty} exceeds "
                        f"supplier max capacity {cap_val}"
                    ),
                    "affected_field": "quantity",
                    "original_value": str(orig_qty),
                    "injected_value": str(new_qty),
                    "severity": "HIGH",
                }
            )
    all_data["purchase_orders"] = po_df

    # ──────────────────────────────────────────────────────────────
    # 4. shortage_without_lead_time — remove some lead-time records
    # ──────────────────────────────────────────────────────────────
    lt_df = all_data["lead_times"]
    n_remove = max(1, int(len(lt_df) * rates["shortage_without_lead_time"]))
    remove_idx = rng.choice(lt_df.index, size=n_remove, replace=False)

    for idx in remove_idx:
        row = lt_df.loc[idx]
        gt_records.append(
            {
                "record_id": row["lead_time_id"],
                "entity": "lead_times",
                "issue_type": "shortage_without_lead_time",
                "description": (
                    f"Lead-time record {row['lead_time_id']} removed — "
                    f"supplier {row['supplier_id']} → location {row['location_id']} "
                    f"has no transit data"
                ),
                "affected_field": "lead_time_id",
                "original_value": str(row["lead_time_id"]),
                "injected_value": "REMOVED",
                "severity": "CRITICAL",
            }
        )

    all_data["lead_times"] = lt_df.drop(index=remove_idx).reset_index(drop=True)

    # ──────────────────────────────────────────────────────────────
    # 5. uom_mismatch — change UOM in supplier_capacity to differ from SKU
    # ──────────────────────────────────────────────────────────────
    sc_df = all_data["supplier_capacities"]
    sku_uom_map = all_data["skus"].set_index("sku_id")["uom"].to_dict()
    n_mismatch = max(1, int(len(sc_df) * rates["uom_mismatch"]))
    mismatch_idx = rng.choice(sc_df.index, size=n_mismatch, replace=False)

    for idx in mismatch_idx:
        orig_uom = sc_df.at[idx, "uom"]
        sku = sc_df.at[idx, "sku_id"]
        sku_uom = sku_uom_map.get(sku, orig_uom)
        # Pick a *different* UOM
        other_uoms = [u for u in config.UNITS_OF_MEASURE if u != sku_uom]
        new_uom = rng.choice(other_uoms)
        sc_df.at[idx, "uom"] = new_uom

        gt_records.append(
            {
                "record_id": sc_df.at[idx, "supplier_capacity_id"],
                "entity": "supplier_capacities",
                "issue_type": "uom_mismatch",
                "description": (
                    f"Supplier capacity {sc_df.at[idx, 'supplier_capacity_id']} "
                    f"UOM {new_uom} ≠ SKU {sku} UOM {sku_uom}"
                ),
                "affected_field": "uom",
                "original_value": str(orig_uom),
                "injected_value": str(new_uom),
                "severity": "MEDIUM",
            }
        )

    all_data["supplier_capacities"] = sc_df

    # ── Build ground-truth DataFrame ──
    ground_truth_df = pd.DataFrame(gt_records)

    return all_data, ground_truth_df
