"""
Export module for the synthetic supply chain dataset.

Saves all tables to CSV in their designated folders:
  - data/master/
  - data/transactions/
  - data/computed/
  - data/ground_truth/

Also generates a manifest.json containing row counts, column counts,
and cryptographic checksums (MD5, SHA-256) for complete provenance.
"""

import hashlib
import json
import os
import sys
from datetime import datetime
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def _compute_file_checksum(filepath: str) -> dict:
    """Compute MD5 and SHA-256 checksums of a file on disk."""
    md5_hash = hashlib.md5()
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            md5_hash.update(chunk)
            sha256_hash.update(chunk)
    return {
        "md5": md5_hash.hexdigest(),
        "sha256": sha256_hash.hexdigest(),
        "size_bytes": os.path.getsize(filepath),
    }


def export_all(all_data: dict, ground_truth_df: pd.DataFrame = None) -> dict:
    """
    Export all generated data tables to CSV and generate manifest.json.

    Parameters
    ----------
    all_data : dict
        Dict of entity name -> pandas DataFrame.
    ground_truth_df : pd.DataFrame, optional
        Separate ground truth labels for anomalies (never mixed with features).

    Returns
    -------
    dict
        Manifest mapping file names to row count, columns, and checksums.
    """
    # Ensure all directories exist
    for d in config.OUTPUT_DIRS:
        os.makedirs(d, exist_ok=True)

    # Master tables mapping
    master_mapping = {
        "skus": os.path.join(config.MASTER_DIR, "skus.csv"),
        "locations": os.path.join(config.MASTER_DIR, "locations.csv"),
        "suppliers": os.path.join(config.MASTER_DIR, "suppliers.csv"),
    }

    # Transaction tables mapping
    trans_mapping = {
        "supplier_capacities": os.path.join(config.TRANSACTION_DIR, "supplier_capacities.csv"),
        "lead_times": os.path.join(config.TRANSACTION_DIR, "lead_times.csv"),
        "forecast_demand": os.path.join(config.TRANSACTION_DIR, "forecast_demand.csv"),
        "inventory": os.path.join(config.TRANSACTION_DIR, "inventory.csv"),
        "purchase_orders": os.path.join(config.TRANSACTION_DIR, "purchase_orders.csv"),
        "production_plans": os.path.join(config.TRANSACTION_DIR, "production_plans.csv"),
    }

    file_mapping = {**master_mapping, **trans_mapping}
    manifest_entries = {}

    # Export master and transaction tables
    for key, path in file_mapping.items():
        df = all_data.get(key)
        if df is not None and isinstance(df, pd.DataFrame):
            print(f"  Writing {os.path.relpath(path, config.PROJECT_ROOT)} ({len(df):,} rows)...")
            df.to_csv(path, index=False)
            chk = _compute_file_checksum(path)
            manifest_entries[os.path.basename(path)] = {
                "category": "master" if key in master_mapping else "transactions",
                "relative_path": os.path.relpath(path, config.PROJECT_ROOT),
                "rows": len(df),
                "columns": len(df.columns),
                "column_names": list(df.columns),
                **chk,
            }

    # Export ground truth separately (strictly segregated)
    if ground_truth_df is not None and isinstance(ground_truth_df, pd.DataFrame):
        gt_path = os.path.join(config.GROUND_TRUTH_DIR, "ground_truth.csv")
        print(f"  Writing {os.path.relpath(gt_path, config.PROJECT_ROOT)} ({len(ground_truth_df):,} rows)...")
        ground_truth_df.to_csv(gt_path, index=False)
        chk = _compute_file_checksum(gt_path)
        manifest_entries["ground_truth.csv"] = {
            "category": "ground_truth",
            "relative_path": os.path.relpath(gt_path, config.PROJECT_ROOT),
            "rows": len(ground_truth_df),
            "columns": len(ground_truth_df.columns),
            "column_names": list(ground_truth_df.columns),
            **chk,
        }

    # Save manifest.json
    manifest = {
        "generated_at": datetime.now().isoformat(),
        "random_seed": config.RANDOM_SEED,
        "scale_factor": config.SCALE_FACTOR,
        "total_files": len(manifest_entries),
        "files": manifest_entries,
    }

    manifest_path = os.path.join(config.DATA_DIR, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"  📄 Manifest saved to {os.path.relpath(manifest_path, config.PROJECT_ROOT)}")

    return manifest
