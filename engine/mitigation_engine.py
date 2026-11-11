"""
Mitigation Engine – generates 1-4 candidate mitigation options for each
detected shortage event.

Mitigation types considered:
  EXPEDITE_PO, ALTERNATE_SUPPLIER, SUBSTITUTE_SKU,
  INCREASE_PRODUCTION, REDISTRIBUTE_INVENTORY

Only applicable types are generated; the best option per shortage is
flagged as *recommended* based on a feasibility-adjusted cost metric.
"""

import os
import sys
import datetime

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


# ────────────────────────── helper look-ups ──────────────────────────────

def _build_lookups(data: dict) -> dict:
    """
    Pre-compute frequently-needed look-up structures from the input data
    to avoid repeated scans inside the per-shortage loop.

    Returns a dict of lookup objects.
    """
    rng = np.random.RandomState(config.RANDOM_SEED + 42)

    # POs grouped by (sku_id, location_id), only non-cancelled future orders
    po = data["purchase_orders"].copy()
    po["expected_delivery_date"] = pd.to_datetime(po["expected_delivery_date"])
    po = po[po["status"] != "CANCELLED"]
    po_groups = po.groupby(["sku_id", "location_id"])

    # Supplier capacities by sku_id (active only)
    sc = data["supplier_capacities"]
    sc_active = sc[sc["status"] == "ACTIVE"].copy()
    sc_by_sku = sc_active.groupby("sku_id")

    # Supplier info indexed by supplier_id
    sup = data["suppliers"].set_index("supplier_id")

    # Lead times indexed by (supplier_id, location_id)
    lt = data["lead_times"].copy()
    lt_idx = lt.set_index(["supplier_id", "location_id"])

    # SKU info indexed by sku_id
    sku_info = data["skus"].set_index("sku_id")

    # Inventory indexed by (sku_id, location_id)
    inv = data["inventory"].set_index(["sku_id", "location_id"])

    # Location info indexed by location_id
    loc_info = data["locations"].set_index("location_id")

    # Production plans by (sku_id, location_id)
    pp = data["production_plans"]
    pp_groups = pp.groupby(["sku_id", "location_id"])

    return {
        "rng": rng,
        "po": po,
        "po_groups": po_groups,
        "sc_by_sku": sc_by_sku,
        "sup": sup,
        "lt_idx": lt_idx,
        "sku_info": sku_info,
        "inv": inv,
        "loc_info": loc_info,
        "pp_groups": pp_groups,
        "sc_active": sc_active,
    }


# ────────────────────────── individual generators ────────────────────────

def _try_expedite_po(row, lookups) -> dict | None:
    """Generate an EXPEDITE_PO mitigation if pending POs exist."""
    rng = lookups["rng"]
    try:
        pos = lookups["po_groups"].get_group((row["sku_id"], row["location_id"]))
    except KeyError:
        return None

    # Consider POs that are OPEN or CONFIRMED (not yet received)
    candidates = pos[pos["status"].isin(["OPEN", "CONFIRMED", "IN_TRANSIT"])]
    if candidates.empty:
        return None

    # Pick the largest PO as candidate
    best = candidates.loc[candidates["quantity"].idxmax()]
    supplier_id = best["supplier_id"]

    # Get supplier reliability
    reliability = lookups["sup"].at[supplier_id, "reliability_score"] if supplier_id in lookups["sup"].index else 0.5

    # Estimate lead time reduction 30-50%
    lt_reduction_pct = rng.uniform(0.30, 0.50)
    original_lt = 14  # default fallback
    try:
        original_lt = lookups["lt_idx"].at[(supplier_id, row["location_id"]), "transit_days"]
        if isinstance(original_lt, pd.Series):
            original_lt = original_lt.iloc[0]
    except KeyError:
        pass
    new_lt = max(1, int(original_lt * (1 - lt_reduction_pct)))

    # Expediting premium 1.2–1.5×
    premium = rng.uniform(1.2, 1.5)
    unit_cost = row.get("sku_unit_cost", 1.0) * premium

    return {
        "mitigation_type": "EXPEDITE_PO",
        "description": (
            f"Expedite PO {best['po_id']} from supplier {supplier_id}. "
            f"Reduce lead time by {lt_reduction_pct:.0%} ({original_lt}→{new_lt} days) "
            f"with {premium:.1f}× cost premium."
        ),
        "estimated_qty": float(best["quantity"]),
        "estimated_cost_per_unit": round(unit_cost, 2),
        "estimated_total_cost": round(unit_cost * float(best["quantity"]), 2),
        "estimated_lead_time_days": new_lt,
        "feasibility_score": round(float(reliability), 2),
        "risk_factors": (
            "Supplier reliability below threshold"
            if reliability < 0.6
            else "Expedite cost premium applies"
        ),
    }


def _try_alternate_supplier(row, lookups) -> dict | None:
    """Generate an ALTERNATE_SUPPLIER mitigation if another supplier exists."""
    rng = lookups["rng"]
    sku = row["sku_id"]
    loc = row["location_id"]
    shortage_qty = row["shortage_quantity"]

    try:
        capacities = lookups["sc_by_sku"].get_group(sku)
    except KeyError:
        return None

    # Find suppliers for this SKU — pick one we don't already have a PO from
    existing_suppliers = set()
    try:
        pos = lookups["po_groups"].get_group((sku, loc))
        existing_suppliers = set(pos["supplier_id"].unique())
    except KeyError:
        pass

    alt = capacities[~capacities["supplier_id"].isin(existing_suppliers)]
    if alt.empty:
        # Fall back to any supplier
        alt = capacities
    if alt.empty:
        return None

    # Pick the supplier with the most capacity
    best_row = alt.loc[alt["max_weekly_capacity"].idxmax()]
    alt_supplier_id = best_row["supplier_id"]

    reliability = lookups["sup"].at[alt_supplier_id, "reliability_score"] if alt_supplier_id in lookups["sup"].index else 0.5
    certified = lookups["sup"].at[alt_supplier_id, "certified"] if alt_supplier_id in lookups["sup"].index else False

    est_qty = min(shortage_qty, float(best_row["max_weekly_capacity"]))

    # Lead time from alternate supplier
    alt_lt = 14
    try:
        alt_lt_val = lookups["lt_idx"].at[(alt_supplier_id, loc), "transit_days"]
        if isinstance(alt_lt_val, pd.Series):
            alt_lt_val = alt_lt_val.iloc[0]
        alt_lt = int(alt_lt_val)
    except KeyError:
        pass

    unit_cost = row.get("sku_unit_cost", 1.0) * rng.uniform(1.0, 1.3)

    feasibility = float(reliability) * (0.95 if certified else 0.70)
    feasibility = round(min(feasibility, 1.0), 2)

    return {
        "mitigation_type": "ALTERNATE_SUPPLIER",
        "description": (
            f"Source {est_qty:.0f} units from alternate supplier {alt_supplier_id} "
            f"(reliability {reliability:.2f}, certified={certified})."
        ),
        "estimated_qty": round(est_qty, 2),
        "estimated_cost_per_unit": round(unit_cost, 2),
        "estimated_total_cost": round(unit_cost * est_qty, 2),
        "estimated_lead_time_days": alt_lt,
        "feasibility_score": feasibility,
        "risk_factors": (
            "Alternate supplier not certified"
            if not certified
            else "Lead time may vary"
        ),
    }


def _try_substitute_sku(row, lookups) -> dict | None:
    """Generate a SUBSTITUTE_SKU mitigation if a substitute exists."""
    rng = lookups["rng"]
    sku = row["sku_id"]
    loc = row["location_id"]

    if sku not in lookups["sku_info"].index:
        return None

    sku_row = lookups["sku_info"].loc[sku]
    sub_sku = sku_row.get("substitute_sku_id")
    if pd.isna(sub_sku) or sub_sku is None or str(sub_sku).strip() == "":
        return None

    sub_approved = bool(sku_row.get("substitute_approved", False))

    # Check inventory of substitute at this location
    sub_inv = 0.0
    if (sub_sku, loc) in lookups["inv"].index:
        sub_inv_row = lookups["inv"].loc[(sub_sku, loc)]
        if isinstance(sub_inv_row, pd.DataFrame):
            sub_inv = float(sub_inv_row["on_hand_qty"].iloc[0])
        else:
            sub_inv = float(sub_inv_row["on_hand_qty"])

    est_qty = min(row["shortage_quantity"], max(sub_inv, 0))
    if est_qty <= 0:
        est_qty = row["shortage_quantity"] * 0.5  # partial cover estimate

    sub_unit_cost = row.get("sku_unit_cost", 1.0)
    if sub_sku in lookups["sku_info"].index:
        sub_unit_cost = float(lookups["sku_info"].at[sub_sku, "unit_cost"])

    if sub_approved:
        feasibility = round(rng.uniform(0.7, 0.9), 2)
    else:
        feasibility = 0.0

    risk = "substitute_not_approved" if not sub_approved else "Substitute may have different specs"

    return {
        "mitigation_type": "SUBSTITUTE_SKU",
        "description": (
            f"Use substitute SKU {sub_sku} (approved={sub_approved}). "
            f"Available inventory: {sub_inv:.0f} units."
        ),
        "estimated_qty": round(est_qty, 2),
        "estimated_cost_per_unit": round(sub_unit_cost, 2),
        "estimated_total_cost": round(sub_unit_cost * est_qty, 2),
        "estimated_lead_time_days": 0,
        "feasibility_score": feasibility,
        "risk_factors": risk,
    }


def _try_increase_production(row, lookups) -> dict | None:
    """Generate an INCREASE_PRODUCTION mitigation for PLANT locations."""
    rng = lookups["rng"]
    loc = row["location_id"]

    if loc not in lookups["loc_info"].index:
        return None

    loc_row = lookups["loc_info"].loc[loc]
    if loc_row.get("type") != "PLANT":
        return None

    sku = row["sku_id"]

    # Look at existing production plans for capacity utilisation
    avg_util = 70.0
    try:
        pp = lookups["pp_groups"].get_group((sku, loc))
        avg_util = pp["capacity_utilized_pct"].mean()
    except KeyError:
        pass

    remaining_capacity_pct = max(0, 100 - avg_util)
    # Estimate additional qty as fraction of shortage
    est_qty = row["shortage_quantity"] * (remaining_capacity_pct / 100.0)
    if est_qty <= 0:
        est_qty = row["shortage_quantity"] * 0.1  # at least try 10%

    unit_cost = row.get("sku_unit_cost", 1.0) * 1.1  # overtime premium

    feasibility = round(min(remaining_capacity_pct / 100.0 + 0.2, 1.0), 2)
    if remaining_capacity_pct < 5:
        feasibility = round(rng.uniform(0.1, 0.3), 2)

    return {
        "mitigation_type": "INCREASE_PRODUCTION",
        "description": (
            f"Increase production at plant {loc}. "
            f"Current avg utilisation {avg_util:.0f}%, "
            f"remaining capacity ≈{remaining_capacity_pct:.0f}%."
        ),
        "estimated_qty": round(est_qty, 2),
        "estimated_cost_per_unit": round(unit_cost, 2),
        "estimated_total_cost": round(unit_cost * est_qty, 2),
        "estimated_lead_time_days": int(rng.randint(3, 14)),
        "feasibility_score": feasibility,
        "risk_factors": (
            "Limited remaining capacity"
            if remaining_capacity_pct < 20
            else "Overtime / shift premium applies"
        ),
    }


def _try_redistribute_inventory(row, lookups) -> dict | None:
    """Generate a REDISTRIBUTE_INVENTORY mitigation from excess at other locations."""
    rng = lookups["rng"]
    sku = row["sku_id"]
    loc = row["location_id"]

    inv = lookups["inv"]
    # Find all locations that stock this SKU (excluding current)
    if sku not in inv.index.get_level_values(0):
        return None

    sku_inv = inv.xs(sku, level="sku_id")
    if isinstance(sku_inv, pd.Series):
        # Only one location
        return None

    other_locs = sku_inv.drop(loc, errors="ignore")
    if other_locs.empty:
        return None

    # Find locations with excess (on_hand > safety_stock)
    if isinstance(other_locs, pd.DataFrame):
        other_locs = other_locs.copy()
        other_locs["excess"] = other_locs["on_hand_qty"] - other_locs["safety_stock_qty"]
        excess_locs = other_locs[other_locs["excess"] > 0]
    else:
        return None

    if excess_locs.empty:
        return None

    total_excess = excess_locs["excess"].sum()
    est_qty = min(row["shortage_quantity"], total_excess)
    if est_qty <= 0:
        return None

    # Source location (highest excess)
    source_loc = excess_locs["excess"].idxmax()

    transit_days = int(rng.randint(3, 8))
    transport_cost_per_unit = rng.uniform(0.5, 3.0)

    return {
        "mitigation_type": "REDISTRIBUTE_INVENTORY",
        "description": (
            f"Transfer {est_qty:.0f} units of {sku} from {source_loc}. "
            f"Total excess at other locations: {total_excess:.0f} units."
        ),
        "estimated_qty": round(est_qty, 2),
        "estimated_cost_per_unit": round(transport_cost_per_unit, 2),
        "estimated_total_cost": round(transport_cost_per_unit * est_qty, 2),
        "estimated_lead_time_days": transit_days,
        "feasibility_score": round(rng.uniform(0.6, 0.8), 2),
        "risk_factors": "Inter-location transit risk; demand at source may change",
    }


# ────────────────────────── main entry point ─────────────────────────────

_GENERATORS = [
    _try_expedite_po,
    _try_alternate_supplier,
    _try_substitute_sku,
    _try_increase_production,
    _try_redistribute_inventory,
]


def generate_mitigations(shortages_df: pd.DataFrame, data: dict) -> pd.DataFrame:
    """
    Generate 1-4 candidate mitigation options for every shortage event.

    Parameters
    ----------
    shortages_df : pd.DataFrame
        Output of ``detect_shortages`` — one row per shortage event.
    data : dict
        Original input DataFrames.

    Returns
    -------
    pd.DataFrame
        One row per mitigation option with type, cost, feasibility, etc.
    """
    output_cols = [
        "mitigation_id", "shortage_id",
        "mitigation_type", "description",
        "estimated_qty", "estimated_cost_per_unit", "estimated_total_cost",
        "estimated_lead_time_days",
        "feasibility_score", "risk_factors",
        "recommended", "created_at",
    ]

    if shortages_df.empty:
        return pd.DataFrame(columns=output_cols)

    lookups = _build_lookups(data)
    now_iso = datetime.datetime.now().isoformat()

    all_mitigations: list[dict] = []

    for _, shortage_row in shortages_df.iterrows():
        shortage_id = shortage_row["shortage_id"]
        options: list[dict] = []
        seq = 0

        for gen_fn in _GENERATORS:
            if seq >= config.MAX_MITIGATIONS_PER_SHORTAGE:
                break
            result = gen_fn(shortage_row, lookups)
            if result is not None:
                seq += 1
                result["mitigation_id"] = config.mitigation_id(shortage_id, seq)
                result["shortage_id"] = shortage_id
                result["recommended"] = False
                result["created_at"] = now_iso
                options.append(result)

        # Mark the best option as recommended (highest feasibility / lowest cost)
        if options:
            best_idx = max(
                range(len(options)),
                key=lambda i: (
                    options[i]["feasibility_score"]
                    / max(options[i]["estimated_cost_per_unit"], 0.01)
                ),
            )
            options[best_idx]["recommended"] = True
            all_mitigations.extend(options)

    result_df = pd.DataFrame(all_mitigations)
    if result_df.empty:
        return pd.DataFrame(columns=output_cols)

    # Ensure column order; some columns may be missing if no mitigations
    for col in output_cols:
        if col not in result_df.columns:
            result_df[col] = None

    return result_df[output_cols].reset_index(drop=True)
