"""
Actor-specific view generators and reporting pipelines.

Fulfills Primary Actors / Systems requirements:
  "Primary Actors / Systems: Supplier, planner, carrier/warehouse operator,
   logistics analyst and operations manager"
  "The solution should expose key decisions and exceptions,
   preserve traceability, and produce measurable outputs."
"""

import os
import sys
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def generate_planner_view(shortages_df: pd.DataFrame, mitigations_df: pd.DataFrame) -> pd.DataFrame:
    """
    Generate prioritized action dashboard for Demand and Supply Planners.

    Focuses on:
      - Shortages sorted by priority score (financial impact)
      - Recommended mitigation option with expected cost delta and feasibility
      - Immediate action required
    """
    if shortages_df.empty:
        return pd.DataFrame()

    rec_mits = mitigations_df[mitigations_df["recommended"] == True].copy() if not mitigations_df.empty else pd.DataFrame()

    merged = shortages_df.merge(
        rec_mits[["shortage_id", "mitigation_type", "description", "feasibility_score", "estimated_total_cost", "estimated_lead_time_days"]],
        on="shortage_id",
        how="left"
    )

    merged = merged.sort_values(by="priority_score", ascending=False).reset_index(drop=True)
    merged["planner_action_urgency"] = merged["severity"].map({
        "CRITICAL": "IMMEDIATE (Within 24h)",
        "HIGH": "HIGH PRIORITY (Within 48h)",
        "MEDIUM": "MEDIUM PRIORITY (Next S&OP Cycle)",
        "LOW": "ROUTINE REVIEW",
    })

    return merged[[
        "shortage_id", "sku_id", "location_id", "severity", "planner_action_urgency",
        "priority_score", "root_cause", "first_shortage_week", "duration_weeks",
        "shortage_quantity", "mitigation_type", "description", "feasibility_score",
        "estimated_total_cost", "estimated_lead_time_days"
    ]]


def generate_operations_summary(data: dict, shortages_df: pd.DataFrame, balance_df: pd.DataFrame) -> dict:
    """
    Generate executive KPI scorecard for Operations Managers.

    Measures macro health:
      - Total demand units vs projected stockout exposure
      - Plant manufacturing utilization
      - Shortage distribution by severity
      - Estimated stockout financial risk
    """
    demand = data.get("forecast_demand", pd.DataFrame())
    skus = data.get("skus", pd.DataFrame())
    prod = data.get("production_plans", pd.DataFrame())

    total_demand_qty = int(demand["quantity"].sum()) if not demand.empty else 0
    total_shortage_events = len(shortages_df) if not shortages_df.empty else 0
    total_shortage_qty = int(shortages_df["shortage_quantity"].sum()) if not shortages_df.empty else 0
    total_financial_exposure = float(shortages_df["priority_score"].sum()) if not shortages_df.empty else 0.0

    avg_plant_utilization = float(prod["capacity_utilized_pct"].mean()) if not prod.empty and "capacity_utilized_pct" in prod.columns else 0.0

    severity_breakdown = shortages_df["severity"].value_counts().to_dict() if not shortages_df.empty else {}
    root_cause_breakdown = shortages_df["root_cause"].value_counts().to_dict() if not shortages_df.empty else {}

    return {
        "macro_metrics": {
            "total_forecast_demand_units": total_demand_qty,
            "total_shortage_events": total_shortage_events,
            "total_shortage_units_at_risk": total_shortage_qty,
            "total_financial_exposure_usd": round(total_financial_exposure, 2),
            "service_level_risk_pct": round((total_shortage_qty / max(1, total_demand_qty)) * 100, 2),
            "average_plant_utilization_pct": round(avg_plant_utilization, 2),
        },
        "severity_distribution": severity_breakdown,
        "root_cause_distribution": root_cause_breakdown,
        "active_sku_count": len(skus[skus["status"] == "ACTIVE"]) if not skus.empty else 0,
        "total_sku_count": len(skus) if not skus.empty else 0,
    }


def generate_logistics_analyst_view(data: dict) -> pd.DataFrame:
    """
    Generate freight, lead time, and delay analysis for Logistics Analysts.

    Highlights:
      - Inbound shipments experiencing transit delay
      - Transport mode lane reliability
      - Expedited freight candidates
    """
    pos = data.get("purchase_orders", pd.DataFrame())
    lead_times = data.get("lead_times", pd.DataFrame())

    if pos.empty:
        return pd.DataFrame()

    po_copy = pos.copy()
    po_copy["expected_delivery_date"] = pd.to_datetime(po_copy["expected_delivery_date"])
    po_copy["actual_delivery_date"] = pd.to_datetime(po_copy["actual_delivery_date"])

    po_copy["is_delayed"] = po_copy["actual_delivery_date"] > po_copy["expected_delivery_date"]
    po_copy["delay_days"] = (po_copy["actual_delivery_date"] - po_copy["expected_delivery_date"]).dt.days.fillna(0).astype(int)

    # Merge transport mode if possible
    if not lead_times.empty:
        lt_modes = lead_times.drop_duplicates(subset=["supplier_id", "location_id"])[["supplier_id", "location_id", "transport_mode"]]
        po_copy = po_copy.merge(lt_modes, on=["supplier_id", "location_id"], how="left")

    return po_copy[[
        "po_id", "supplier_id", "sku_id", "location_id", "week", "quantity",
        "order_date", "expected_delivery_date", "actual_delivery_date",
        "status", "is_delayed", "delay_days"
    ] + (["transport_mode"] if "transport_mode" in po_copy.columns else [])]


def generate_supplier_scorecard(data: dict, mitigations_df: pd.DataFrame) -> pd.DataFrame:
    """
    Generate supplier performance scorecard and capacity utilization.

    Tracks:
      - Supplier reliability rating
      - Number of POs fulfilled and delayed
      - Number of times tapped for expedited replenishment
    """
    suppliers = data.get("suppliers", pd.DataFrame())
    pos = data.get("purchase_orders", pd.DataFrame())

    if suppliers.empty:
        return pd.DataFrame()

    scorecard = suppliers[["supplier_id", "name", "country", "reliability_score", "payment_terms", "status", "certified"]].copy()

    if not pos.empty:
        po_stats = pos.groupby("supplier_id").agg(
            total_orders=("po_id", "count"),
            total_units_ordered=("quantity", "sum"),
            total_spend=("total_cost", "sum")
        ).reset_index()
        scorecard = scorecard.merge(po_stats, on="supplier_id", how="left").fillna(0)
    else:
        scorecard["total_orders"] = 0
        scorecard["total_units_ordered"] = 0
        scorecard["total_spend"] = 0.0

    return scorecard


def generate_warehouse_schedule(data: dict, balance_df: pd.DataFrame) -> pd.DataFrame:
    """
    Generate weekly inbound schedule and safety stock alerts for Carrier/Warehouse Operators.

    Tracks:
      - Weekly inbound delivery volume by location
      - Weeks where safety stock is breached
    """
    if balance_df.empty:
        return pd.DataFrame()

    wh_view = balance_df[[
        "location_id", "sku_id", "week", "week_label",
        "beginning_balance", "scheduled_receipts", "forecast_demand",
        "ending_balance", "safety_stock_qty", "is_below_safety", "is_shortage"
    ]].copy()

    return wh_view[wh_view["is_below_safety"] | wh_view["is_shortage"] | (wh_view["scheduled_receipts"] > 0)].reset_index(drop=True)


def print_actor_summary(actor: str, data: dict) -> None:
    """Print an executive summary tailored to a specific Primary Actor role."""
    shortages_df = data.get("shortages", pd.DataFrame())
    mitigations_df = data.get("mitigations", pd.DataFrame())
    balance_df = data.get("projected_balance", pd.DataFrame())

    actor_lower = actor.lower()

    if actor_lower in ["planner", "all"]:
        print("\n" + "═" * 78)
        print("  DEMAND & SUPPLY PLANNER DASHBOARD — TOP PRIORITIZED SHORTAGES")
        print("═" * 78)
        planner_view = generate_planner_view(shortages_df, mitigations_df)
        if not planner_view.empty:
            print(f"  Total Shortage Incidents: {len(planner_view):,}")
            print("  Top 5 Actionable Shortages by Financial Exposure Score:\n")
            top5 = planner_view.head(5)
            for idx, r in top5.iterrows():
                print(f"  [{r['severity']}] {r['shortage_id']} | SKU: {r['sku_id']} @ {r['location_id']} (Wk {r['first_shortage_week']:02d}, {r['duration_weeks']} wks)")
                print(f"      Deficit: {r['shortage_quantity']:,} units | Root Cause: {r['root_cause']} | Exposure: ${r['priority_score']:,.2f}")
                print(f"      Action ({r['planner_action_urgency']}): Recommended '{r['mitigation_type']}' (Feasibility: {r['feasibility_score']*100:.0f}%, +${r['estimated_total_cost']:,.2f})")
                print("      " + "-" * 70)
        else:
            print("  No shortages detected.")

    if actor_lower in ["operations", "ops", "all"]:
        print("\n" + "═" * 78)
        print("  OPERATIONS MANAGER SCORECARD — MACRO KPIs")
        print("═" * 78)
        ops_summary = generate_operations_summary(data, shortages_df, balance_df)
        macro = ops_summary.get("macro_metrics", {})
        print(f"  Total Annual Demand Units       : {macro.get('total_forecast_demand_units', 0):>15,}")
        print(f"  Total Shortage Deficit Units     : {macro.get('total_shortage_units_at_risk', 0):>15,}")
        print(f"  Service Level Risk Ratio         : {macro.get('service_level_risk_pct', 0):>14.2f}%")
        print(f"  Aggregate Financial Exposure     : ${macro.get('total_financial_exposure_usd', 0):>14,.2f}")
        print(f"  Average Plant Capacity Utilized  : {macro.get('average_plant_utilization_pct', 0):>14.2f}%")
        print("  Severity Breakdown:")
        for sev, count in ops_summary.get("severity_distribution", {}).items():
            print(f"    - {sev:<12s}: {count:>8,}")

    if actor_lower in ["logistics", "all"]:
        print("\n" + "═" * 78)
        print("  LOGISTICS ANALYST REPORT — TRANSIT PERFORMANCE & DELAYS")
        print("═" * 78)
        logistics_view = generate_logistics_analyst_view(data)
        if not logistics_view.empty:
            total_orders = len(logistics_view)
            delayed = logistics_view[logistics_view["is_delayed"] == True]
            delayed_count = len(delayed)
            avg_delay = delayed["delay_days"].mean() if delayed_count > 0 else 0.0
            print(f"  Total Purchase Orders Analyzed   : {total_orders:>12,}")
            print(f"  Shipments Delayed in Transit     : {delayed_count:>12,} ({(delayed_count/max(1,total_orders))*100:.1f}%)")
            print(f"  Average Delivery Lag for Delayed : {avg_delay:>12.1f} days")
            if "transport_mode" in logistics_view.columns:
                print("  Orders by Freight Mode:")
                for mode, count in logistics_view["transport_mode"].value_counts().items():
                    print(f"    - {mode:<8s}: {count:>8,}")

    if actor_lower in ["supplier", "all"]:
        print("\n" + "═" * 78)
        print("  SUPPLIER OPERATIONS SCORECARD")
        print("═" * 78)
        supplier_view = generate_supplier_scorecard(data, mitigations_df)
        if not supplier_view.empty:
            active_sups = supplier_view[supplier_view["status"] == "ACTIVE"]
            avg_rel = active_sups["reliability_score"].mean() if not active_sups.empty else 0.0
            print(f"  Active Suppliers Monitored       : {len(active_sups):>12,}")
            print(f"  Average Supplier Reliability     : {avg_rel*100:>11.1f}%")
            print("  Top 3 Strategic Suppliers by Inbound Volume:")
            top3 = supplier_view.sort_values(by="total_units_ordered", ascending=False).head(3)
            for _, r in top3.iterrows():
                print(f"    - {r['supplier_id']} ({r['name']}) | Country: {r['country']} | Units: {int(r['total_units_ordered']):,} | Spend: ${r['total_spend']:,.2f}")

    if actor_lower in ["warehouse", "carrier", "all"]:
        print("\n" + "═" * 78)
        print("  CARRIER / WAREHOUSE OPERATOR RECEIVING SCHEDULE")
        print("═" * 78)
        wh_view = generate_warehouse_schedule(data, balance_df)
        if not wh_view.empty:
            safety_breaches = wh_view["is_below_safety"].sum()
            stockouts = wh_view["is_shortage"].sum()
            print(f"  Active Receiving Schedule Rows   : {len(wh_view):>12,}")
            print(f"  Safety Stock Threshold Breaches  : {safety_breaches:>12,}")
            print(f"  Projected Stockout Week-Rows     : {stockouts:>12,}")

    print("═" * 78 + "\n")
