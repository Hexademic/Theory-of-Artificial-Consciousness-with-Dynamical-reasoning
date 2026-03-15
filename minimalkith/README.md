# MinimalKith

**MinimalKith** is the minimal interoceptive organism reference implementation for the
[Constitutional Phenomenology Framework (CPF)](../CPF_SPEC_v1.0.md).

It provides a clean, self-contained Python package for running controlled batch experiments
that establish the causal relationship between prediction error (ε), interoceptive drive (ISE),
and gated action in a simple scalar environment.

---

## Purpose

MinimalKith answers two empirical questions:

1. **Does ε causally predict gate events?** (Granger causality, cross-correlation)
2. **Does gate-triggered action reduce subsequent ε?** (pre/post error reduction)

By comparing a fully-connected interoceptive loop against an ablated (disconnected) control,
it validates that the loop architecture — not noise or confounds — drives gating behaviour.

---

## Package structure

```
minimalkith/
├── configs/
│   └── config.yaml          # Default run parameters
├── ci/
│   └── pipeline.yaml        # GitHub Actions CI
├── data/
│   └── runs/                # SQLite databases (created at runtime)
├── reports/                 # HTML reports (created at runtime)
├── src/
│   ├── __init__.py
│   ├── core.py              # Metabolic, ISE, RitualGate, PredictiveModel,
│   │                        #   Actuator, Proprioceptor
│   ├── environment.py       # Deterministic scalar signal generator
│   ├── interoception.py     # InteroceptiveLoop with ablation toggle
│   ├── persistence.py       # SQLite storage layer (WAL mode)
│   ├── harness.py           # Batch runner (60 runs × 3 conditions)
│   ├── analysis.py          # Six analysis functions
│   └── reporting.py        # One-page HTML report generator
└── tests/
    ├── test_unit.py         # Component-level unit tests
    └── test_integration.py  # End-to-end integration tests
```

---

## Installation

```bash
pip install numpy scipy matplotlib pyyaml
# Optional: PyTorch for cpf_instrumentation integration
pip install torch
```

No separate package install is required — run from the repository root.

---

## Quick start

### Smoke run (3 conditions × 2 minutes)

```bash
python -m minimalkith.src.harness \
    --config minimalkith/configs/config.yaml \
    --batch-id smoke_001 \
    --smoke
```

### Full batch (60 runs, ~2 hours)

```bash
python -m minimalkith.src.harness \
    --config minimalkith/configs/config.yaml \
    --batch-id batch_001
```

### Generate HTML report

```python
from minimalkith.src.reporting import BatchReport

report = BatchReport.from_database(
    "data/runs/batch_001.db",
    batch_id="batch_001",
)
report.write_html("reports/batch_001.html")
```

---

## Experimental conditions

| Condition | N | Description |
|-----------|---|-------------|
| Baseline  | 20 | Normal environment, full interoception |
| Pressure  | 20 | Pressure pulse (t=120–180 s), full interoception |
| Ablation  | 20 | Normal environment, interoception disconnected |

All 60 runs are executed in randomised order (controlled by `batch_seed`) to eliminate
systematic ordering bias.

---

## Architecture

```
observation(t)
     │
     ▼
PredictiveModel ──► ε (prediction error)
                         │
               [connected?]──No──► ISE.update(0)
                    │Yes
                    ▼
              ISE.update(ε)
                    │
                    ▼
              ISE.drive > θ?
                    │Yes
                    ▼
              RitualGate.evaluate() ──► gate_fired
                    │
                    ▼
              Actuator.command()
```

The `connected` flag is toggled to `False` in the Ablation condition, causing ISE to
receive zero input regardless of ε. This is the minimal structural ablation.

---

## Analysis functions

All six functions in `analysis.py` operate on numpy arrays extracted from the SQLite DB:

| Function | Method | Hypothesis tested |
|----------|--------|-------------------|
| `compute_peri_event_histogram` | Mean ε ± SEM around gate events | ε peaks before gate fires |
| `lagged_cross_correlation` | Normalised cross-correlation | Positive peak lag → ε precedes gate |
| `time_lagged_regression` | OLS with F-test | ε + ISE predict gate better than chance |
| `granger_test` | AR F-test (restricted vs unrestricted) | ε Granger-causes gate |
| `pre_post_error_reduction` | Paired t-test | Gate action reduces |ε| |
| `ablation_effect_size` | Cohen's d + Mann-Whitney U | Connected > Ablated gate activity |

Significance threshold: α = 0.01 throughout.

---

## Database schema

```sql
run_meta  (run_id, condition, seed, params JSON, start_ts, end_ts)
ticks     (tick_id, run_id, timestamp, seed)
state     (tick_id, metabolic, ISE, epsilon, gate_state, actuator_vector BLOB,
           proprioception BLOB)
events    (event_id, tick_id, type, details JSON)
```

WAL journal mode ensures atomic writes; a crash mid-batch leaves the DB consistent.

---

## Running tests

```bash
# Unit tests only
pytest minimalkith/tests/test_unit.py -v

# Integration tests (runs a 30 s smoke batch)
pytest minimalkith/tests/test_integration.py -v

# All tests with coverage
pytest minimalkith/tests/ -v --cov=minimalkith/src --cov-report=term-missing
```

---

## Configuration

Edit `minimalkith/configs/config.yaml` to adjust:

- `run_duration_s` — seconds per run (default 600)
- `n_per_condition` — runs per condition (default 20)
- `batch_seed` — master RNG seed for reproducibility
- `ise_threshold` — ISE drive level required to enable the gate
- `refractory_ticks` — minimum ticks between gate events

---

## CPF integration

MinimalKith is designed to be the empirical validation layer for the CPF.
The causal results (Granger p-values, ablation Cohen's d, error reduction %) feed
directly into the `AblationReport` section of the CPF Stability Ledger, providing
evidence that the interoceptive loop satisfies the **Somatic Honesty** axiom (Axiom I).

See `cpf_instrumentation/` for the PyTorch forward-hook telemetry layer that connects
MinimalKith validation results to live LLM runs.
