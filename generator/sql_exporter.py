"""
SQLite database and SQL seed exporter for the YottaFlex dataset.

Fulfills Step 9 of the specification:
  "Step 9 — Export CSV/JSON/SQL seed data plus README, schema/data dictionary,
   generator command, fixed seed, source manifest and validation summary."
and Step 7:
  "Step 7 — Produce a separate ground_truth.csv/json for known anomalies..."
"""

import os
import sqlite3
import sys
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def export_sqlite_and_sql(all_data: dict, db_path: str = None, sql_schema_path: str = None) -> str:
    """
    Export all data tables into an indexed SQLite database and dump schema.sql.

    Parameters
    ----------
    all_data : dict
        Dict of table_name -> pd.DataFrame.
    db_path : str, optional
        Target SQLite database path. Default: data/supply_chain.db.
    sql_schema_path : str, optional
        Target SQL DDL path. Default: data/schema.sql.

    Returns
    -------
    str
        Path to the generated SQLite database.
    """
    if db_path is None:
        db_path = os.path.join(config.DATA_DIR, "supply_chain.db")
    if sql_schema_path is None:
        sql_schema_path = os.path.join(config.DATA_DIR, "schema.sql")

    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    # Remove existing db if present to ensure clean rebuild
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON;")

    # Table DDL mapping
    ddl_statements = [
        """
        CREATE TABLE IF NOT EXISTS skus (
            sku_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            subcategory TEXT,
            uom TEXT NOT NULL,
            weight_kg REAL,
            unit_cost REAL,
            substitute_sku_id TEXT,
            substitute_approved BOOLEAN,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS locations (
            location_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            region TEXT NOT NULL,
            country TEXT NOT NULL,
            capacity_units INTEGER,
            status TEXT NOT NULL,
            latitude REAL,
            longitude REAL
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS suppliers (
            supplier_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            country TEXT NOT NULL,
            reliability_score REAL,
            payment_terms TEXT NOT NULL,
            status TEXT NOT NULL,
            certified BOOLEAN,
            specialization TEXT
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS supplier_capacities (
            supplier_capacity_id TEXT PRIMARY KEY,
            supplier_id TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            max_weekly_capacity INTEGER,
            min_order_qty INTEGER,
            uom TEXT NOT NULL,
            effective_from TEXT,
            effective_to TEXT,
            status TEXT NOT NULL,
            FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id),
            FOREIGN KEY (sku_id) REFERENCES skus(sku_id)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS lead_times (
            lead_time_id TEXT PRIMARY KEY,
            supplier_id TEXT NOT NULL,
            location_id TEXT NOT NULL,
            transit_days INTEGER,
            transport_mode TEXT NOT NULL,
            effective_from TEXT,
            effective_to TEXT,
            FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id),
            FOREIGN KEY (location_id) REFERENCES locations(location_id)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS forecast_demand (
            demand_id TEXT PRIMARY KEY,
            sku_id TEXT NOT NULL,
            location_id TEXT NOT NULL,
            week INTEGER NOT NULL,
            year INTEGER NOT NULL,
            week_label TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            uom TEXT NOT NULL,
            confidence REAL,
            demand_type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (sku_id) REFERENCES skus(sku_id),
            FOREIGN KEY (location_id) REFERENCES locations(location_id)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS inventory (
            inventory_id TEXT PRIMARY KEY,
            sku_id TEXT NOT NULL,
            location_id TEXT NOT NULL,
            on_hand_qty INTEGER NOT NULL,
            safety_stock_qty INTEGER NOT NULL,
            reorder_point INTEGER NOT NULL,
            uom TEXT NOT NULL,
            last_updated TEXT NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY (sku_id) REFERENCES skus(sku_id),
            FOREIGN KEY (location_id) REFERENCES locations(location_id)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS purchase_orders (
            po_id TEXT,
            supplier_id TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            location_id TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            uom TEXT NOT NULL,
            order_date TEXT NOT NULL,
            expected_delivery_date TEXT NOT NULL,
            actual_delivery_date TEXT,
            status TEXT NOT NULL,
            unit_cost REAL,
            total_cost REAL,
            week INTEGER NOT NULL,
            FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id),
            FOREIGN KEY (sku_id) REFERENCES skus(sku_id),
            FOREIGN KEY (location_id) REFERENCES locations(location_id)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS production_plans (
            production_plan_id TEXT PRIMARY KEY,
            sku_id TEXT NOT NULL,
            location_id TEXT NOT NULL,
            week INTEGER NOT NULL,
            year INTEGER NOT NULL,
            planned_quantity INTEGER NOT NULL,
            actual_quantity INTEGER,
            bom_sku_id TEXT,
            bom_qty_per_unit REAL,
            capacity_utilized_pct REAL,
            status TEXT NOT NULL,
            FOREIGN KEY (sku_id) REFERENCES skus(sku_id),
            FOREIGN KEY (location_id) REFERENCES locations(location_id)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS shortages (
            shortage_id TEXT PRIMARY KEY,
            sku_id TEXT NOT NULL,
            location_id TEXT NOT NULL,
            first_shortage_week INTEGER NOT NULL,
            last_shortage_week INTEGER NOT NULL,
            duration_weeks INTEGER NOT NULL,
            shortage_quantity INTEGER NOT NULL,
            peak_shortage_week INTEGER NOT NULL,
            peak_shortage_qty INTEGER NOT NULL,
            severity TEXT NOT NULL,
            priority_score REAL NOT NULL,
            root_cause TEXT NOT NULL,
            sku_category TEXT,
            sku_unit_cost REAL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (sku_id) REFERENCES skus(sku_id),
            FOREIGN KEY (location_id) REFERENCES locations(location_id)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS mitigations (
            mitigation_id TEXT PRIMARY KEY,
            shortage_id TEXT NOT NULL,
            mitigation_type TEXT NOT NULL,
            description TEXT NOT NULL,
            estimated_qty INTEGER,
            estimated_cost_per_unit REAL,
            estimated_total_cost REAL,
            estimated_lead_time_days INTEGER,
            feasibility_score REAL NOT NULL,
            risk_factors TEXT,
            recommended BOOLEAN NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (shortage_id) REFERENCES shortages(shortage_id)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS state_transition_events (
            event_id TEXT PRIMARY KEY,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            event_timestamp TEXT NOT NULL,
            from_state TEXT NOT NULL,
            to_state TEXT NOT NULL,
            actor_role TEXT NOT NULL,
            quantity_impact REAL,
            rationale TEXT
        );
        """
    ]

    # Execute DDL
    for stmt in ddl_statements:
        cursor.execute(stmt)

    # Write schema.sql
    with open(sql_schema_path, "w") as f:
        f.write("-- YottaFlex Supply Chain Shortage Prioritization Schema\n")
        f.write("-- Generated deterministically with seed = 20261022\n\n")
        for stmt in ddl_statements:
            f.write(stmt.strip() + "\n\n")

    # Insert data
    table_to_df_key = {
        "skus": "skus",
        "locations": "locations",
        "suppliers": "suppliers",
        "supplier_capacities": "supplier_capacities",
        "lead_times": "lead_times",
        "forecast_demand": "forecast_demand",
        "inventory": "inventory",
        "purchase_orders": "purchase_orders",
        "production_plans": "production_plans",
        "shortages": "shortages",
        "mitigations": "mitigations",
        "state_transition_events": "state_transition_events",
    }

    for table_name, df_key in table_to_df_key.items():
        df = all_data.get(df_key)
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            df.to_sql(table_name, conn, if_exists="append", index=False)

    # Create helpful indexes
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_fd_sku_loc ON forecast_demand(sku_id, location_id);",
        "CREATE INDEX IF NOT EXISTS idx_po_sku_loc ON purchase_orders(sku_id, location_id);",
        "CREATE INDEX IF NOT EXISTS idx_shortage_severity ON shortages(severity);",
        "CREATE INDEX IF NOT EXISTS idx_mit_shortage ON mitigations(shortage_id);",
    ]
    for idx_stmt in indexes:
        cursor.execute(idx_stmt)

    conn.commit()
    conn.close()

    print(f"  💾 SQLite database exported to {os.path.relpath(db_path, config.PROJECT_ROOT)}")
    print(f"  📜 SQL DDL exported to {os.path.relpath(sql_schema_path, config.PROJECT_ROOT)}")

    # Also export ground_truth.json (Step 7: "Produce a separate ground_truth.csv/json")
    gt_df = all_data.get("ground_truth")
    if gt_df is not None and isinstance(gt_df, pd.DataFrame):
        gt_json_path = os.path.join(config.GROUND_TRUTH_DIR, "ground_truth.json")
        gt_df.to_json(gt_json_path, orient="records", indent=2)
        print(f"  📄 Ground truth JSON exported to {os.path.relpath(gt_json_path, config.PROJECT_ROOT)}")

    return db_path
