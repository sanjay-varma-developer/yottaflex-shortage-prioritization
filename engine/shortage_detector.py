"""
Shortage Detector – identifies and prioritises shortages from the
Projected Available Balance (PAB) output.

Consecutive shortage weeks for the same (sku_id, location_id) are merged
into a single shortage event.  Each event is scored for severity and
root-cause analysis is attached.
"""

import os
import sys
import datetime

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def _group_consecutive_shortages(shortage_rows: pd.DataFrame) -> pd.DataFrame:
    """
    Collapse consecutive shortage weeks for each (sku_id, location_id)
    into contiguous events.

    Parameters
    ----------
    shortage_rows : pd.DataFrame
        Subset of balance_df where is_shortage is True, must contain
        sku_id, location_id, week, ending_balance columns.

    Returns
    -------
    pd.DataFrame
        One row per shortage event with first/last week, duration,
        shortage_quantity (abs of most negative balance), peak week, etc.
    """
    if shortage_rows.empty:
        return pd.DataFrame(columns=[
            "sku_id", "location_id", "first_shortage_week",
            "last_shortage_week", "duration_weeks", "shortage_quantity",
            "peak_shortage_week", "peak_shortage_qty",
        ])

    df = shortage_rows.sort_values(["sku_id", "location_id", "week"]).copy()

    # Detect breaks in consecutive weeks within each (sku, loc) group.
    # A new event starts whenever the week is not exactly previous_week + 1.
    df["prev_week"] = df.groupby(["sku_id", "location_id"])["week"].shift(1)
    df["new_event"] = (
        df["prev_week"].isna() | (df["week"] != df["prev_week"] + 1)
    ).astype(int)
    df["event_group"] = df.groupby(["sku_id", "location_id"])["new_event"].cumsum()

    group_keys = ["sku_id", "location_id", "event_group"]
    events = df.groupby(group_keys, as_index=False).agg(
        first_shortage_week=("week", "min"),
        last_shortage_week=("week", "max"),
        duration_weeks=("week", "count"),
        shortage_quantity=("ending_balance", lambda s: abs(s.min())),
        peak_shortage_qty=("ending_balance", lambda s: abs(s.min())),
        peak_shortage_week=("ending_balance", lambda s: s.idxmin()),
    )

    # Resolve peak_shortage_week from positional index back to the week value
    events["peak_shortage_week"] = df.loc[events["peak_shortage_week"], "week"].values

    events = events.drop(columns=["event_group"])
    return events


def _assign_severity(events: pd.DataFrame) -> pd.Series:
    """
    Assign shortage severity based on config.SHORTAGE_SEVERITIES.

    Rules (evaluated top-down, first match wins):
      CRITICAL : shortage_qty > 1000  OR  duration > 8
      HIGH     : shortage_qty > 500   OR  duration > 4
      MEDIUM   : shortage_qty > 100   OR  duration > 2
      LOW      : everything else
    """
    conditions = [
        (events["shortage_quantity"] > 1000) | (events["duration_weeks"] > 8),
        (events["shortage_quantity"] > 500)  | (events["duration_weeks"] > 4),
        (events["shortage_quantity"] > 100)  | (events["duration_weeks"] > 2),
    ]
    choices = ["CRITICAL", "HIGH", "MEDIUM"]
    return pd.Series(
        np.select(conditions, choices, default="LOW"),
        index=events.index,
    )


def _compute_priority_score(events: pd.DataFrame) -> pd.Series:
    """
    Priority score = shortage_quantity × duration_weeks × sku_unit_cost.
    Higher = more urgent.
    """
    return (
        events["shortage_quantity"]
        * events["duration_weeks"]
        * events["sku_unit_cost"]
    )


def _determine_root_causes(
    events: pd.DataFrame,
    balance_df: pd.DataFrame,
    data: dict,
) -> pd.Series:
    """
    Analyse each shortage event and assign a primary root-cause label.

    Root-cause rules (first applicable match per event):
      DEMAND_SPIKE           – promotional demand in the shortage weeks
      SUPPLY_DELAY           – delayed POs exist for that SKU-location
      CAPACITY_CONSTRAINT    – supplier weekly capacity < demand
      LOW_INITIAL_INVENTORY  – starting inventory < 2 weeks of demand
      PRODUCTION_SHORTFALL   – planned production < demand at PLANT locations
    """
    # Pre-compute helper lookups -------------------------------------------------

    # 1. Promotional demand weeks per (sku, loc)
    fd = data["forecast_demand"]
    promo_weeks = (
        fd[fd["demand_type"] == "PROMOTIONAL"]
        .groupby(["sku_id", "location_id"])["week"]
        .apply(set)
    )

    # 2. Delayed POs: actual > expected or status IN_TRANSIT past expected
    po = data["purchase_orders"].copy()
    po["expected_delivery_date"] = pd.to_datetime(po["expected_delivery_date"])
    if "actual_delivery_date" in po.columns:
        po["actual_delivery_date"] = pd.to_datetime(po["actual_delivery_date"], errors="coerce")
        delayed_mask = (
            (po["actual_delivery_date"] > po["expected_delivery_date"])
            | ((po["status"] == "IN_TRANSIT") & (po["expected_delivery_date"] < pd.Timestamp.now()))
        )
    else:
        delayed_mask = (
            (po["status"] == "IN_TRANSIT")
            & (po["expected_delivery_date"] < pd.Timestamp.now())
        )
    delayed_pairs = set(
        po.loc[delayed_mask, ["sku_id", "location_id"]]
        .apply(tuple, axis=1)
    )

    # 3. Supplier capacity per SKU (summed across all suppliers)
    sc = data["supplier_capacities"]
    supplier_cap_by_sku = (
        sc[sc["status"] == "ACTIVE"]
        .groupby("sku_id")["max_weekly_capacity"]
        .sum()
    )

    # 4. Average weekly demand per (sku, loc)
    avg_demand = (
        fd.groupby(["sku_id", "location_id"])["quantity"]
        .mean()
    )

    # 5. Initial inventory
    inv = data["inventory"].set_index(["sku_id", "location_id"])["on_hand_qty"]

    # 6. Plant locations
    plant_locs = set(
        data["locations"][data["locations"]["type"] == "PLANT"]["location_id"]
    )

    # 7. Production totals per (sku, loc)
    pp = data["production_plans"]
    prod_total = (
        pp.groupby(["sku_id", "location_id"])["planned_quantity"].sum()
    )
    demand_total = (
        fd.groupby(["sku_id", "location_id"])["quantity"].sum()
    )

    # Iterate once to assign root causes ------------------------------------------
    root_causes = []
    for _, row in events.iterrows():
        sku = row["sku_id"]
        loc = row["location_id"]
        first_w = row["first_shortage_week"]
        last_w = row["last_shortage_week"]
        shortage_weeks_set = set(range(first_w, last_w + 1))

        # Check DEMAND_SPIKE
        pw = promo_weeks.get((sku, loc), set())
        if pw & shortage_weeks_set:
            root_causes.append("DEMAND_SPIKE")
            continue

        # Check SUPPLY_DELAY
        if (sku, loc) in delayed_pairs:
            root_causes.append("SUPPLY_DELAY")
            continue

        # Check CAPACITY_CONSTRAINT
        cap = supplier_cap_by_sku.get(sku, 0)
        avg_d = avg_demand.get((sku, loc), 0)
        if cap > 0 and cap < avg_d:
            root_causes.append("CAPACITY_CONSTRAINT")
            continue

        # Check LOW_INITIAL_INVENTORY
        init_inv = inv.get((sku, loc), 0)
        if avg_d > 0 and init_inv < 2 * avg_d:
            root_causes.append("LOW_INITIAL_INVENTORY")
            continue

        # Check PRODUCTION_SHORTFALL (only at plants)
        if loc in plant_locs:
            prod = prod_total.get((sku, loc), 0)
            dem = demand_total.get((sku, loc), 0)
            if prod < dem:
                root_causes.append("PRODUCTION_SHORTFALL")
                continue

        # Default — pick the most common generic cause
        root_causes.append("LOW_INITIAL_INVENTORY")

    return pd.Series(root_causes, index=events.index)


def detect_shortages(balance_df: pd.DataFrame, data: dict) -> pd.DataFrame:
    """
    Detect, group, and prioritise shortages from the balance engine output.

    Parameters
    ----------
    balance_df : pd.DataFrame
        Output of ``calculate_projected_balance`` — one row per
        (sku_id, location_id, week).
    data : dict
        Original input DataFrames (needed for root-cause analysis).

    Returns
    -------
    pd.DataFrame
        One row per shortage event with severity, priority_score,
        root_cause, and denormalised SKU attributes.
    """
    # 1. Filter shortage rows
    shortage_rows = balance_df[balance_df["is_shortage"]].copy()
    if shortage_rows.empty:
        cols = [
            "shortage_id", "sku_id", "location_id",
            "first_shortage_week", "last_shortage_week", "duration_weeks",
            "shortage_quantity", "peak_shortage_week", "peak_shortage_qty",
            "severity", "priority_score", "root_cause",
            "sku_category", "sku_unit_cost", "created_at",
        ]
        return pd.DataFrame(columns=cols)

    # 2. Group consecutive weeks into events
    events = _group_consecutive_shortages(shortage_rows)

    # 3. Denormalize SKU info
    sku_info = data["skus"][["sku_id", "category", "unit_cost"]].drop_duplicates("sku_id")
    events = events.merge(
        sku_info.rename(columns={"category": "sku_category", "unit_cost": "sku_unit_cost"}),
        on="sku_id",
        how="left",
    )
    events["sku_unit_cost"] = events["sku_unit_cost"].fillna(1.0)

    # 4. Severity
    events["severity"] = _assign_severity(events)

    # 5. Priority score
    events["priority_score"] = _compute_priority_score(events)

    # 6. Root cause
    events["root_cause"] = _determine_root_causes(events, balance_df, data)

    # 7. Assign IDs
    events = events.sort_values("priority_score", ascending=False).reset_index(drop=True)
    events["shortage_id"] = [config.shortage_id(i + 1) for i in range(len(events))]

    # 8. Timestamp
    events["created_at"] = datetime.datetime.now().isoformat()

    # 9. Final column order
    output_cols = [
        "shortage_id", "sku_id", "location_id",
        "first_shortage_week", "last_shortage_week", "duration_weeks",
        "shortage_quantity", "peak_shortage_week", "peak_shortage_qty",
        "severity", "priority_score", "root_cause",
        "sku_category", "sku_unit_cost", "created_at",
    ]
    return events[output_cols].reset_index(drop=True)
