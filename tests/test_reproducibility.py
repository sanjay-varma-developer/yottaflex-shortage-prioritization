"""
Reproducibility tests for the YottaFlex Supply Chain data generator.

Step 10 of the specification: Regenerate twice with the same seed
and compare row counts / checksums to demonstrate reproducibility.
"""

import hashlib
import json
import os
import sys
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def compute_dataframe_fingerprint(df: pd.DataFrame) -> dict:
    """Compute a fingerprint for a DataFrame: row count, column count, and content hash."""
    content = df.to_csv(index=False).encode("utf-8")
    return {
        "rows": len(df),
        "columns": len(df.columns),
        "column_names": sorted(df.columns.tolist()),
        "md5": hashlib.md5(content).hexdigest(),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def run_reproducibility_test():
    """
    Generate the dataset twice with the same seed and verify they are identical.

    Returns True if all checksums match, False otherwise.
    """
    # Import here to avoid circular imports
    from generator.generate import run_generation

    print("\n" + "=" * 70)
    print("  REPRODUCIBILITY TEST (Step 10)")
    print("  Generating data twice with seed =", config.RANDOM_SEED)
    print("=" * 70)

    # --- Run 1 ---
    print("\n  ▶ Run 1...")
    data_run1 = run_generation(export=False)
    fingerprints_1 = {}
    for name, df in data_run1.items():
        if isinstance(df, pd.DataFrame) and not df.empty:
            fingerprints_1[name] = compute_dataframe_fingerprint(df)

    # --- Run 2 ---
    print("\n  ▶ Run 2...")
    data_run2 = run_generation(export=False)
    fingerprints_2 = {}
    for name, df in data_run2.items():
        if isinstance(df, pd.DataFrame) and not df.empty:
            fingerprints_2[name] = compute_dataframe_fingerprint(df)

    # --- Compare ---
    print("\n  Comparing fingerprints...\n")
    all_match = True
    results = []

    all_keys = sorted(set(list(fingerprints_1.keys()) + list(fingerprints_2.keys())))
    for name in all_keys:
        fp1 = fingerprints_1.get(name)
        fp2 = fingerprints_2.get(name)

        if fp1 is None:
            print(f"  ❌ {name}: present in Run 2 only")
            all_match = False
            results.append({"entity": name, "match": False, "reason": "Missing in Run 1"})
            continue
        if fp2 is None:
            print(f"  ❌ {name}: present in Run 1 only")
            all_match = False
            results.append({"entity": name, "match": False, "reason": "Missing in Run 2"})
            continue

        rows_match = fp1["rows"] == fp2["rows"]
        hash_match = fp1["md5"] == fp2["md5"]

        if rows_match and hash_match:
            print(f"  ✅ {name:25s} — {fp1['rows']:>8,} rows — MD5 match: {fp1['md5']}")
            results.append({
                "entity": name, "match": True,
                "rows": fp1["rows"], "md5": fp1["md5"],
            })
        else:
            print(f"  ❌ {name:25s} — rows: {fp1['rows']} vs {fp2['rows']} — "
                  f"MD5: {fp1['md5']} vs {fp2['md5']}")
            all_match = False
            results.append({
                "entity": name, "match": False,
                "rows_run1": fp1["rows"], "rows_run2": fp2["rows"],
                "md5_run1": fp1["md5"], "md5_run2": fp2["md5"],
            })

    print("\n" + "-" * 70)
    if all_match:
        print("  ✅ REPRODUCIBILITY TEST PASSED — all entities match across two runs.")
    else:
        print("  ❌ REPRODUCIBILITY TEST FAILED — some entities differ.")
    print("=" * 70 + "\n")

    # Export results
    results_path = os.path.join(config.PROJECT_ROOT, "docs", "reproducibility_report.json")
    os.makedirs(os.path.dirname(results_path), exist_ok=True)
    with open(results_path, "w") as f:
        json.dump({
            "seed": config.RANDOM_SEED,
            "all_match": all_match,
            "entities": results,
        }, f, indent=2)
    print(f"  📄 Report saved to {results_path}")

    return all_match


def test_reproducibility():
    """Pytest entrypoint to assert full reproducibility across runs."""
    assert run_reproducibility_test() is True


if __name__ == "__main__":
    success = run_reproducibility_test()
    sys.exit(0 if success else 1)

