"""
Master data generators for SKUs, Locations, and Suppliers.

These are the foundational/parent tables that all other data depends on.
"""

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def generate_skus(rng: np.random.RandomState) -> pd.DataFrame:
    """Generate the SKU master table.

    Parameters
    ----------
    rng : np.random.RandomState
        Seeded random state for reproducibility.

    Returns
    -------
    pd.DataFrame
        DataFrame with NUM_SKUS rows and columns:
        sku_id, name, category, subcategory, uom, weight_kg, unit_cost,
        substitute_sku_id, substitute_approved, status, created_at.
    """
    n = config.NUM_SKUS

    # Basic identifiers
    ids = [config.sku_id(i + 1) for i in range(n)]
    categories = rng.choice(config.SKU_CATEGORIES, size=n)

    # Subcategories — simple suffix within category
    subcategory_map = {
        "Electronics": ["Sensors", "Connectors", "Boards", "Displays"],
        "Automotive": ["Engine", "Chassis", "Interior", "Electrical"],
        "Consumer Goods": ["Personal Care", "Household", "Appliances", "Tools"],
        "Pharmaceuticals": ["OTC", "Prescription", "Raw API", "Excipients"],
        "Industrial": ["Bearings", "Valves", "Motors", "Pumps"],
        "Food & Beverage": ["Dairy", "Grains", "Beverages", "Additives"],
        "Chemicals": ["Solvents", "Acids", "Polymers", "Catalysts"],
        "Textiles": ["Woven", "Knitted", "Nonwoven", "Yarn"],
        "Packaging": ["Cartons", "Films", "Bottles", "Labels"],
        "Components": ["Fasteners", "Gaskets", "Springs", "Seals"],
    }
    subcategories = [
        rng.choice(subcategory_map.get(cat, ["General"])) for cat in categories
    ]

    names = [f"{cat} Part {i + 1}" for i, cat in enumerate(categories)]
    uoms = rng.choice(config.UNITS_OF_MEASURE, size=n)
    weights = np.round(rng.uniform(0.1, 50.0, size=n), 2)
    unit_costs = np.round(rng.uniform(5.0, 500.0, size=n), 2)

    # Substitutes — ~30 % of SKUs have one, pointing to another random SKU
    substitute_mask = rng.random(n) < 0.30
    substitute_ids = [None] * n
    for i in range(n):
        if substitute_mask[i]:
            # Pick a different SKU
            target = rng.randint(0, n)
            while target == i:
                target = rng.randint(0, n)
            substitute_ids[i] = ids[target]

    # substitute_approved — True for most, False for a few edge cases (~5 % of those with subs)
    substitute_approved = [None] * n
    for i in range(n):
        if substitute_ids[i] is not None:
            substitute_approved[i] = bool(rng.random() > 0.05)

    # Status distribution: ACTIVE 90 %, DISCONTINUED 5 %, ON_HOLD 5 %
    status_choices = rng.choice(
        ["ACTIVE", "DISCONTINUED", "ON_HOLD"], size=n, p=[0.90, 0.05, 0.05]
    )

    # Created at: random date in 2025
    start_epoch = pd.Timestamp("2025-01-01").value // 10**9
    end_epoch = pd.Timestamp("2025-12-31").value // 10**9
    random_epochs = rng.randint(start_epoch, end_epoch, size=n)
    created_at = pd.to_datetime(random_epochs, unit="s").normalize()

    return pd.DataFrame(
        {
            "sku_id": ids,
            "name": names,
            "category": categories,
            "subcategory": subcategories,
            "uom": uoms,
            "weight_kg": weights,
            "unit_cost": unit_costs,
            "substitute_sku_id": substitute_ids,
            "substitute_approved": substitute_approved,
            "status": status_choices,
            "created_at": created_at,
        }
    )


def generate_locations(rng: np.random.RandomState) -> pd.DataFrame:
    """Generate the location master table.

    Parameters
    ----------
    rng : np.random.RandomState
        Seeded random state for reproducibility.

    Returns
    -------
    pd.DataFrame
        DataFrame with NUM_LOCATIONS rows and columns:
        location_id, name, type, region, country, capacity_units, status,
        latitude, longitude.
    """
    n = config.NUM_LOCATIONS

    ids = [config.location_id(i + 1) for i in range(n)]
    regions = rng.choice(config.REGIONS, size=n)

    # ~20 % PLANT, remaining split between WAREHOUSE and DISTRIBUTION_CENTER
    num_plants = max(1, int(n * 0.20))
    types = []
    non_plant_options = ["WAREHOUSE", "DISTRIBUTION_CENTER"]
    for i in range(n):
        if i < num_plants:
            types.append("PLANT")
        else:
            types.append(rng.choice(non_plant_options))

    # Shuffle to mix plants into the list
    order = rng.permutation(n)
    types = [types[order[i]] for i in range(n)]
    regions_shuffled = regions  # already random

    names = [f"{regions_shuffled[i]} {types[i].replace('_', ' ').title()} {i + 1}" for i in range(n)]

    countries = rng.choice(["IN", "CN", "DE", "US", "JP"], size=n)
    capacity_units = rng.randint(10000, 500001, size=n)

    # Rough lat/lon by country
    lat_lon_map = {
        "IN": (20.0, 78.0),
        "CN": (35.0, 105.0),
        "DE": (51.0, 10.0),
        "US": (38.0, -97.0),
        "JP": (36.0, 138.0),
    }
    latitudes = np.array(
        [lat_lon_map[c][0] + rng.normal(0, 3) for c in countries]
    ).round(4)
    longitudes = np.array(
        [lat_lon_map[c][1] + rng.normal(0, 5) for c in countries]
    ).round(4)

    return pd.DataFrame(
        {
            "location_id": ids,
            "name": names,
            "type": types,
            "region": regions_shuffled,
            "country": countries,
            "capacity_units": capacity_units,
            "status": "ACTIVE",
            "latitude": latitudes,
            "longitude": longitudes,
        }
    )


def generate_suppliers(rng: np.random.RandomState) -> pd.DataFrame:
    """Generate the supplier master table.

    Parameters
    ----------
    rng : np.random.RandomState
        Seeded random state for reproducibility.

    Returns
    -------
    pd.DataFrame
        DataFrame with NUM_SUPPLIERS rows and columns:
        supplier_id, name, country, reliability_score, payment_terms, status,
        certified, specialization.
    """
    n = config.NUM_SUPPLIERS

    ids = [config.supplier_id(i + 1) for i in range(n)]

    countries = rng.choice(
        ["IN", "CN", "DE", "US", "JP", "KR", "TW", "VN"], size=n
    )

    names = [f"Supplier {countries[i]}-{i + 1}" for i in range(n)]

    # Reliability: beta distribution centred around 0.8  (a=8, b=2 → mean 0.8)
    reliability = np.round(rng.beta(8, 2, size=n), 3)

    payment_terms = rng.choice(config.SUPPLIER_PAYMENT_TERMS, size=n)

    # Status: ACTIVE 85 %, INACTIVE 10 %, SUSPENDED 5 %
    statuses = rng.choice(
        ["ACTIVE", "INACTIVE", "SUSPENDED"], size=n, p=[0.85, 0.10, 0.05]
    )

    certified = rng.random(n) < 0.80

    specializations = rng.choice(config.SKU_CATEGORIES, size=n)

    return pd.DataFrame(
        {
            "supplier_id": ids,
            "name": names,
            "country": countries,
            "reliability_score": reliability,
            "payment_terms": payment_terms,
            "status": statuses,
            "certified": certified,
            "specialization": specializations,
        }
    )
