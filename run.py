#!/usr/bin/env python3
"""
YottaFlex Supply Chain Shortage Prioritization System
=====================================================

Main entry point that orchestrates the full pipeline:
  1. Generate synthetic master + transaction data
  2. Inject labeled edge cases
  3. Calculate projected available balance (PAB)
  4. Detect and prioritize shortages
  5. Generate candidate mitigations
  6. Validate all data
  7. Export results

Author: Sanjay Varma
"""

import argparse
import os
import sys
import time
from datetime import datetime

import config
from generator.generate import run_generation
from generator.sql_exporter import export_sqlite_and_sql
from engine.run_engine import run_engine
from engine.actor_views import print_actor_summary
from validators.validator import run_validation, print_validation_report, export_validation_summary


def main():
    parser = argparse.ArgumentParser(
        description="YottaFlex Supply Chain Shortage Prioritization System"
    )
    parser.add_argument(
        "--scale", type=float, default=1.0,
        help="Scale factor for data volume (1.0 = full, 0.05 = starter). Default: 1.0"
    )
    parser.add_argument(
        "--seed", type=int, default=config.RANDOM_SEED,
        help=f"Random seed for reproducibility. Default: {config.RANDOM_SEED}"
    )
    parser.add_argument(
        "--skip-engine", action="store_true",
        help="Skip the engine phase (only generate data)."
    )
    parser.add_argument(
        "--skip-validation", action="store_true",
        help="Skip validation checks."
    )
    parser.add_argument(
        "--reproducibility-test", action="store_true",
        help="Run the reproducibility test (Step 10): generate twice and compare checksums."
    )
    parser.add_argument(
        "--actor", type=str, default=None,
        choices=["planner", "operations", "logistics", "supplier", "warehouse", "all"],
        help="Print executive dashboard view for a specific Primary Actor role."
    )
    args = parser.parse_args()

    # Apply scale factor
    if args.scale != 1.0:
        config.SCALE_FACTOR = args.scale
        config.NUM_SKUS = int(3_000 * args.scale)
        config.NUM_LOCATIONS = int(50 * max(args.scale, 0.2))
        config.NUM_SUPPLIERS = int(500 * args.scale)
        config.NUM_PURCHASE_ORDERS = int(10_000 * args.scale)

    # Apply seed
    if args.seed != config.RANDOM_SEED:
        config.RANDOM_SEED = args.seed

    # Reproducibility test mode
    if args.reproducibility_test:
        from tests.test_reproducibility import run_reproducibility_test
        success = run_reproducibility_test()
        sys.exit(0 if success else 1)

    print("=" * 70)
    print("  YottaFlex Supply Chain Shortage Prioritization System")
    print("=" * 70)
    print(f"  Seed:        {config.RANDOM_SEED}")
    print(f"  Scale:       {config.SCALE_FACTOR}")
    print(f"  SKUs:        {config.NUM_SKUS}")
    print(f"  Locations:   {config.NUM_LOCATIONS}")
    print(f"  Suppliers:   {config.NUM_SUPPLIERS}")
    print(f"  POs:         {config.NUM_PURCHASE_ORDERS}")
    print(f"  Weeks:       {config.NUM_WEEKS}")
    print(f"  Started at:  {datetime.now().isoformat()}")
    print("=" * 70)

    total_start = time.time()

    # ── Phase 1: Data Generation ──────────────────────────────────────
    print("\n" + "─" * 70)
    print("  PHASE 1: Data Generation")
    print("─" * 70)
    t0 = time.time()
    data = run_generation(export=True)
    gen_time = time.time() - t0
    print(f"\n  ⏱  Data generation completed in {gen_time:.1f}s")

    # ── Phase 2: Engine (Balance, Shortages, Mitigations) ─────────────
    if not args.skip_engine:
        print("\n" + "─" * 70)
        print("  PHASE 2: Engine — Balance → Shortages → Mitigations")
        print("─" * 70)
        t0 = time.time()
        engine_results = run_engine(data)
        data.update(engine_results)
        eng_time = time.time() - t0
        print(f"\n  ⏱  Engine completed in {eng_time:.1f}s")
    else:
        print("\n  ⏭  Skipping engine phase (--skip-engine)")

    # ── Phase 3: SQL & Database Export (Step 9) ──────────────────────
    print("\n" + "─" * 70)
    print("  PHASE 3: SQLite & SQL Seed Export (Step 9)")
    print("─" * 70)
    t0 = time.time()
    export_sqlite_and_sql(data)
    sql_time = time.time() - t0
    print(f"  ⏱  Database export completed in {sql_time:.1f}s")

    # ── Phase 4: Validation ───────────────────────────────────────────
    if not args.skip_validation:
        print("\n" + "─" * 70)
        print("  PHASE 4: Validation (Step 8)")
        print("─" * 70)
        t0 = time.time()
        results = run_validation(data)
        print_validation_report(results)
        export_validation_summary(results)
        val_time = time.time() - t0
        print(f"  ⏱  Validation completed in {val_time:.1f}s")
    else:
        print("\n  ⏭  Skipping validation (--skip-validation)")

    # ── Phase 5: Actor Summary (Optional CLI Dashboard) ──────────────
    if args.actor:
        print_actor_summary(args.actor, data)

    # ── Summary ───────────────────────────────────────────────────────
    total_time = time.time() - total_start
    print("\n" + "=" * 70)
    print("  PIPELINE COMPLETE")
    print("=" * 70)
    print(f"  Total time: {total_time:.1f}s")
    print(f"\n  Output directory: {config.DATA_DIR}")
    print("  Files generated:")
    for root, dirs, files in os.walk(config.DATA_DIR):
        for fname in sorted(files):
            fpath = os.path.join(root, fname)
            size = os.path.getsize(fpath)
            rel = os.path.relpath(fpath, config.PROJECT_ROOT)
            if size > 1_000_000:
                print(f"    📄 {rel} ({size/1_000_000:.1f} MB)")
            else:
                print(f"    📄 {rel} ({size/1_000:.1f} KB)")
    print("=" * 70)


if __name__ == "__main__":
    main()
