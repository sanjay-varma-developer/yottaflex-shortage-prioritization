# Technical Interview & Architecture Defense Guide

**Candidate**: Sanjay Varma  
**Role Target**: Associate AI Forward Deployed Engineer  
**Organization**: YottaFlex AI Technologies  
**Project**: Supply Chain Shortage Prioritization System  

---

## 1. The 2-Minute Executive Pitch

> *"In enterprise supply chains, planners don't suffer from a lack of data; they suffer from alert fatigue. A single delayed component can trigger thousands of disconnected alerts across downstream assembly plants.*
> 
> *I designed and built an end-to-end supply chain shortage prioritization platform that models 3,000 SKUs, 50 facilities, 500 vendors, and 10,000 purchase orders over a 52-week horizon (~613,000 demand rows).*
> 
> *Rather than row-by-row simulation, I engineered a vectorized discrete-time MRP balance engine in pandas/numpy that computes projected available balances across the entire horizon in 0.8 seconds. It clusters contiguous negative balance periods into actionable multi-period shortage events, ranks them by enterprise financial exposure ($\text{Deficit} \times \text{Duration} \times \text{Unit Cost}$), diagnoses root causes across 5 hypotheses, and formulates scored mitigation recommendations across 5 recovery archetypes.*
> 
> *The entire system runs with 100% deterministic reproducibility from seed `20261022`, passes 41 relational validation checks and 16 automated pytest suites, and publishes tailored decision dashboards for all 5 enterprise personas: Planners, Operations Managers, Logistics Analysts, Suppliers, and Warehouse Operators."*

---

## 2. Key Architectural Decisions & Engineering Trade-offs

### Decision 1: Discrete-Time MRP Mechanics vs. Discrete-Event Simulation
* **Choice**: Modeled weekly discrete-time buckets ($t \in [1, 52]$) rather than continuous millisecond event queues.
* **Why**: Tactical S&OP (Sales & Operations Planning) operates on weekly replenishment and manufacturing cycles. Discrete-time buckets enable complete vectorization via grouped cumulative sums (`cumsum`), computing 613,392 rows in **0.8 seconds** compared to minutes in an event-driven loop.

### Decision 2: Contiguous Shortage Clustering vs. Isolated Period Alerts
* **Choice**: Clustered back-to-back negative weeks for the same $(s, l)$ pair into a single multi-week Shortage Event with duration and peak deficit.
* **Why**: An inventory deficit spanning weeks 12 through 18 is a single structural breakdown (e.g. supplier outage), not 7 separate unrelated crises. Grouping provides planners with an operational start week, end week, and total stockout window.

### Decision 3: Financial Exposure Priority Scoring
* **Choice**: $\text{Priority Score} = \text{Peak Deficit} \times \text{Duration Weeks} \times \text{Unit Cost}$.
* **Why**: Unit shortage count alone is misleading. A stockout of 100 high-value electronic microcontrollers (\$450 each) over 10 weeks poses far higher enterprise risk (\$450,000 exposure) than a 500-unit shortage of low-cost cardboard packaging (\$0.10 each) over 1 week (\$50 exposure).

### Decision 4: Strict Separation of Ground Truth (Zero Feature Leakage)
* **Choice**: Injected negative scenarios are written exclusively to `data/ground_truth/ground_truth.csv` and `.json`.
* **Why**: In predictive modeling and algorithmic decision systems, leaking anomaly indicators (`issue_type`) into feature matrices causes artificial target leakage and prevents true real-world validation.

---

## 3. Anticipated Tough Technical Questions & Answers

### Q1: "How did you ensure deterministic reproducibility across independent runs?"
> **Answer**:  
> *"I isolated all stochastic operations to a single `np.random.RandomState(config.RANDOM_SEED)` instance with fixed seed `20261022`. I avoided relying on the global `np.random` state, and ensured that all IDs are computed functionally from zero-padded sequential counters rather than random UUIDs. Step 10 is tested automatically in `tests/test_reproducibility.py`, asserting identical MD5 and SHA-256 hashes across all 11 tables."*

### Q2: "Why did you choose pandas/numpy instead of an LP solver like PuLP or Gurobi?"
> **Answer**:  
> *"Linear Programming is ideal for bounded cost-minimization once all decisions are framed. However, the core challenge here is multi-period balance accounting, exception detection, root-cause attribution, and multi-actor delivery across 613k rows. Vectorized numpy/pandas handles 613k rows in 0.8 seconds without solver licensing constraints or memory overhead. In our V2 roadmap, the candidate mitigations generated here can be fed directly into an LP solver as decision variables."*

### Q3: "How does the system prevent unapproved substitute parts from being shipped?"
> **Answer**:  
> *"In `engine/mitigation_engine.py`, when formulating `SUBSTITUTE_SKU` options, the engine checks `substitute_approved`. If False, it sets feasibility score to `0.0` and flags `policy_block = True`. The recommendation optimizer (`recommended = True`) filters out zero-feasibility options, preventing unauthorized substitutions while still logging the candidate for QA engineering review."*

---

## 4. Production Scaling Roadmap (V2 & Beyond)

If deployed in an enterprise environment scaling from 3,000 SKUs to 1,000,000 SKUs:
1. **Distributed Compute**: Migrate the balance engine from single-node pandas to **Apache Spark / PySpark** or **Polars / DuckDB** for out-of-core memory execution.
2. **Event Streaming**: Ingest PO confirmations and carrier tracking via **Apache Kafka** or **AWS Kinesis**, appending directly to `state_transition_events`.
3. **Prescriptive LP Solver**: Couple the mitigation candidate generator with an integer programming solver (OR-Tools / Gurobi) to solve the global network flow problem subject to budget ceilings.
