"""
Transaction data generators — Purchase Orders and Production Plans.

Purchase orders connect suppliers to locations for specific SKUs.
Production plans define what each PLANT location intends to produce,
including bill-of-materials (BOM) component dependencies.
"""

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def generate_purchase_orders(
    rng: np.random.RandomState,
    supplier_caps_df: pd.DataFrame,
    lead_times_df: pd.DataFrame,
    sku_loc_df: pd.DataFrame,
) -> pd.DataFrame:
    """Generate purchase orders using valid supplier-SKU-location routes.

    Only creates POs where:
    - The supplier can supply the SKU  (supplier_capacities)
    - The supplier can reach the location (lead_times)
    - The SKU is stocked at the location (sku_loc_df)

    Parameters
    ----------
    rng : np.random.RandomState
    supplier_caps_df : pd.DataFrame
    lead_times_df : pd.DataFrame
    sku_loc_df : pd.DataFrame

    Returns
    -------
    pd.DataFrame
        NUM_PURCHASE_ORDERS rows with columns: po_id, supplier_id, sku_id,
        location_id, quantity, uom, order_date, expected_delivery_date,
        actual_delivery_date, status, unit_cost, total_cost, week.
    """
    n = config.NUM_PURCHASE_ORDERS

    # ── Build valid routes: supplier-sku-location ──
    # supplier_caps gives supplier → sku
    sup_sku = supplier_caps_df[["supplier_id", "sku_id", "uom", "max_weekly_capacity"]].copy()

    # lead_times gives supplier → location (with transit days)
    sup_loc = lead_times_df[["supplier_id", "location_id", "transit_days"]].copy()

    # Merge to get supplier-sku-location triples
    routes = sup_sku.merge(sup_loc, on="supplier_id", how="inner")

    # Filter to only routes where the SKU is stocked at the location
    sku_loc_set = set(zip(sku_loc_df["sku_id"], sku_loc_df["location_id"]))
    mask = [
        (row.sku_id, row.location_id) in sku_loc_set
        for row in routes.itertuples(index=False)
    ]
    valid_routes = routes[mask].reset_index(drop=True)

    if len(valid_routes) == 0:
        # Fallback: use routes even without sku-loc match
        valid_routes = routes.reset_index(drop=True)

    # ── Sample n routes with replacement ──
    chosen_idx = rng.choice(len(valid_routes), size=n, replace=True)
    chosen = valid_routes.iloc[chosen_idx].reset_index(drop=True)

    # ── Order dates spread through 2026 ──
    start_epoch = int(pd.Timestamp("2026-01-01").timestamp())
    end_epoch = int(pd.Timestamp("2026-10-31").timestamp())
    order_epochs = rng.randint(start_epoch, end_epoch, size=n)
    order_dates = pd.to_datetime(order_epochs, unit="s").normalize()

    # ── Expected delivery = order_date + transit_days ──
    transit_days = chosen["transit_days"].values
    expected_delivery = order_dates + pd.to_timedelta(transit_days, unit="D")

    # ── Actual delivery: add delay for some POs ──
    delay_mask = rng.random(n) < config.TRANSPORT_DELAY_PROBABILITY
    delay_days = rng.randint(3, 15, size=n)
    actual_offsets = np.where(delay_mask, delay_days, 0)

    # ── Status distribution ──
    statuses = rng.choice(
        config.PO_STATUSES,
        size=n,
        p=[0.15, 0.20, 0.20, 0.35, 0.10],
    )

    # actual_delivery_date only for RECEIVED POs
    actual_delivery = expected_delivery + pd.to_timedelta(actual_offsets, unit="D")
    actual_delivery_final = pd.Series(
        [
            actual_delivery[i] if statuses[i] == "RECEIVED" else pd.NaT
            for i in range(n)
        ]
    )

    # ── Quantities ──
    max_caps = chosen["max_weekly_capacity"].values
    quantities = np.clip(
        rng.randint(10, np.maximum(11, max_caps)),
        10,
        max_caps,
    )

    # ── Costs ──
    unit_costs = np.round(rng.uniform(5.0, 500.0, size=n), 2)
    total_costs = np.round(quantities * unit_costs, 2)

    # ── Delivery week ──
    delivery_week = expected_delivery.isocalendar().week.astype(int).values

    ids = [config.purchase_order_id(i + 1) for i in range(n)]

    return pd.DataFrame(
        {
            "po_id": ids,
            "supplier_id": chosen["supplier_id"].values,
            "sku_id": chosen["sku_id"].values,
            "location_id": chosen["location_id"].values,
            "quantity": quantities,
            "uom": chosen["uom"].values,
            "order_date": order_dates,
            "expected_delivery_date": expected_delivery,
            "actual_delivery_date": actual_delivery_final,
            "status": statuses,
            "unit_cost": unit_costs,
            "total_cost": total_costs,
            "week": delivery_week,
        }
    )


def generate_production_plans(
    rng: np.random.RandomState,
    skus_df: pd.DataFrame,
    locations_df: pd.DataFrame,
    sku_loc_df: pd.DataFrame,
    demand_df: pd.DataFrame,
) -> pd.DataFrame:
    """Generate production plans for PLANT locations.

    Each plan specifies a finished SKU, a required BOM component, and
    planned / actual production quantities.

    Parameters
    ----------
    rng : np.random.RandomState
    skus_df : pd.DataFrame
    locations_df : pd.DataFrame
    sku_loc_df : pd.DataFrame
    demand_df : pd.DataFrame

    Returns
    -------
    pd.DataFrame
        ~2000-4000 rows with columns: production_plan_id, sku_id, location_id,
        week, year, planned_quantity, actual_quantity, bom_sku_id,
        bom_qty_per_unit, capacity_utilized_pct, status.
    """
    plant_locs = locations_df[locations_df["type"] == "PLANT"]["location_id"].values

    if len(plant_locs) == 0:
        return pd.DataFrame()

    # SKUs available at plant locations
    plant_sku_loc = sku_loc_df[sku_loc_df["location_id"].isin(plant_locs)]
    if len(plant_sku_loc) == 0:
        # Fallback: assign some SKUs to plants
        plant_sku_loc = pd.DataFrame(
            {
                "sku_id": rng.choice(skus_df["sku_id"].values, size=len(plant_locs) * 10),
                "location_id": np.repeat(plant_locs, 10),
            }
        )

    all_sku_ids = skus_df["sku_id"].values
    records = []
    counter = 0

    # Target 2000-4000 rows: pick a subset of plant-sku pairs and give them a few weeks
    unique_pairs = plant_sku_loc.drop_duplicates().values  # (sku, loc) arrays
    # Limit pairs to keep rows in range
    target_rows = rng.randint(2000, 4001)
    weeks_per_pair = max(1, min(8, target_rows // max(1, len(unique_pairs))))
    max_pairs = target_rows // max(1, weeks_per_pair)
    if len(unique_pairs) > max_pairs:
        indices = rng.choice(len(unique_pairs), size=max_pairs, replace=False)
        selected_pairs = unique_pairs[indices]
    else:
        selected_pairs = unique_pairs

    status_options = ["PLANNED", "IN_PROGRESS", "COMPLETED", "CANCELLED"]
    status_probs = [0.30, 0.20, 0.40, 0.10]

    for sku, loc in selected_pairs:
        # BOM: 1-3 component SKUs
        n_components = rng.randint(1, 4)
        component_candidates = [s for s in all_sku_ids if s != sku]
        if len(component_candidates) < n_components:
            n_components = len(component_candidates)
        bom_skus = rng.choice(component_candidates, size=n_components, replace=False)
        bom_qtys = np.round(rng.uniform(0.5, 5.0, size=n_components), 2)

        # Pick random weeks for this pair
        prod_weeks = sorted(rng.choice(range(1, 53), size=weeks_per_pair, replace=False))

        for wk in prod_weeks:
            for b_sku, b_qty in zip(bom_skus, bom_qtys):
                counter += 1
                planned = int(rng.randint(100, 2001))
                status = rng.choice(status_options, p=status_probs)

                actual = None
                if status == "COMPLETED":
                    actual = int(planned * rng.uniform(0.85, 1.05))
                elif status == "IN_PROGRESS":
                    actual = int(planned * rng.uniform(0.3, 0.7))

                capacity_pct = round(rng.uniform(0.50, 0.99), 2)

                records.append(
                    {
                        "production_plan_id": config.production_plan_id(counter),
                        "sku_id": sku,
                        "location_id": loc,
                        "week": int(wk),
                        "year": config.YEAR,
                        "planned_quantity": planned,
                        "actual_quantity": actual,
                        "bom_sku_id": b_sku,
                        "bom_qty_per_unit": b_qty,
                        "capacity_utilized_pct": capacity_pct,
                        "status": status,
                    }
                )

                # Stop if we've generated enough
                if counter >= target_rows:
                    break
            if counter >= target_rows:
                break
        if counter >= target_rows:
            break

    return pd.DataFrame(records)
