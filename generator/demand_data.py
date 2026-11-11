"""
Demand data generators — SKU-location mapping and weekly forecast demand.

The forecast demand table is the largest dataset (~624 K rows at full scale).
Generation uses vectorised pandas/numpy operations for memory efficiency.
"""

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def generate_sku_location_mapping(
    rng: np.random.RandomState,
    skus_df: pd.DataFrame,
    locations_df: pd.DataFrame,
) -> pd.DataFrame:
    """Map each SKU to a random subset of locations.

    Each SKU is stocked at 2-6 locations (avg ~ AVG_LOCATIONS_PER_SKU).

    Parameters
    ----------
    rng : np.random.RandomState
    skus_df : pd.DataFrame
    locations_df : pd.DataFrame

    Returns
    -------
    pd.DataFrame
        Columns: sku_id, location_id.  Approximately NUM_SKUS × AVG rows.
    """
    sku_ids = skus_df["sku_id"].values
    loc_ids = locations_df["location_id"].values
    n_locs = len(loc_ids)

    rows_sku = []
    rows_loc = []

    for sku in sku_ids:
        # Poisson-clipped around AVG to get 2-6
        k = rng.poisson(config.AVG_LOCATIONS_PER_SKU)
        k = max(2, min(k, min(6, n_locs)))
        chosen = rng.choice(loc_ids, size=k, replace=False)
        rows_sku.extend([sku] * k)
        rows_loc.extend(chosen)

    return pd.DataFrame({"sku_id": rows_sku, "location_id": rows_loc})


def generate_forecast_demand(
    rng: np.random.RandomState,
    sku_loc_df: pd.DataFrame,
    skus_df: pd.DataFrame,
) -> pd.DataFrame:
    """Generate 52 weeks of forecast demand for every SKU-location pair.

    Uses vectorised operations to efficiently produce ~624 K rows.

    Parameters
    ----------
    rng : np.random.RandomState
    sku_loc_df : pd.DataFrame  – columns: sku_id, location_id
    skus_df : pd.DataFrame     – columns: sku_id, uom (at minimum)

    Returns
    -------
    pd.DataFrame
        Columns: demand_id, sku_id, location_id, week, year, week_label,
        quantity, uom, confidence, demand_type, created_at.
    """
    n_pairs = len(sku_loc_df)
    n_weeks = config.NUM_WEEKS  # 52
    total_rows = n_pairs * n_weeks

    # ── Build the cartesian product: each pair × 52 weeks ──
    # Repeat each pair 52 times
    sku_ids = np.repeat(sku_loc_df["sku_id"].values, n_weeks)
    loc_ids = np.repeat(sku_loc_df["location_id"].values, n_weeks)

    # Tile weeks 1-52 for every pair
    weeks = np.tile(np.arange(1, n_weeks + 1), n_pairs)

    # ── Demand IDs ──
    year_str = str(config.YEAR)
    demand_ids = np.array(
        [
            f"DEM-{s}-{l}-{year_str}W{w:02d}"
            for s, l, w in zip(sku_ids, loc_ids, weeks)
        ]
    )

    # ── UOM lookup ──
    uom_map = skus_df.set_index("sku_id")["uom"].to_dict()
    # Vectorised via a single lookup per pair, then repeat
    pair_uoms = sku_loc_df["sku_id"].map(uom_map).values
    uoms = np.repeat(pair_uoms, n_weeks)

    # ── Base demand with seasonal sine pattern ──
    # Unique base per pair
    base_demands = rng.randint(50, 501, size=n_pairs)  # 50-500
    base_repeated = np.repeat(base_demands, n_weeks).astype(np.float64)

    # Seasonal factor: sine wave peaking around week 26
    seasonal = 1.0 + 0.3 * np.sin(2 * np.pi * (weeks - 13) / 52)

    # Gaussian noise ±20 %
    noise = 1.0 + rng.normal(0, 0.10, size=total_rows)

    raw_qty = base_repeated * seasonal * noise

    # ── Demand spikes ──
    spike_mask = rng.random(total_rows) < config.DEMAND_SPIKE_PROBABILITY
    spike_multipliers = rng.uniform(
        config.DEMAND_SPIKE_MULTIPLIER_RANGE[0],
        config.DEMAND_SPIKE_MULTIPLIER_RANGE[1],
        size=total_rows,
    )
    raw_qty = np.where(spike_mask, raw_qty * spike_multipliers, raw_qty)

    quantity = np.maximum(1, np.round(raw_qty)).astype(int)

    # ── Demand type ──
    demand_type = np.where(spike_mask, "PROMOTIONAL", "REGULAR")

    # ── Week labels ──
    week_labels = np.array([f"{year_str}W{w:02d}" for w in weeks])

    # ── Confidence ──
    confidence = np.round(rng.uniform(0.6, 0.99, size=total_rows), 2)

    # ── Created-at timestamps ──
    start_epoch = int(pd.Timestamp("2025-11-01").timestamp())
    end_epoch = int(pd.Timestamp("2026-01-15").timestamp())
    created_epochs = rng.randint(start_epoch, end_epoch, size=total_rows)
    created_at = pd.to_datetime(created_epochs, unit="s").normalize()

    return pd.DataFrame(
        {
            "demand_id": demand_ids,
            "sku_id": sku_ids,
            "location_id": loc_ids,
            "week": weeks,
            "year": config.YEAR,
            "week_label": week_labels,
            "quantity": quantity,
            "uom": uoms,
            "confidence": confidence,
            "demand_type": demand_type,
            "created_at": created_at,
        }
    )
