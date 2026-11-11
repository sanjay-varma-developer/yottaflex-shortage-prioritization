"""
Main generator orchestrator for the YottaFlex synthetic supply chain dataset.

Executes Step 1 through Step 7:
  1. Master tables (SKU, Location, Supplier)
  2. Capacity & Lead Times (SupplierCapacity, LeadTime)
  3. Demand (SKU-Location mapping, 52-week ForecastDemand)
  4. Inventory (On-hand, safety stock, reorder point)
  5. Transactions (PurchaseOrder, ProductionPlan)
  6. Edge-Case Injection (5 labeled anomalies)
  7. Export (CSV files + manifest.json)
"""

import os
import sys
import time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from generator.master_data import generate_skus, generate_locations, generate_suppliers
from generator.capacity_data import generate_supplier_capacities, generate_lead_times
from generator.demand_data import generate_sku_location_mapping, generate_forecast_demand
from generator.inventory_data import generate_inventory
from generator.transaction_data import generate_purchase_orders, generate_production_plans
from generator.edge_cases import inject_edge_cases
from generator.export import export_all


def run_generation(export: bool = True) -> dict:
    """
    Run complete synthetic data generation pipeline using deterministic seed.

    Parameters
    ----------
    export : bool, default=True
        Whether to export CSVs and manifest to data/ folder.

    Returns
    -------
    dict
        Dictionary containing all generated DataFrames + 'ground_truth'.
    """
    print(f"  Starting data generation with seed = {config.RANDOM_SEED} (scale = {config.SCALE_FACTOR})...")
    rng = np.random.RandomState(config.RANDOM_SEED)

    t0 = time.time()

    # 1. Master Data
    print("  [1/6] Generating Master Data (SKUs, Locations, Suppliers)...")
    skus_df = generate_skus(rng)
    locations_df = generate_locations(rng)
    suppliers_df = generate_suppliers(rng)
    print(f"        -> SKUs: {len(skus_df):,}, Locations: {len(locations_df):,}, Suppliers: {len(suppliers_df):,}")

    # 2. Capacity & Lead Times
    print("  [2/6] Generating Supplier Capacities & Transit Lead Times...")
    supplier_caps_df = generate_supplier_capacities(rng, skus_df, suppliers_df)
    lead_times_df = generate_lead_times(rng, suppliers_df, locations_df)
    print(f"        -> Capacities: {len(supplier_caps_df):,}, Lead Times: {len(lead_times_df):,}")

    # 3. SKU-Location Mapping & Forecast Demand
    print("  [3/6] Generating SKU-Location Mapping & 52-Week Forecast Demand...")
    sku_loc_df = generate_sku_location_mapping(rng, skus_df, locations_df)
    demand_df = generate_forecast_demand(rng, sku_loc_df, skus_df)
    print(f"        -> SKU-Location Pairs: {len(sku_loc_df):,}, Demand Rows: {len(demand_df):,}")

    # 4. Inventory
    print("  [4/6] Generating Inventory Snapshot (Week 0 On-Hand)...")
    inventory_df = generate_inventory(rng, sku_loc_df, demand_df)
    print(f"        -> Inventory Rows: {len(inventory_df):,}")

    # 5. Transactions (POs & Production Plans)
    print("  [5/6] Generating Purchase Orders & Production Plans...")
    pos_df = generate_purchase_orders(rng, supplier_caps_df, lead_times_df, sku_loc_df)
    prod_df = generate_production_plans(rng, skus_df, locations_df, sku_loc_df, demand_df)
    print(f"        -> Purchase Orders: {len(pos_df):,}, Production Plans: {len(prod_df):,}")

    # Assemble dataset
    all_data = {
        "skus": skus_df,
        "locations": locations_df,
        "suppliers": suppliers_df,
        "supplier_capacities": supplier_caps_df,
        "lead_times": lead_times_df,
        "sku_location_mapping": sku_loc_df,
        "forecast_demand": demand_df,
        "inventory": inventory_df,
        "purchase_orders": pos_df,
        "production_plans": prod_df,
    }

    # 6. Edge Case Injection
    print("  [6/6] Injecting 5 Labeled Edge Cases...")
    all_data, ground_truth_df = inject_edge_cases(rng, all_data)
    all_data["ground_truth"] = ground_truth_df
    print(f"        -> Ground Truth Anomaly Records: {len(ground_truth_df):,}")

    # 7. Export
    if export:
        print("  Exporting tables to CSV...")
        export_all(all_data, ground_truth_df)

    elapsed = time.time() - t0
    print(f"  ✨ Generation finished in {elapsed:.2f}s")

    return all_data


if __name__ == "__main__":
    run_generation(export=True)
