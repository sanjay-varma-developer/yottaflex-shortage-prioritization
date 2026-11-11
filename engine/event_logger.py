"""
Event history and state transition logger for supply chain transactions.

Fulfills Business Workflow Rule 4:
  "Persist state changes as explicit records/events where relevant;
   do not overwrite history."
and Entities & Relationships specification:
  "retain event history for state changes; validate all joins."
"""

import os
import sys
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def generate_state_transition_events(data: dict) -> pd.DataFrame:
    """
    Generate an immutable audit trail of state transitions across key transactions.

    Tracks:
      - PurchaseOrder lifecycles (OPEN -> CONFIRMED -> IN_TRANSIT -> RECEIVED / CANCELLED)
      - ProductionPlan lifecycles (PLANNED -> IN_PROGRESS -> COMPLETED)
      - Shortage event lifecycles (DETECTED -> MITIGATION_EVALUATED -> MITIGATION_RECOMMENDED)

    Parameters
    ----------
    data : dict
        Dictionary of generated tables.

    Returns
    -------
    pd.DataFrame
        Columns: event_id, entity_type, entity_id, event_timestamp,
                 from_state, to_state, actor_role, quantity_impact, rationale.
    """
    events = []
    counter = 1

    pos = data.get("purchase_orders", pd.DataFrame())
    if not pos.empty:
        for row in pos.itertuples(index=False):
            # 1. Order Creation Event
            events.append({
                "event_id": f"EVT-{counter:08d}",
                "entity_type": "PurchaseOrder",
                "entity_id": row.po_id,
                "event_timestamp": str(row.order_date),
                "from_state": "NONE",
                "to_state": "OPEN",
                "actor_role": "planner",
                "quantity_impact": row.quantity,
                "rationale": f"Replenishment order created for SKU {row.sku_id} at location {row.location_id}",
            })
            counter += 1

            # 2. Confirmation Event
            if row.status in ["CONFIRMED", "IN_TRANSIT", "RECEIVED"]:
                events.append({
                    "event_id": f"EVT-{counter:08d}",
                    "entity_type": "PurchaseOrder",
                    "entity_id": row.po_id,
                    "event_timestamp": str(row.order_date),
                    "from_state": "OPEN",
                    "to_state": "CONFIRMED",
                    "actor_role": "supplier",
                    "quantity_impact": row.quantity,
                    "rationale": f"Supplier {row.supplier_id} accepted purchase order",
                })
                counter += 1

            # 3. Transit Event
            if row.status in ["IN_TRANSIT", "RECEIVED"]:
                events.append({
                    "event_id": f"EVT-{counter:08d}",
                    "entity_type": "PurchaseOrder",
                    "entity_id": row.po_id,
                    "event_timestamp": str(row.order_date),
                    "from_state": "CONFIRMED",
                    "to_state": "IN_TRANSIT",
                    "actor_role": "carrier/warehouse operator",
                    "quantity_impact": row.quantity,
                    "rationale": "Shipment picked up by logistics carrier",
                })
                counter += 1

            # 4. Receipt Event
            if row.status == "RECEIVED" and pd.notna(row.actual_delivery_date):
                events.append({
                    "event_id": f"EVT-{counter:08d}",
                    "entity_type": "PurchaseOrder",
                    "entity_id": row.po_id,
                    "event_timestamp": str(row.actual_delivery_date),
                    "from_state": "IN_TRANSIT",
                    "to_state": "RECEIVED",
                    "actor_role": "carrier/warehouse operator",
                    "quantity_impact": row.quantity,
                    "rationale": f"Shipment received into inventory at location {row.location_id}",
                })
                counter += 1

            # 5. Cancellation Event
            if row.status == "CANCELLED":
                events.append({
                    "event_id": f"EVT-{counter:08d}",
                    "entity_type": "PurchaseOrder",
                    "entity_id": row.po_id,
                    "event_timestamp": str(row.expected_delivery_date),
                    "from_state": "OPEN",
                    "to_state": "CANCELLED",
                    "actor_role": "operations manager",
                    "quantity_impact": -row.quantity,
                    "rationale": "Order cancelled due to supplier constraints or route disruptions",
                })
                counter += 1

    # Production Plan events
    prod = data.get("production_plans", pd.DataFrame())
    if not prod.empty:
        for row in prod.itertuples(index=False):
            events.append({
                "event_id": f"EVT-{counter:08d}",
                "entity_type": "ProductionPlan",
                "entity_id": row.production_plan_id,
                "event_timestamp": f"{row.year}-W{row.week:02d}",
                "from_state": "NONE",
                "to_state": row.status,
                "actor_role": "operations manager",
                "quantity_impact": row.planned_quantity,
                "rationale": f"Production batch scheduled at plant {row.location_id} using BOM {row.bom_sku_id}",
            })
            counter += 1

    # Shortage decision events
    shortages = data.get("shortages", pd.DataFrame())
    if not shortages.empty:
        for row in shortages.itertuples(index=False):
            events.append({
                "event_id": f"EVT-{counter:08d}",
                "entity_type": "Shortage",
                "entity_id": row.shortage_id,
                "event_timestamp": f"2026-W{row.first_shortage_week:02d}",
                "from_state": "NORMAL",
                "to_state": f"SHORTAGE_{row.severity}",
                "actor_role": "planner",
                "quantity_impact": -row.shortage_quantity,
                "rationale": f"Deficit triggered: root cause={row.root_cause}, duration={row.duration_weeks}wks",
            })
            counter += 1

    return pd.DataFrame(events)
