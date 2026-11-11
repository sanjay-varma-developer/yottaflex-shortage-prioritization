"""
Inventory data generator — on-hand inventory snapshot at week 0.

Intentionally under-stocks ~15 % of SKU-location pairs to trigger
shortages during the engine simulation.
"""

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def generate_inventory(
    rng: np.random.RandomState,
    sku_loc_df: pd.DataFrame,
    demand_df: pd.DataFrame,
) -> pd.DataFrame:
    """Generate initial on-hand inventory for every SKU-location pair.

    Parameters
    ----------
    rng : np.random.RandomState
    sku_loc_df : pd.DataFrame  – columns: sku_id, location_id
    demand_df : pd.DataFrame   – full forecast; used to compute avg weekly demand

    Returns
    -------
    pd.DataFrame
        Columns: inventory_id, sku_id, location_id, on_hand_qty,
        safety_stock_qty, reorder_point, uom, last_updated, status.
    """
    # ── Compute average weekly demand per (sku, location) ──
    avg_demand = (
        demand_df.groupby(["sku_id", "location_id"])["quantity"]
        .mean()
        .reset_index()
        .rename(columns={"quantity": "avg_weekly_demand"})
    )

    inv = sku_loc_df.merge(avg_demand, on=["sku_id", "location_id"], how="left")
    inv["avg_weekly_demand"] = inv["avg_weekly_demand"].fillna(100)  # fallback

    n = len(inv)

    # ── Decide which items are understocked (~15 %) ──
    low_mask = rng.random(n) < 0.15

    # Weeks-of-supply for on-hand
    wos = np.where(low_mask, rng.uniform(0.5, 1.5, size=n), rng.uniform(2, 8, size=n))
    on_hand = np.maximum(0, np.round(inv["avg_weekly_demand"].values * wos)).astype(int)

    # Safety stock: 2 weeks of avg demand
    safety_stock = np.round(
        inv["avg_weekly_demand"].values * config.SAFETY_STOCK_WEEKS
    ).astype(int)

    # Reorder point: safety stock + 1 week of demand (proxy for avg lead time demand)
    reorder_point = safety_stock + np.round(inv["avg_weekly_demand"].values).astype(int)

    # UOM — carry over from demand_df or default
    uom_map = demand_df.drop_duplicates(subset=["sku_id", "location_id"]).set_index(
        ["sku_id", "location_id"]
    )["uom"]
    inv_uom = (
        inv.set_index(["sku_id", "location_id"])
        .join(uom_map)
        .reset_index()["uom"]
        .fillna("EA")
    )

    ids = [config.inventory_id(i + 1) for i in range(n)]

    return pd.DataFrame(
        {
            "inventory_id": ids,
            "sku_id": inv["sku_id"].values,
            "location_id": inv["location_id"].values,
            "on_hand_qty": on_hand,
            "safety_stock_qty": safety_stock,
            "reorder_point": reorder_point,
            "uom": inv_uom.values,
            "last_updated": pd.Timestamp("2025-12-31"),
            "status": "AVAILABLE",
        }
    )
