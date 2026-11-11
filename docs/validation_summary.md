# Validation Summary

**Generated**: 2026-11-11T23:04:14.882470

| Status | Count |
|--------|-------|
| ✅ PASS | 57 |
| ❌ FAIL | 0 |
| ⚠️  WARN | 2 |
| **Total** | **59** |

## Detailed Results

| Status | Entity | Check | Message | Details |
|--------|--------|-------|---------|--------|
| ✅ | SKU | pk_uniqueness | All 150 sku_id values are unique. | — |
| ✅ | Location | pk_uniqueness | All 10 location_id values are unique. | — |
| ✅ | Supplier | pk_uniqueness | All 25 supplier_id values are unique. | — |
| ✅ | SupplierCapacity | pk_uniqueness | All 195 supplier_capacity_id values are unique. | — |
| ✅ | LeadTime | pk_uniqueness | All 173 lead_time_id values are unique. | — |
| ✅ | ForecastDemand | pk_uniqueness | All 31304 demand_id values are unique. | — |
| ✅ | Inventory | pk_uniqueness | All 602 inventory_id values are unique. | — |
| ⚠️ | PurchaseOrder | pk_uniqueness | 2 duplicate po_id values found, matching labeled 'inbound_counted_twice' edge cases in ground truth. | Labeled duplicate IDs: ['PO-2026-000106', 'PO-2026-000220'] |
| ✅ | ProductionPlan | pk_uniqueness | All 1968 production_plan_id values are unique. | — |
| ✅ | Shortage | pk_uniqueness | All 681 shortage_id values are unique. | — |
| ✅ | MitigationOption | pk_uniqueness | All 1724 mitigation_id values are unique. | — |
| ✅ | SKU.substitute_sku_id→SKU (substitute).sku_id | fk_integrity | All 52 foreign keys resolve. | — |
| ✅ | SupplierCapacity.supplier_id→Supplier.supplier_id | fk_integrity | All 195 foreign keys resolve. | — |
| ✅ | SupplierCapacity.sku_id→SKU.sku_id | fk_integrity | All 195 foreign keys resolve. | — |
| ✅ | LeadTime.supplier_id→Supplier.supplier_id | fk_integrity | All 173 foreign keys resolve. | — |
| ✅ | LeadTime.location_id→Location.location_id | fk_integrity | All 173 foreign keys resolve. | — |
| ✅ | ForecastDemand.sku_id→SKU.sku_id | fk_integrity | All 31304 foreign keys resolve. | — |
| ✅ | ForecastDemand.location_id→Location.location_id | fk_integrity | All 31304 foreign keys resolve. | — |
| ✅ | Inventory.sku_id→SKU.sku_id | fk_integrity | All 602 foreign keys resolve. | — |
| ✅ | Inventory.location_id→Location.location_id | fk_integrity | All 602 foreign keys resolve. | — |
| ✅ | PurchaseOrder.supplier_id→Supplier.supplier_id | fk_integrity | All 502 foreign keys resolve. | — |
| ✅ | PurchaseOrder.sku_id→SKU.sku_id | fk_integrity | All 502 foreign keys resolve. | — |
| ✅ | PurchaseOrder.location_id→Location.location_id | fk_integrity | All 502 foreign keys resolve. | — |
| ✅ | ProductionPlan.sku_id→SKU.sku_id | fk_integrity | All 1968 foreign keys resolve. | — |
| ✅ | ProductionPlan.location_id→Location.location_id | fk_integrity | All 1968 foreign keys resolve. | — |
| ✅ | Shortage.sku_id→SKU.sku_id | fk_integrity | All 681 foreign keys resolve. | — |
| ✅ | Shortage.location_id→Location.location_id | fk_integrity | All 681 foreign keys resolve. | — |
| ✅ | MitigationOption.shortage_id→Shortage.shortage_id | fk_integrity | All 1724 foreign keys resolve. | — |
| ✅ | SKU.category | enum_values | All values in allowed set: ['Electronics', 'Automotive', 'Consumer Goods', 'Pharmaceuticals', 'Industrial', 'Food & Beverage', 'Chemicals', 'Textiles', 'Packaging', 'Components'] | — |
| ✅ | SKU.uom | enum_values | All values in allowed set: ['EA', 'KG', 'LT', 'BOX', 'PALLET'] | — |
| ✅ | SKU.status | enum_values | All values in allowed set: ['ACTIVE', 'DISCONTINUED', 'ON_HOLD'] | — |
| ✅ | Location.type | enum_values | All values in allowed set: ['WAREHOUSE', 'DISTRIBUTION_CENTER', 'PLANT'] | — |
| ✅ | Location.region | enum_values | All values in allowed set: ['North', 'South', 'East', 'West', 'Central'] | — |
| ✅ | Supplier.payment_terms | enum_values | All values in allowed set: ['NET30', 'NET45', 'NET60', 'NET90'] | — |
| ✅ | Supplier.status | enum_values | All values in allowed set: ['ACTIVE', 'INACTIVE', 'SUSPENDED'] | — |
| ✅ | LeadTime.transport_mode | enum_values | All values in allowed set: ['ROAD', 'RAIL', 'SEA', 'AIR'] | — |
| ✅ | ForecastDemand.demand_type | enum_values | All values in allowed set: ['REGULAR', 'PROMOTIONAL'] | — |
| ✅ | PurchaseOrder.status | enum_values | All values in allowed set: ['OPEN', 'CONFIRMED', 'IN_TRANSIT', 'RECEIVED', 'CANCELLED'] | — |
| ✅ | ProductionPlan.status | enum_values | All values in allowed set: ['PLANNED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED'] | — |
| ✅ | Shortage.severity | enum_values | All values in allowed set: ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'] | — |
| ✅ | MitigationOption.mitigation_type | enum_values | All values in allowed set: ['EXPEDITE_PO', 'ALTERNATE_SUPPLIER', 'SUBSTITUTE_SKU', 'INCREASE_PRODUCTION', 'REDISTRIBUTE_INVENTORY', 'PARTIAL_FULFILLMENT', 'BACKORDER'] | — |
| ✅ | ForecastDemand.quantity | positive_values | All 31304 values are positive. | — |
| ✅ | Inventory.on_hand_qty | positive_values | All 602 values are non-negative. | — |
| ✅ | PurchaseOrder.quantity | positive_values | All 502 values are positive. | — |
| ✅ | SupplierCapacity.max_weekly_capacity | positive_values | All 195 values are positive. | — |
| ✅ | SupplierCapacity.min_order_qty | positive_values | All 195 values are positive. | — |
| ✅ | SupplierCapacity.effective_from<=effective_to | date_order | All date orderings valid (195 checked). | — |
| ✅ | LeadTime.effective_from<=effective_to | date_order | All date orderings valid (173 checked). | — |
| ✅ | PurchaseOrder.order_date<=expected_delivery_date | date_order | All date orderings valid (502 checked). | — |
| ✅ | PurchaseOrder.total_cost | arithmetic_reconciliation | total_cost = quantity × unit_cost: 0 mismatches out of 502. | — |
| ✅ | ForecastDemand.week | week_range | Weeks out of [1,52] range: 0 | — |
| ✅ | SupplierCapacity | moq_vs_capacity | MOQ > max_weekly_capacity: 0 records | — |
| ✅ | Supplier.reliability_score | score_range | Values outside [0,1]: 0 | — |
| ✅ | SKU | full_row_duplicates | 0 fully duplicated rows. | — |
| ✅ | ForecastDemand | full_row_duplicates | 0 fully duplicated rows. | — |
| ⚠️ | PurchaseOrder | full_row_duplicates | 2 fully duplicated rows. | — |
| ✅ | PurchaseOrder.RECEIVED | lifecycle_transition | All 188 RECEIVED orders have recorded delivery dates. | — |
| ✅ | PurchaseOrder.OPEN_or_CONFIRMED | lifecycle_transition | All 172 pending orders have null actual_delivery_date. | — |
| ✅ | ProductionPlan.COMPLETED | lifecycle_transition | All 793 COMPLETED production plans have recorded actual_quantity. | — |
