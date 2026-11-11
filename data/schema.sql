-- YottaFlex Supply Chain Shortage Prioritization Schema
-- Generated deterministically with seed = 20261022

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

