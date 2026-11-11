"""
Balance Engine – calculates Projected Available Balance (PAB) for every
SKU-location pair across the 52-week horizon.

PAB(week_t) = PAB(week_{t-1})
             + Scheduled_Receipts(week_t)
             + Planned_Production(week_t)
             - Forecast_Demand(week_t)

The implementation is fully vectorized (groupby + cumsum) so that it
handles ~624 K rows in seconds rather than minutes.
"""

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def _build_week_grid(data: dict) -> pd.DataFrame:
    """
    Build the full Cartesian product of (sku_id, location_id) × weeks so
    that every SKU-location has a row for every week even when there is no
    demand, supply, or production in that week.

    Returns a DataFrame with columns: sku_id, location_id, week, year, week_label.
    """
    # Derive the universe of SKU-location pairs from forecast_demand (most
    # complete source) augmented with inventory records.
    demand_pairs = data["forecast_demand"][["sku_id", "location_id"]].drop_duplicates()
    inv_pairs = data["inventory"][["sku_id", "location_id"]].drop_duplicates()
    pairs = pd.concat([demand_pairs, inv_pairs]).drop_duplicates().reset_index(drop=True)

    weeks = np.arange(config.WEEK_START, config.WEEK_END + 1)
    week_df = pd.DataFrame({
        "week": weeks,
        "year": config.YEAR,
    })
    week_df["week_label"] = week_df["week"].apply(lambda w: f"{config.YEAR}W{w:02d}")

    # Cross join
    pairs["_key"] = 1
    week_df["_key"] = 1
    grid = pairs.merge(week_df, on="_key").drop(columns="_key")
    return grid


def _aggregate_scheduled_receipts(data: dict) -> pd.DataFrame:
    """
    Sum PO quantities per (sku_id, location_id, week) for orders that are
    NOT cancelled.  The week is derived from expected_delivery_date.
    """
    po = data["purchase_orders"].copy()
    po = po[po["status"] != "CANCELLED"]

    # Derive the ISO week from the expected delivery date
    po["expected_delivery_date"] = pd.to_datetime(po["expected_delivery_date"])
    po["week"] = po["expected_delivery_date"].dt.isocalendar().week.astype(int)

    receipts = (
        po.groupby(["sku_id", "location_id", "week"], as_index=False)["quantity"]
        .sum()
        .rename(columns={"quantity": "scheduled_receipts"})
    )
    return receipts


def _aggregate_planned_production(data: dict) -> pd.DataFrame:
    """
    Sum planned_quantity per (sku_id, location_id, week) for production
    plans whose status is COMPLETED or IN_PROGRESS.
    """
    pp = data["production_plans"].copy()
    pp = pp[pp["status"].isin(["COMPLETED", "IN_PROGRESS"])]

    production = (
        pp.groupby(["sku_id", "location_id", "week"], as_index=False)["planned_quantity"]
        .sum()
        .rename(columns={"planned_quantity": "planned_production"})
    )
    return production


def _aggregate_forecast_demand(data: dict) -> pd.DataFrame:
    """
    Sum forecast demand quantity per (sku_id, location_id, week).
    """
    fd = data["forecast_demand"].copy()
    demand = (
        fd.groupby(["sku_id", "location_id", "week"], as_index=False)["quantity"]
        .sum()
        .rename(columns={"quantity": "forecast_demand"})
    )
    return demand


def _get_initial_inventory(data: dict) -> pd.DataFrame:
    """
    Get on-hand quantity and safety stock per (sku_id, location_id) from
    inventory snapshot.
    """
    inv = data["inventory"][["sku_id", "location_id", "on_hand_qty", "safety_stock_qty"]].copy()
    # If there are duplicates, take the latest (they should already be unique)
    inv = inv.drop_duplicates(subset=["sku_id", "location_id"], keep="last")
    return inv


def calculate_projected_balance(data: dict) -> pd.DataFrame:
    """
    Calculate the Projected Available Balance (PAB) for every SKU-location
    pair, week by week over the planning horizon.

    Parameters
    ----------
    data : dict
        Dictionary of DataFrames keyed by table name (skus, locations,
        suppliers, forecast_demand, inventory, purchase_orders,
        production_plans, etc.).

    Returns
    -------
    pd.DataFrame
        One row per (sku_id, location_id, week) with balance metrics
        including beginning_balance, ending_balance, is_shortage, etc.
    """
    # 1. Build the full week grid
    grid = _build_week_grid(data)

    # 2. Aggregate the three flow components
    receipts = _aggregate_scheduled_receipts(data)
    production = _aggregate_planned_production(data)
    demand = _aggregate_forecast_demand(data)

    # 3. Left-join flows onto the grid
    merge_keys = ["sku_id", "location_id", "week"]
    grid = grid.merge(receipts, on=merge_keys, how="left")
    grid = grid.merge(production, on=merge_keys, how="left")
    grid = grid.merge(demand, on=merge_keys, how="left")

    # Fill missing flows with 0
    for col in ("scheduled_receipts", "planned_production", "forecast_demand"):
        grid[col] = grid[col].fillna(0.0)

    # 4. Join initial inventory
    inv = _get_initial_inventory(data)
    grid = grid.merge(inv, on=["sku_id", "location_id"], how="left")
    grid["on_hand_qty"] = grid["on_hand_qty"].fillna(0.0)
    grid["safety_stock_qty"] = grid["safety_stock_qty"].fillna(0.0)

    # 5. Sort so that cumsum runs in chronological order within each pair
    grid = grid.sort_values(["sku_id", "location_id", "week"]).reset_index(drop=True)

    # 6. Compute the net flow per week
    grid["net_flow"] = (
        grid["scheduled_receipts"]
        + grid["planned_production"]
        - grid["forecast_demand"]
    )

    # 7. Cumulative net flow within each (sku_id, location_id)
    grid["cum_net_flow"] = grid.groupby(["sku_id", "location_id"])["net_flow"].cumsum()

    # 8. Ending balance = on_hand + cumulative net flow
    grid["ending_balance"] = grid["on_hand_qty"] + grid["cum_net_flow"]

    # 9. Beginning balance = previous week's ending balance; for week 1 it is on_hand
    grid["beginning_balance"] = grid.groupby(["sku_id", "location_id"])["ending_balance"].shift(1)
    grid["beginning_balance"] = grid["beginning_balance"].fillna(grid["on_hand_qty"])

    # 10. Derived columns
    grid["available_to_promise"] = grid["ending_balance"] - grid["safety_stock_qty"]
    grid["is_shortage"] = grid["ending_balance"] < 0
    grid["is_below_safety"] = (grid["ending_balance"] < grid["safety_stock_qty"]) & (grid["ending_balance"] >= 0)

    # 11. Cumulative demand and supply
    grid["cumulative_demand"] = grid.groupby(["sku_id", "location_id"])["forecast_demand"].cumsum()
    grid["cumulative_supply"] = grid.groupby(["sku_id", "location_id"])[
        ["scheduled_receipts", "planned_production"]
    ].transform("cumsum").sum(axis=1) + grid["on_hand_qty"]

    # 12. Select and order output columns
    output_cols = [
        "sku_id", "location_id", "week", "year", "week_label",
        "beginning_balance", "scheduled_receipts", "planned_production",
        "forecast_demand", "ending_balance", "safety_stock_qty",
        "available_to_promise", "is_shortage", "is_below_safety",
        "cumulative_demand", "cumulative_supply",
    ]
    result = grid[output_cols].copy()
    return result
