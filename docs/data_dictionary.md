# YottaFlex Supply Chain — Data Dictionary

> **Version:** 1.0  
> **Last Updated:** 2026-11-11  
> **Scope:** All 11 entities in the Supply Chain Shortage Prioritization System

---

## Table of Contents

1. [SKU](#1-sku)
2. [Location](#2-location)
3. [Supplier](#3-supplier)
4. [SupplierCapacity](#4-suppliercapacity)
5. [LeadTime](#5-leadtime)
6. [ForecastDemand](#6-forecastdemand)
7. [Inventory](#7-inventory)
8. [PurchaseOrder](#8-purchaseorder)
9. [ProductionPlan](#9-productionplan)
10. [Shortage](#10-shortage)
11. [MitigationOption](#11-mitigationoption)
12. [StateTransitionEvent](#12-statetransitionevent)
13. [Relationship Summary](#13-relationship-summary)
14. [State Lifecycles](#14-state-lifecycles)
15. [Bridge Tables](#15-bridge-tables)

---

## 1. SKU

**Description:** Stock Keeping Unit — the master catalogue of every product, component, or material tracked in the supply chain.

**File:** `data/master/skus.csv`  
**Primary Key:** `sku_id`  
**Record Count (full scale):** 3,000

### Columns

| Column | Data Type | Required | Allowed Values / Format | Units | Unique | Validation Rule | Description |
|---|---|---|---|---|---|---|---|
| `sku_id` | string | ✅ | `SKU-NNNNNN` (zero-padded 6 digits) | — | ✅ | Regex `^SKU-\d{6}$` | Primary key. Auto-generated sequential ID. |
| `name` | string | ✅ | Free text | — | ✅ | Non-empty, max 200 chars | Human-readable product name. |
| `category` | string | ✅ | `Electronics`, `Automotive`, `Consumer Goods`, `Pharmaceuticals`, `Industrial`, `Food & Beverage`, `Chemicals`, `Textiles`, `Packaging`, `Components` | — | ❌ | Must be in `SKU_CATEGORIES` list | Product category. |
| `subcategory` | string | ✅ | Free text | — | ❌ | Non-empty | Finer classification within category. |
| `uom` | string | ✅ | `EA`, `KG`, `LT`, `BOX`, `PALLET` | — | ❌ | Must be in `UNITS_OF_MEASURE` | Base unit of measure for this SKU. |
| `weight_kg` | float | ✅ | > 0 | kg | ❌ | Positive float | Unit weight used for logistics calculations. |
| `unit_cost` | float | ✅ | > 0 | USD | ❌ | Positive float, 2 decimal places | Standard cost per UOM. |
| `substitute_sku_id` | string | ❌ | `SKU-NNNNNN` or `null` | — | ❌ | Must reference a valid `sku_id` if present; cannot self-reference | Approved substitute product when this SKU is short. |
| `substitute_approved` | boolean | ✅ | `True` / `False` | — | ❌ | If `substitute_sku_id` is null, must be `False` | Whether the substitute has been formally approved. |
| `status` | string | ✅ | `ACTIVE`, `DISCONTINUED`, `ON_HOLD` | — | ❌ | Must be one of the allowed values | Current lifecycle status. |
| `created_at` | date | ✅ | `YYYY-MM-DD` | — | ❌ | Valid ISO date, ≤ today | Record creation timestamp. |

### Foreign Keys

| Column | References | Cardinality | On Delete |
|---|---|---|---|
| `substitute_sku_id` | `SKU.sku_id` | N:1 (self-referencing) | SET NULL |

### Suggested Indexes

- **Primary:** `sku_id`
- `category` (filter queries)
- `status` (filter active SKUs)
- `substitute_sku_id` (join lookups)

### Business Rules

- Only `ACTIVE` SKUs participate in demand forecasting and purchase orders.
- A SKU may have at most **one** substitute; the substitute must itself be `ACTIVE`.
- Edge case `substitute_not_approved`: ~1% of SKUs with substitutes may have `substitute_approved = False` to test validation.
- `unit_cost` is used downstream in priority scoring and total-cost calculations.

---

## 2. Location

**Description:** Physical sites (warehouses, distribution centres, manufacturing plants) where inventory is held or consumed.

**File:** `data/master/locations.csv`  
**Primary Key:** `location_id`  
**Record Count (full scale):** 50

### Columns

| Column | Data Type | Required | Allowed Values / Format | Units | Unique | Validation Rule | Description |
|---|---|---|---|---|---|---|---|
| `location_id` | string | ✅ | `LOC-NNN` (zero-padded 3 digits) | — | ✅ | Regex `^LOC-\d{3}$` | Primary key. |
| `name` | string | ✅ | Free text | — | ✅ | Non-empty, max 200 chars | Location name (e.g., city + type). |
| `type` | string | ✅ | `WAREHOUSE`, `DISTRIBUTION_CENTER`, `PLANT` | — | ❌ | Must be in `LOCATION_TYPES` | Facility type; determines eligibility for production plans. |
| `region` | string | ✅ | `North`, `South`, `East`, `West`, `Central` | — | ❌ | Must be in `REGIONS` | Geographic region. |
| `country` | string | ✅ | Free text (country name) | — | ❌ | Non-empty | Country where the facility is situated. |
| `capacity_units` | int | ✅ | > 0 | UOM (mixed) | ❌ | Positive integer | Maximum storage / throughput capacity. |
| `status` | string | ✅ | `ACTIVE`, `INACTIVE` | — | ❌ | Must be one of the allowed values | Operational status. |
| `latitude` | float | ✅ | −90 to 90 | degrees | ❌ | Valid latitude | GPS latitude. |
| `longitude` | float | ✅ | −180 to 180 | degrees | ❌ | Valid longitude | GPS longitude. |

### Foreign Keys

None (master table).

### Suggested Indexes

- **Primary:** `location_id`
- `type` (filter plants for production plans)
- `region` (regional reporting)
- `status`

### Business Rules

- Only `ACTIVE` locations are eligible for demand, inventory, and purchase order records.
- `PLANT` locations are the only ones eligible as `location_id` in `ProductionPlan`.
- Locations with `INACTIVE` status retain historical data but receive no new transactions.

---

## 3. Supplier

**Description:** External organisations that provide materials, components, or finished goods.

**File:** `data/master/suppliers.csv`  
**Primary Key:** `supplier_id`  
**Record Count (full scale):** 500

### Columns

| Column | Data Type | Required | Allowed Values / Format | Units | Unique | Validation Rule | Description |
|---|---|---|---|---|---|---|---|
| `supplier_id` | string | ✅ | `SUP-NNNNNN` (zero-padded 6 digits) | — | ✅ | Regex `^SUP-\d{6}$` | Primary key. |
| `name` | string | ✅ | Free text | — | ✅ | Non-empty, max 200 chars | Supplier legal name. |
| `country` | string | ✅ | Free text | — | ❌ | Non-empty | Country of incorporation / primary operations. |
| `reliability_score` | float | ✅ | 0.0 – 1.0 | ratio | ❌ | `0 <= x <= 1` | Historical on-time-in-full delivery score. |
| `payment_terms` | string | ✅ | `NET30`, `NET45`, `NET60`, `NET90` | — | ❌ | Must be in `SUPPLIER_PAYMENT_TERMS` | Negotiated payment terms. |
| `status` | string | ✅ | `ACTIVE`, `INACTIVE`, `SUSPENDED` | — | ❌ | Must be one of the allowed values | Supplier engagement status. |
| `certified` | boolean | ✅ | `True` / `False` | — | ❌ | — | Whether the supplier holds required quality certifications. |
| `specialization` | string | ✅ | Free text | — | ❌ | Non-empty | Primary product specialization (maps to SKU categories). |

### Foreign Keys

None (master table; linked to SKU through SupplierCapacity bridge).

### Suggested Indexes

- **Primary:** `supplier_id`
- `status`
- `reliability_score` (sorting/filtering)
- `country`

### Business Rules

- Only `ACTIVE` suppliers can appear on new purchase orders.
- `SUSPENDED` suppliers retain existing POs but cannot receive new ones.
- `reliability_score` feeds into mitigation feasibility scoring.
- 15% of suppliers (`CONSTRAINED_SUPPLIER_FRACTION`) are marked as capacity-constrained during generation.

---

## 4. SupplierCapacity

**Description:** Bridge table capturing the N:M relationship between Suppliers and SKUs — which supplier can supply which SKU, and at what capacity.

**File:** `data/master/supplier_capacities.csv`  
**Primary Key:** `supplier_capacity_id`  
**Record Count (full scale):** ~6,000–15,000 (varies by generation)

### Columns

| Column | Data Type | Required | Allowed Values / Format | Units | Unique | Validation Rule | Description |
|---|---|---|---|---|---|---|---|
| `supplier_capacity_id` | string | ✅ | `SC-NNNNNN` | — | ✅ | Regex `^SC-\d{6}$` | Primary key. |
| `supplier_id` | string | ✅ | `SUP-NNNNNN` | — | ❌ | Must reference `Supplier.supplier_id` | Foreign key to Supplier. |
| `sku_id` | string | ✅ | `SKU-NNNNNN` | — | ❌ | Must reference `SKU.sku_id` | Foreign key to SKU. |
| `max_weekly_capacity` | int | ✅ | > 0 | UOM | ❌ | Positive integer | Maximum units this supplier can deliver per week for this SKU. |
| `min_order_qty` | int | ✅ | > 0 | UOM | ❌ | Positive integer; ≤ `max_weekly_capacity` | Minimum order quantity per order. |
| `uom` | string | ✅ | `EA`, `KG`, `LT`, `BOX`, `PALLET` | — | ❌ | Should match `SKU.uom` (edge case: UOM mismatch) | Unit of measure for capacity. |
| `effective_from` | date | ✅ | `YYYY-MM-DD` | — | ❌ | Valid ISO date | Start date of this capacity agreement. |
| `effective_to` | date | ✅ | `YYYY-MM-DD` | — | ❌ | Must be ≥ `effective_from` | End date of this capacity agreement. |
| `status` | string | ✅ | `ACTIVE`, `EXPIRED` | — | ❌ | `EXPIRED` if `effective_to < today` | Whether this capacity record is currently valid. |

### Foreign Keys

| Column | References | Cardinality | On Delete |
|---|---|---|---|
| `supplier_id` | `Supplier.supplier_id` | N:1 | CASCADE |
| `sku_id` | `SKU.sku_id` | N:1 | CASCADE |

### Composite Uniqueness

The combination `(supplier_id, sku_id, effective_from)` should be unique — a supplier has at most one capacity record per SKU per effective period.

### Suggested Indexes

- **Primary:** `supplier_capacity_id`
- `(supplier_id, sku_id)` — composite for join lookups
- `status`
- `sku_id` — for reverse lookups (find all suppliers for a SKU)

### Business Rules

- Edge case `supplier_capacity_exceeded`: ~2% of records may have PO quantities that exceed `max_weekly_capacity`.
- Edge case `uom_mismatch`: ~0.5% of records may have a `uom` that differs from `SKU.uom`.
- Only `ACTIVE` records are used in shortage mitigation (alternate supplier logic).
- `min_order_qty` constrains the minimum viable expedite or alternate-supplier mitigation quantity.

---

## 5. LeadTime

**Description:** Bridge table capturing transit lead times between Suppliers and Locations, by transport mode. Represents the N:M relationship between Supplier and Location.

**File:** `data/master/lead_times.csv`  
**Primary Key:** `lead_time_id`  
**Record Count (full scale):** ~5,000–12,000

### Columns

| Column | Data Type | Required | Allowed Values / Format | Units | Unique | Validation Rule | Description |
|---|---|---|---|---|---|---|---|
| `lead_time_id` | string | ✅ | `LT-NNNNNN` | — | ✅ | Regex `^LT-\d{6}$` | Primary key. |
| `supplier_id` | string | ✅ | `SUP-NNNNNN` | — | ❌ | Must reference `Supplier.supplier_id` | Foreign key to Supplier. |
| `location_id` | string | ✅ | `LOC-NNN` | — | ❌ | Must reference `Location.location_id` | Foreign key to destination Location. |
| `transit_days` | int | ✅ | > 0 | days | ❌ | Positive integer | Standard transit time from supplier to location. |
| `transport_mode` | string | ✅ | `ROAD`, `RAIL`, `SEA`, `AIR` | — | ❌ | Must be in `TRANSPORT_MODES` | Mode of transport. |
| `effective_from` | date | ✅ | `YYYY-MM-DD` | — | ❌ | Valid ISO date | Start of validity period. |
| `effective_to` | date | ✅ | `YYYY-MM-DD` | — | ❌ | Must be ≥ `effective_from` | End of validity period. |

### Foreign Keys

| Column | References | Cardinality | On Delete |
|---|---|---|---|
| `supplier_id` | `Supplier.supplier_id` | N:1 | CASCADE |
| `location_id` | `Location.location_id` | N:1 | CASCADE |

### Composite Uniqueness

`(supplier_id, location_id, transport_mode, effective_from)` should be unique.

### Suggested Indexes

- **Primary:** `lead_time_id`
- `(supplier_id, location_id)` — composite for join lookups
- `transport_mode`

### Business Rules

- Lead times are used to calculate `expected_delivery_date` on purchase orders: `order_date + transit_days`.
- Edge case `shortage_without_lead_time`: ~0.5% of shortages may lack a corresponding lead time record to test fallback logic.
- The `AIR` mode has the shortest transit days (1–5) but highest cost; `SEA` is longest (20–45) but cheapest.
- Lead time feeds into the `estimated_lead_time_days` field in `MitigationOption`.

---

## 6. ForecastDemand

**Description:** Weekly demand forecasts per SKU per Location for the planning horizon (52 weeks of 2026).

**File:** `data/transactions/forecast_demand.csv`  
**Primary Key:** `demand_id`  
**Record Count (full scale):** ~12,000 × 52 ≈ 624,000

### Columns

| Column | Data Type | Required | Allowed Values / Format | Units | Unique | Validation Rule | Description |
|---|---|---|---|---|---|---|---|
| `demand_id` | string | ✅ | `DEM-SKU-NNNNNN-LOC-NNN-2026WNN` | — | ✅ | Deterministic composite ID | Primary key — encodes SKU, location, and week. |
| `sku_id` | string | ✅ | `SKU-NNNNNN` | — | ❌ | Must reference `SKU.sku_id` | Which product is demanded. |
| `location_id` | string | ✅ | `LOC-NNN` | — | ❌ | Must reference `Location.location_id` | Where demand occurs. |
| `week` | int | ✅ | 1–52 | — | ❌ | `WEEK_START <= week <= WEEK_END` | ISO week number. |
| `year` | int | ✅ | 2026 | — | ❌ | Must equal `config.YEAR` | Planning year. |
| `week_label` | string | ✅ | `2026WNN` (zero-padded 2 digits) | — | ❌ | Matches `f"{YEAR}W{week:02d}"` | Human-readable week label. |
| `quantity` | int | ✅ | > 0 | UOM | ❌ | Positive integer | Forecasted demand quantity. |
| `uom` | string | ✅ | `EA`, `KG`, `LT`, `BOX`, `PALLET` | — | ❌ | Must match `SKU.uom` | Unit of measure. |
| `confidence` | float | ✅ | 0.0 – 1.0 | ratio | ❌ | `0 <= x <= 1` | Statistical confidence in the forecast. |
| `demand_type` | string | ✅ | `REGULAR`, `PROMOTIONAL` | — | ❌ | Must be one of the allowed values | Whether demand is baseline or promotional. |
| `created_at` | date | ✅ | `YYYY-MM-DD` | — | ❌ | Valid ISO date | Record creation date. |

### Foreign Keys

| Column | References | Cardinality | On Delete |
|---|---|---|---|
| `sku_id` | `SKU.sku_id` | N:1 | CASCADE |
| `location_id` | `Location.location_id` | N:1 | CASCADE |

### Composite Uniqueness

`(sku_id, location_id, week, year)` is unique — one forecast per SKU-location-week.

### Suggested Indexes

- **Primary:** `demand_id`
- `(sku_id, location_id, week)` — composite for PAB calculation lookups
- `week` — for weekly aggregation
- `demand_type` — filter promotional spikes

### Business Rules

- 5% of demand rows (`DEMAND_SPIKE_PROBABILITY`) receive a spike multiplier of 2×–5× (`DEMAND_SPIKE_MULTIPLIER_RANGE`), simulating promotional surges.
- Demand `quantity` drives the PAB (Projected Available Balance) calculation; negative PAB triggers shortage detection.
- `confidence` < 0.5 indicates lower forecast reliability and may affect prioritisation.
- `PROMOTIONAL` demand rows typically have higher quantities and lower confidence.

---

## 7. Inventory

**Description:** Current on-hand inventory snapshot per SKU per Location, including safety stock and reorder point parameters.

**File:** `data/transactions/inventory.csv`  
**Primary Key:** `inventory_id`  
**Record Count (full scale):** ~12,000 (one per SKU-location pair)

### Columns

| Column | Data Type | Required | Allowed Values / Format | Units | Unique | Validation Rule | Description |
|---|---|---|---|---|---|---|---|
| `inventory_id` | string | ✅ | `INV-NNNNNN` | — | ✅ | Regex `^INV-\d{6}$` | Primary key. |
| `sku_id` | string | ✅ | `SKU-NNNNNN` | — | ❌ | Must reference `SKU.sku_id` | Foreign key to SKU. |
| `location_id` | string | ✅ | `LOC-NNN` | — | ❌ | Must reference `Location.location_id` | Foreign key to Location. |
| `on_hand_qty` | int | ✅ | ≥ 0 | UOM | ❌ | Non-negative integer | Physical inventory currently on hand. |
| `safety_stock_qty` | int | ✅ | ≥ 0 | UOM | ❌ | Non-negative integer | Minimum buffer stock level (= `SAFETY_STOCK_WEEKS` × avg weekly demand). |
| `reorder_point` | int | ✅ | ≥ 0 | UOM | ❌ | Non-negative integer; typically `safety_stock_qty + (avg_weekly_demand × avg_lead_time_weeks)` | Inventory level that triggers replenishment. |
| `uom` | string | ✅ | `EA`, `KG`, `LT`, `BOX`, `PALLET` | — | ❌ | Must match `SKU.uom` | Unit of measure. |
| `last_updated` | date | ✅ | `YYYY-MM-DD` | — | ❌ | Valid ISO date | Timestamp of last inventory count. |
| `status` | string | ✅ | `AVAILABLE` | — | ❌ | Must be `AVAILABLE` | Inventory availability status. |

### Foreign Keys

| Column | References | Cardinality | On Delete |
|---|---|---|---|
| `sku_id` | `SKU.sku_id` | N:1 | CASCADE |
| `location_id` | `Location.location_id` | N:1 | CASCADE |

### Composite Uniqueness

`(sku_id, location_id)` is unique — one inventory record per SKU-location pair.

### Suggested Indexes

- **Primary:** `inventory_id`
- `(sku_id, location_id)` — unique composite
- `sku_id` — for SKU-level aggregation

### Business Rules

- `safety_stock_qty = SAFETY_STOCK_WEEKS (2) × average weekly demand` for the SKU-location pair.
- `reorder_point = safety_stock_qty + (avg_weekly_demand × avg_lead_time_weeks)`.
- `on_hand_qty` is the starting inventory for week 1 of the PAB calculation.
- Inventory is never negative at rest; shortages are computed via PAB, not by decrementing inventory below zero.

---

## 8. PurchaseOrder

**Description:** Inbound supply orders placed with suppliers, tracking status from creation through delivery.

**File:** `data/transactions/purchase_orders.csv`  
**Primary Key:** `po_id`  
**Record Count (full scale):** 10,000

### Columns

| Column | Data Type | Required | Allowed Values / Format | Units | Unique | Validation Rule | Description |
|---|---|---|---|---|---|---|---|
| `po_id` | string | ✅ | `PO-2026-NNNNNN` | — | ✅ | Regex `^PO-2026-\d{6}$` | Primary key. |
| `supplier_id` | string | ✅ | `SUP-NNNNNN` | — | ❌ | Must reference `Supplier.supplier_id` | Which supplier fulfils this order. |
| `sku_id` | string | ✅ | `SKU-NNNNNN` | — | ❌ | Must reference `SKU.sku_id` | Which product is being ordered. |
| `location_id` | string | ✅ | `LOC-NNN` | — | ❌ | Must reference `Location.location_id` | Destination location for delivery. |
| `quantity` | int | ✅ | > 0 | UOM | ❌ | Positive integer | Ordered quantity. |
| `uom` | string | ✅ | `EA`, `KG`, `LT`, `BOX`, `PALLET` | — | ❌ | Must match `SKU.uom` | Unit of measure. |
| `order_date` | date | ✅ | `YYYY-MM-DD` | — | ❌ | Valid ISO date | Date the PO was raised. |
| `expected_delivery_date` | date | ✅ | `YYYY-MM-DD` | — | ❌ | Must be ≥ `order_date` | Calculated: `order_date + transit_days` from LeadTime. |
| `actual_delivery_date` | date | ❌ | `YYYY-MM-DD` or `null` | — | ❌ | If present, must be ≥ `order_date` | Actual delivery date; null if not yet received. |
| `status` | string | ✅ | `OPEN`, `CONFIRMED`, `IN_TRANSIT`, `RECEIVED`, `CANCELLED` | — | ❌ | Must be in `PO_STATUSES` | Current order status. |
| `unit_cost` | float | ✅ | > 0 | USD | ❌ | Positive float | Cost per unit. |
| `total_cost` | float | ✅ | > 0 | USD | ❌ | Must equal `quantity × unit_cost` | Total order value. |
| `week` | int | ✅ | 1–52 | — | ❌ | ISO week of `expected_delivery_date` | Delivery week used in PAB calculation. |

### Foreign Keys

| Column | References | Cardinality | On Delete |
|---|---|---|---|
| `supplier_id` | `Supplier.supplier_id` | N:1 | RESTRICT |
| `sku_id` | `SKU.sku_id` | N:1 | RESTRICT |
| `location_id` | `Location.location_id` | N:1 | RESTRICT |

### Suggested Indexes

- **Primary:** `po_id`
- `(sku_id, location_id, week)` — for PAB supply lookups
- `supplier_id`
- `status`
- `expected_delivery_date`

### Business Rules

- Only non-`CANCELLED` POs with `status` in (`OPEN`, `CONFIRMED`, `IN_TRANSIT`) contribute supply in the PAB calculation.
- `RECEIVED` POs have already been consumed into `on_hand_qty`.
- Edge case `inbound_counted_twice`: ~0.5% of POs may be duplicated to test double-counting detection.
- 8% of POs (`TRANSPORT_DELAY_PROBABILITY`) may have `actual_delivery_date` later than `expected_delivery_date`, simulating transit delays.
- `total_cost` must equal `quantity × unit_cost` — any mismatch is a validation error.

---

## 9. ProductionPlan

**Description:** Internal manufacturing plans that convert raw material SKUs into finished goods at Plant locations.

**File:** `data/transactions/production_plans.csv`  
**Primary Key:** `production_plan_id`  
**Record Count (full scale):** Varies (one per SKU-plant-week combination for PLANT locations)

### Columns

| Column | Data Type | Required | Allowed Values / Format | Units | Unique | Validation Rule | Description |
|---|---|---|---|---|---|---|---|
| `production_plan_id` | string | ✅ | `PP-NNNNNN` | — | ✅ | Regex `^PP-\d{6}$` | Primary key. |
| `sku_id` | string | ✅ | `SKU-NNNNNN` | — | ❌ | Must reference `SKU.sku_id` | Finished-good SKU being produced. |
| `location_id` | string | ✅ | `LOC-NNN` | — | ❌ | Must reference `Location.location_id` where `type = 'PLANT'` | Manufacturing plant. |
| `week` | int | ✅ | 1–52 | — | ❌ | `WEEK_START <= week <= WEEK_END` | Production week. |
| `year` | int | ✅ | 2026 | — | ❌ | Must equal `config.YEAR` | Planning year. |
| `planned_quantity` | int | ✅ | > 0 | UOM | ❌ | Positive integer | Planned output quantity. |
| `actual_quantity` | int | ❌ | ≥ 0 or `null` | UOM | ❌ | Non-negative if present | Actual output (populated post-production). |
| `bom_sku_id` | string | ✅ | `SKU-NNNNNN` | — | ❌ | Must reference `SKU.sku_id`; must differ from `sku_id` | Bill-of-material component SKU consumed. |
| `bom_qty_per_unit` | float | ✅ | > 0 | UOM | ❌ | Positive float | Units of `bom_sku_id` consumed per unit of `sku_id` produced. |
| `capacity_utilized_pct` | float | ✅ | 0.0 – 100.0 | percent | ❌ | `0 <= x <= 100` | Percentage of plant capacity used. |
| `status` | string | ✅ | `PLANNED`, `IN_PROGRESS`, `COMPLETED`, `CANCELLED` | — | ❌ | Must be one of the allowed values | Production status. |

### Foreign Keys

| Column | References | Cardinality | On Delete |
|---|---|---|---|
| `sku_id` | `SKU.sku_id` | N:1 | RESTRICT |
| `location_id` | `Location.location_id` | N:1 | RESTRICT |
| `bom_sku_id` | `SKU.sku_id` | N:1 | RESTRICT |

### Suggested Indexes

- **Primary:** `production_plan_id`
- `(sku_id, location_id, week)` — PAB supply lookup
- `bom_sku_id` — component-demand analysis
- `status`

### Business Rules

- `location_id` must point to a Location with `type = 'PLANT'`.
- Production plans with `status` in (`PLANNED`, `IN_PROGRESS`) contribute to supply in PAB.
- `COMPLETED` plans have already been consumed into inventory.
- `bom_qty_per_unit` × `planned_quantity` gives the total component demand — this creates dependent demand on `bom_sku_id`.
- `capacity_utilized_pct > 90` signals the plant is near capacity and limits the `INCREASE_PRODUCTION` mitigation.

---

## 10. Shortage

**Description:** Detected supply shortfalls computed from the Projected Available Balance (PAB). Each record represents a contiguous shortage period for one SKU at one location.

**File:** `data/computed/shortages.csv`  
**Primary Key:** `shortage_id`  
**Record Count (full scale):** Varies (output of shortage detection engine)

### Columns

| Column | Data Type | Required | Allowed Values / Format | Units | Unique | Validation Rule | Description |
|---|---|---|---|---|---|---|---|
| `shortage_id` | string | ✅ | `SHORT-2026-NNNNNN` | — | ✅ | Regex `^SHORT-2026-\d{6}$` | Primary key. |
| `sku_id` | string | ✅ | `SKU-NNNNNN` | — | ❌ | Must reference `SKU.sku_id` | Affected product. |
| `location_id` | string | ✅ | `LOC-NNN` | — | ❌ | Must reference `Location.location_id` | Affected location. |
| `first_shortage_week` | int | ✅ | 1–52 | — | ❌ | `1 <= x <= 52` | First week where PAB < 0. |
| `last_shortage_week` | int | ✅ | 1–52 | — | ❌ | Must be ≥ `first_shortage_week` | Last contiguous week where PAB < 0. |
| `duration_weeks` | int | ✅ | ≥ 1 | weeks | ❌ | Must equal `last_shortage_week - first_shortage_week + 1` | Total consecutive weeks of shortage. |
| `shortage_quantity` | int | ✅ | > 0 | UOM | ❌ | Positive integer | Cumulative shortage across all shortage weeks (sum of negative PAB). |
| `peak_shortage_week` | int | ✅ | 1–52 | — | ❌ | Must be between `first_shortage_week` and `last_shortage_week` | Week with the worst (most negative) PAB. |
| `peak_shortage_qty` | int | ✅ | > 0 | UOM | ❌ | Positive integer; ≤ `shortage_quantity` | Shortage quantity in the peak week. |
| `severity` | string | ✅ | `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` | — | ❌ | Must be in `SHORTAGE_SEVERITIES` | Classified severity level. |
| `priority_score` | float | ✅ | 0.0 – 100.0 | score | ❌ | `0 <= x <= 100` | Composite priority score for ranking. |
| `root_cause` | string | ✅ | Free text | — | ❌ | Non-empty | Identified root cause(s) of the shortage. |
| `sku_category` | string | ✅ | Must be in `SKU_CATEGORIES` | — | ❌ | Denormalized from `SKU.category` | Copied for reporting convenience. |
| `sku_unit_cost` | float | ✅ | > 0 | USD | ❌ | Denormalized from `SKU.unit_cost` | Copied for financial-impact calculations. |
| `created_at` | date | ✅ | `YYYY-MM-DD` | — | ❌ | Valid ISO date | Date shortage was detected. |

### Foreign Keys

| Column | References | Cardinality | On Delete |
|---|---|---|---|
| `sku_id` | `SKU.sku_id` | N:1 | RESTRICT |
| `location_id` | `Location.location_id` | N:1 | RESTRICT |

### Suggested Indexes

- **Primary:** `shortage_id`
- `(sku_id, location_id)` — composite for deduplication
- `severity`
- `priority_score` (descending — for top-N queries)
- `first_shortage_week`

### Business Rules

- A shortage is created when PAB drops below `SHORTAGE_THRESHOLD` (0) for any week.
- Contiguous negative-PAB weeks are merged into a single shortage record.
- Severity is classified by `shortage_quantity` and `duration_weeks` (see [business_rules.md](./business_rules.md)).
- `priority_score` is a weighted composite of severity, financial impact, duration, and timing (see [business_rules.md](./business_rules.md)).
- Denormalized fields (`sku_category`, `sku_unit_cost`) are snapshotted at detection time for stable reporting.

---

## 11. MitigationOption

**Description:** Proposed remediation actions for each detected shortage. Multiple options may exist per shortage; at most one is marked `recommended`.

**File:** `data/computed/mitigation_options.csv`  
**Primary Key:** `mitigation_id`  
**Record Count (full scale):** Shortages × up to `MAX_MITIGATIONS_PER_SHORTAGE` (4)

### Columns

| Column | Data Type | Required | Allowed Values / Format | Units | Unique | Validation Rule | Description |
|---|---|---|---|---|---|---|---|
| `mitigation_id` | string | ✅ | `MIT-SHORT-2026-NNNNNN-NN` | — | ✅ | Composite of shortage ID + 2-digit sequence | Primary key. |
| `shortage_id` | string | ✅ | `SHORT-2026-NNNNNN` | — | ❌ | Must reference `Shortage.shortage_id` | Parent shortage. |
| `mitigation_type` | string | ✅ | `EXPEDITE_PO`, `ALTERNATE_SUPPLIER`, `SUBSTITUTE_SKU`, `INCREASE_PRODUCTION`, `REDISTRIBUTE_INVENTORY`, `PARTIAL_FULFILLMENT`, `BACKORDER` | — | ❌ | Must be in `MITIGATION_TYPES` | Category of remediation action. |
| `description` | string | ✅ | Free text | — | ❌ | Non-empty | Human-readable description of the proposed action. |
| `estimated_qty` | int | ✅ | > 0 | UOM | ❌ | Positive integer | Quantity this option could recover. |
| `estimated_cost_per_unit` | float | ✅ | ≥ 0 | USD | ❌ | Non-negative float | Additional cost per unit for this mitigation. |
| `estimated_total_cost` | float | ✅ | ≥ 0 | USD | ❌ | Must equal `estimated_qty × estimated_cost_per_unit` | Total cost of mitigation. |
| `estimated_lead_time_days` | int | ✅ | ≥ 0 | days | ❌ | Non-negative integer | Days until the mitigation yields supply. |
| `feasibility_score` | float | ✅ | 0.0 – 1.0 | ratio | ❌ | `0 <= x <= 1` | Likelihood of successful execution. |
| `risk_factors` | string | ✅ | Free text | — | ❌ | Non-empty | Known risks or assumptions. |
| `recommended` | boolean | ✅ | `True` / `False` | — | ❌ | At most one `True` per `shortage_id` | Whether this is the top-ranked option. |
| `created_at` | date | ✅ | `YYYY-MM-DD` | — | ❌ | Valid ISO date | Date option was generated. |

### Foreign Keys

| Column | References | Cardinality | On Delete |
|---|---|---|---|
| `shortage_id` | `Shortage.shortage_id` | N:1 | CASCADE |

### Suggested Indexes

- **Primary:** `mitigation_id`
- `shortage_id` — for parent lookup
- `mitigation_type`
- `recommended` — filter recommended actions
- `feasibility_score` (descending)

### Business Rules

- Up to `MAX_MITIGATIONS_PER_SHORTAGE` (4) options are generated per shortage.
- Exactly one option per shortage should have `recommended = True` (the one with the highest feasibility-cost trade-off).
- `estimated_total_cost` must equal `estimated_qty × estimated_cost_per_unit`.
- `feasibility_score` factors in supplier reliability, capacity availability, lead time feasibility, and substitute approval status.
- `SUBSTITUTE_SKU` is only generated if the SKU has a substitute with `substitute_approved = True`.
- `INCREASE_PRODUCTION` is only generated if a `PLANT` location exists for the SKU with `capacity_utilized_pct < 90`.

---

## 12. StateTransitionEvent

**Description:** Immutable append-only audit trail logging all lifecycle state transitions across Purchase Orders, Production Plans, and Shortage events. Preserves complete historical traceability without destructive overwrites.

**File:** `data/transactions/state_transition_events.csv`  
**Primary Key:** `event_id`  

### Columns

| Column | Data Type | Required | Allowed Values / Format | Units | Unique | Validation Rule | Description |
|---|---|---|---|---|---|---|---|
| `event_id` | string | ✅ | `EVT-NNNNNNNN` | — | ✅ | Sequential unique ID | Primary key for audit record. |
| `entity_type` | string | ✅ | `PurchaseOrder`, `ProductionPlan`, `Shortage` | — | ❌ | Must be valid entity | Target domain entity name. |
| `entity_id` | string | ✅ | Valid ID format | — | ❌ | FK to parent entity | Unique identifier of affected entity. |
| `event_timestamp` | string | ✅ | ISO datetime or week label | — | ❌ | Valid date format | Timestamp when transition occurred. |
| `from_state` | string | ✅ | Valid lifecycle state | — | ❌ | Allowed enum value | Prior status before transition. |
| `to_state` | string | ✅ | Valid lifecycle state | — | ❌ | Allowed enum value | Resulting status after transition. |
| `actor_role` | string | ✅ | `supplier`, `planner`, `carrier/warehouse operator`, `logistics analyst`, `operations manager` | — | ❌ | One of 5 primary actors | Actor or system driving the transition. |
| `quantity_impact` | float | ❌ | Numeric | UOM | ❌ | Signed float | Quantity added or deducted by the event. |
| `rationale` | string | ✅ | Free text | — | ❌ | Non-empty | Operational justification for the state change. |

---

## 13. Relationship Summary

### Cardinality Matrix

| From Entity | Relationship | To Entity | Cardinality | Via |
|---|---|---|---|---|
| SKU | has many | ForecastDemand | 1 : N | `sku_id` |
| SKU | has many | Inventory | 1 : N | `sku_id` |
| SKU | has many | PurchaseOrder | 1 : N | `sku_id` |
| SKU | has many | ProductionPlan | 1 : N | `sku_id` (as finished good) |
| SKU | has many | ProductionPlan | 1 : N | `bom_sku_id` (as component) |
| SKU | has many | Shortage | 1 : N | `sku_id` |
| SKU | supplied by many | Supplier | N : M | `SupplierCapacity` bridge |
| SKU | substitutes | SKU | N : 1 | `substitute_sku_id` (self-ref) |
| Location | has many | ForecastDemand | 1 : N | `location_id` |
| Location | has many | Inventory | 1 : N | `location_id` |
| Location | has many | PurchaseOrder | 1 : N | `location_id` |
| Location | has many | ProductionPlan | 1 : N | `location_id` |
| Location | has many | Shortage | 1 : N | `location_id` |
| Location | served by many | Supplier | N : M | `LeadTime` bridge |
| Supplier | has many | PurchaseOrder | 1 : N | `supplier_id` |
| Supplier | supplies many | SKU | N : M | `SupplierCapacity` bridge |
| Supplier | serves many | Location | N : M | `LeadTime` bridge |
| Shortage | has many | MitigationOption | 1 : N | `shortage_id` |

### Bridge Tables

| Bridge Table | Connects | Left FK | Right FK | Additional Attributes |
|---|---|---|---|---|
| **SupplierCapacity** | Supplier ↔ SKU | `supplier_id` | `sku_id` | `max_weekly_capacity`, `min_order_qty`, `uom`, effective dates, `status` |
| **LeadTime** | Supplier ↔ Location | `supplier_id` | `location_id` | `transit_days`, `transport_mode`, effective dates |

---

## 13. State Lifecycles

### Purchase Order Lifecycle

```
OPEN → CONFIRMED → IN_TRANSIT → RECEIVED
                              ↘ CANCELLED
OPEN → CANCELLED  (can also be cancelled early)
```

| Status | Description | PAB Contribution |
|---|---|---|
| `OPEN` | Order placed, not yet confirmed by supplier | ✅ Counted as expected supply |
| `CONFIRMED` | Supplier confirmed; preparing shipment | ✅ Counted as expected supply |
| `IN_TRANSIT` | Goods shipped, in transit | ✅ Counted as expected supply |
| `RECEIVED` | Goods delivered and received into inventory | ❌ Already in `on_hand_qty` |
| `CANCELLED` | Order cancelled | ❌ Not counted |

### Production Plan Lifecycle

```
PLANNED → IN_PROGRESS → COMPLETED
                       ↘ CANCELLED
PLANNED → CANCELLED  (can also be cancelled early)
```

| Status | Description | PAB Contribution |
|---|---|---|
| `PLANNED` | Production scheduled but not started | ✅ Counted as expected supply |
| `IN_PROGRESS` | Currently being manufactured | ✅ Counted as expected supply |
| `COMPLETED` | Production finished, output in inventory | ❌ Already in `on_hand_qty` |
| `CANCELLED` | Production cancelled | ❌ Not counted |

---

## 14. Data Volume Summary (Full Scale)

| Entity | Approx. Records | File |
|---|---|---|
| SKU | 3,000 | `data/master/skus.csv` |
| Location | 50 | `data/master/locations.csv` |
| Supplier | 500 | `data/master/suppliers.csv` |
| SupplierCapacity | 6,000–15,000 | `data/master/supplier_capacities.csv` |
| LeadTime | 5,000–12,000 | `data/master/lead_times.csv` |
| ForecastDemand | ~624,000 | `data/transactions/forecast_demand.csv` |
| Inventory | ~12,000 | `data/transactions/inventory.csv` |
| PurchaseOrder | 10,000 | `data/transactions/purchase_orders.csv` |
| ProductionPlan | Varies | `data/transactions/production_plans.csv` |
| Shortage | Varies | `data/computed/shortages.csv` |
| MitigationOption | Shortages × ≤4 | `data/computed/mitigation_options.csv` |

> [!NOTE]
> Record counts with `SCALE_FACTOR = 0.05` are proportionally smaller (e.g., 150 SKUs, 25 suppliers) except for `NUM_LOCATIONS` which has a floor of 10.
