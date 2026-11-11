"""
Central configuration for the YottaFlex Supply Chain Shortage Prioritization System.

All parameters — seed, volumes, naming conventions, and business rules — are
defined here so that every module in the project draws from one source of truth.
"""

# ─────────────────────────── reproducibility ───────────────────────────
RANDOM_SEED = 20261022

# ─────────────────────────── volume parameters ─────────────────────────
# "starter" vs "full" controlled by SCALE_FACTOR (1.0 = full)
SCALE_FACTOR = 1.0            # set to 0.05 for a quick starter run

NUM_SKUS           = int(3_000  * SCALE_FACTOR)
NUM_LOCATIONS      = int(50     * max(SCALE_FACTOR, 0.2))   # keep at least 10
NUM_SUPPLIERS      = int(500    * SCALE_FACTOR)
NUM_PURCHASE_ORDERS = int(10_000 * SCALE_FACTOR)
NUM_WEEKS          = 52        # always 52 weeks for 2026

# Derived: each SKU is stocked at AVG_LOCATIONS_PER_SKU locations
AVG_LOCATIONS_PER_SKU = 4      # gives ~12,000 SKU-location demand pairs at full scale

# ─────────────────────────── time horizon ──────────────────────────────
YEAR = 2026
WEEK_START = 1
WEEK_END   = 52

# ─────────────────────────── ID formats ────────────────────────────────
def sku_id(n: int) -> str:
    return f"SKU-{n:06d}"

def location_id(n: int) -> str:
    return f"LOC-{n:03d}"

def supplier_id(n: int) -> str:
    return f"SUP-{n:06d}"

def demand_id(sku: str, loc: str, week: int) -> str:
    return f"DEM-{sku}-{loc}-{YEAR}W{week:02d}"

def purchase_order_id(n: int) -> str:
    return f"PO-{YEAR}-{n:06d}"

def shortage_id(n: int) -> str:
    return f"SHORT-{YEAR}-{n:06d}"

def mitigation_id(short_id: str, seq: int) -> str:
    return f"MIT-{short_id}-{seq:02d}"

def supplier_capacity_id(n: int) -> str:
    return f"SC-{n:06d}"

def lead_time_id(n: int) -> str:
    return f"LT-{n:06d}"

def inventory_id(n: int) -> str:
    return f"INV-{n:06d}"

def production_plan_id(n: int) -> str:
    return f"PP-{n:06d}"

def bom_id(n: int) -> str:
    return f"BOM-{n:06d}"

# ─────────────────────────── business rules ────────────────────────────
SAFETY_STOCK_WEEKS = 2                  # default safety stock = 2 weeks of avg demand
SHORTAGE_THRESHOLD = 0                  # PAB < this triggers shortage
MAX_MITIGATIONS_PER_SHORTAGE = 4

# Demand spike parameters
DEMAND_SPIKE_PROBABILITY = 0.05         # 5% of demand rows get a spike
DEMAND_SPIKE_MULTIPLIER_RANGE = (2.0, 5.0)

# Supplier constraint parameters
CONSTRAINED_SUPPLIER_FRACTION = 0.15    # 15% of suppliers are capacity-constrained
TRANSPORT_DELAY_PROBABILITY = 0.08      # 8% chance of transit delay per PO

# Edge-case injection rates (Step 5)
EDGE_CASE_RATES = {
    "inbound_counted_twice":          0.005,   # 0.5% of POs
    "substitute_not_approved":        0.01,    # 1% of SKUs with substitutes
    "supplier_capacity_exceeded":     0.02,    # 2% of supplier-capacity records
    "shortage_without_lead_time":     0.005,   # 0.5% of shortages
    "uom_mismatch":                   0.005,   # 0.5% of supplier-capacity records
}

# ─────────────────────────── categories / enums ────────────────────────
SKU_CATEGORIES = [
    "Electronics", "Automotive", "Consumer Goods",
    "Pharmaceuticals", "Industrial", "Food & Beverage",
    "Chemicals", "Textiles", "Packaging", "Components",
]

UNITS_OF_MEASURE = ["EA", "KG", "LT", "BOX", "PALLET"]

LOCATION_TYPES = ["WAREHOUSE", "DISTRIBUTION_CENTER", "PLANT"]

REGIONS = ["North", "South", "East", "West", "Central"]

SUPPLIER_PAYMENT_TERMS = ["NET30", "NET45", "NET60", "NET90"]

TRANSPORT_MODES = ["ROAD", "RAIL", "SEA", "AIR"]

PO_STATUSES = ["OPEN", "CONFIRMED", "IN_TRANSIT", "RECEIVED", "CANCELLED"]

SHORTAGE_SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

MITIGATION_TYPES = [
    "EXPEDITE_PO",
    "ALTERNATE_SUPPLIER",
    "SUBSTITUTE_SKU",
    "INCREASE_PRODUCTION",
    "REDISTRIBUTE_INVENTORY",
    "PARTIAL_FULFILLMENT",
    "BACKORDER",
]

# ─────────────────────────── output paths ──────────────────────────────
import os
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

MASTER_DIR       = os.path.join(DATA_DIR, "master")
TRANSACTION_DIR  = os.path.join(DATA_DIR, "transactions")
COMPUTED_DIR     = os.path.join(DATA_DIR, "computed")
GROUND_TRUTH_DIR = os.path.join(DATA_DIR, "ground_truth")

OUTPUT_DIRS = [MASTER_DIR, TRANSACTION_DIR, COMPUTED_DIR, GROUND_TRUTH_DIR]
