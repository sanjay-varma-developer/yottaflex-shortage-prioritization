"""
Capacity data generators for Supplier Capacities and Lead Times.

These define what each supplier can produce/ship and how long it takes
to reach each location.
"""

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def generate_supplier_capacities(
    rng: np.random.RandomState,
    skus_df: pd.DataFrame,
    suppliers_df: pd.DataFrame,
) -> pd.DataFrame:
    """Generate supplier-SKU capacity records.

    Each active supplier is assigned 3-15 SKUs it can supply, with weekly
    capacity limits, minimum order quantities, and UOM.

    Parameters
    ----------
    rng : np.random.RandomState
    skus_df : pd.DataFrame  – SKU master (needs sku_id, category, uom)
    suppliers_df : pd.DataFrame – Supplier master (needs supplier_id, status, specialization)

    Returns
    -------
    pd.DataFrame
        Columns: supplier_capacity_id, supplier_id, sku_id, max_weekly_capacity,
        min_order_qty, uom, effective_from, effective_to, status.
    """
    active_suppliers = suppliers_df[suppliers_df["status"] == "ACTIVE"]
    sku_ids = skus_df["sku_id"].values
    sku_uoms = skus_df.set_index("sku_id")["uom"].to_dict()
    category_to_skus = skus_df.groupby("category")["sku_id"].apply(list).to_dict()

    # Determine which suppliers are constrained
    n_constrained = int(len(active_suppliers) * config.CONSTRAINED_SUPPLIER_FRACTION)
    constrained_indices = set(
        rng.choice(active_suppliers.index, size=n_constrained, replace=False)
    )

    records = []
    counter = 0

    for idx, row in active_suppliers.iterrows():
        num_skus = rng.randint(3, 16)  # 3-15 SKUs
        spec = row["specialization"]

        # Prefer SKUs from the supplier's specialization category, but mix in others
        preferred = category_to_skus.get(spec, [])
        if len(preferred) >= num_skus:
            chosen_skus = rng.choice(preferred, size=num_skus, replace=False)
        else:
            # Take all preferred + random others
            remaining_needed = num_skus - len(preferred)
            other_skus = [s for s in sku_ids if s not in set(preferred)]
            extras = rng.choice(other_skus, size=min(remaining_needed, len(other_skus)), replace=False)
            chosen_skus = np.concatenate([preferred, extras])[:num_skus]

        is_constrained = idx in constrained_indices

        for sku in chosen_skus:
            counter += 1
            if is_constrained:
                max_cap = int(rng.randint(20, 101))
            else:
                max_cap = int(rng.randint(50, 5001))

            min_oq = int(rng.randint(10, min(501, max_cap)))

            # UOM normally matches SKU; edge cases handled later in edge_cases.py
            uom = sku_uoms.get(sku, "EA")

            records.append(
                {
                    "supplier_capacity_id": config.supplier_capacity_id(counter),
                    "supplier_id": row["supplier_id"],
                    "sku_id": sku,
                    "max_weekly_capacity": max_cap,
                    "min_order_qty": min_oq,
                    "uom": uom,
                    "effective_from": pd.Timestamp("2026-01-01"),
                    "effective_to": pd.Timestamp("2026-12-31"),
                    "status": "ACTIVE",
                }
            )

    return pd.DataFrame(records)


def generate_lead_times(
    rng: np.random.RandomState,
    suppliers_df: pd.DataFrame,
    locations_df: pd.DataFrame,
) -> pd.DataFrame:
    """Generate supplier-to-location lead time records.

    Each active supplier has transit-time entries for 5-15 random locations.

    Parameters
    ----------
    rng : np.random.RandomState
    suppliers_df : pd.DataFrame
    locations_df : pd.DataFrame

    Returns
    -------
    pd.DataFrame
        Columns: lead_time_id, supplier_id, location_id, transit_days,
        transport_mode, effective_from, effective_to.
    """
    active_suppliers = suppliers_df[suppliers_df["status"] == "ACTIVE"]
    loc_ids = locations_df["location_id"].values

    # Transit-day ranges per mode
    transit_ranges = {
        "AIR": (3, 8),
        "ROAD": (5, 16),
        "RAIL": (10, 26),
        "SEA": (20, 46),
    }

    records = []
    counter = 0

    for _, row in active_suppliers.iterrows():
        num_locs = rng.randint(5, min(16, len(loc_ids) + 1))
        chosen_locs = rng.choice(loc_ids, size=num_locs, replace=False)

        for loc in chosen_locs:
            counter += 1
            mode = rng.choice(config.TRANSPORT_MODES)
            lo, hi = transit_ranges[mode]
            transit_days = int(rng.randint(lo, hi))

            records.append(
                {
                    "lead_time_id": config.lead_time_id(counter),
                    "supplier_id": row["supplier_id"],
                    "location_id": loc,
                    "transit_days": transit_days,
                    "transport_mode": mode,
                    "effective_from": pd.Timestamp("2026-01-01"),
                    "effective_to": pd.Timestamp("2026-12-31"),
                }
            )

    return pd.DataFrame(records)
