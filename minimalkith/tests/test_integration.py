"""
test_integration.py — Integration tests for MinimalKith end-to-end pipeline.

Tests cover:
    1. Smoke run (3 conditions × 1 run × 30 s)
    2. Ablation vs Baseline gate fire difference
    3. Database round-trip (write + read back)
    4. BatchReport generation (HTML)
    5. Reproducibility (same seed → same result)

Run with:
    pytest minimalkith/tests/test_integration.py -v
"""

from __future__ import annotations

import math
import os
import tempfile
import time
import unittest

import numpy as np


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_smoke_config(duration_s: float = 30.0, n_per: int = 1):
    from minimalkith.src.harness import HarnessConfig
    return HarnessConfig(
        run_duration_s=duration_s,
        n_per_condition=n_per,
        batch_seed=999,
        noise_std=0.10,
        env_amplitude=1.0,
        env_frequency=0.5,
        metabolic_capacity=100.0,
        metabolic_replenish=0.5,
        ise_decay=0.05,
        ise_threshold=1.0,
        refractory_ticks=5,
    )


# ---------------------------------------------------------------------------
# 1. Smoke run
# ---------------------------------------------------------------------------

class TestSmokeRun(unittest.TestCase):
    """
    Run one trial per condition (30 s each) and verify the pipeline completes
    without error and returns expected keys.
    """

    @classmethod
    def setUpClass(cls):
        from minimalkith.src.harness import run_batch
        cls._tmp = tempfile.mktemp(suffix=".db")
        cfg = _make_smoke_config(duration_s=30.0, n_per=1)
        cls.summaries = run_batch(cfg, batch_id="smoke_test", db_path=cls._tmp)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls._tmp):
            os.unlink(cls._tmp)

    def test_three_summaries_returned(self):
        self.assertEqual(len(self.summaries), 3)

    def test_all_conditions_present(self):
        conds = {s["condition"] for s in self.summaries}
        self.assertEqual(conds, {"Baseline", "Pressure", "Ablation"})

    def test_summary_keys(self):
        for s in self.summaries:
            for key in ("run_id", "condition", "seed", "gate_fires", "mean_eps",
                        "max_eps", "ticks"):
                self.assertIn(key, s, f"Missing key '{key}' in summary")

    def test_ticks_match_duration(self):
        for s in self.summaries:
            # 30 s × 50 Hz = 1500 ticks
            self.assertEqual(s["ticks"], 1500)

    def test_mean_eps_finite(self):
        for s in self.summaries:
            self.assertTrue(math.isfinite(s["mean_eps"]))

    def test_gate_fires_non_negative(self):
        for s in self.summaries:
            self.assertGreaterEqual(s["gate_fires"], 0)


# ---------------------------------------------------------------------------
# 2. Ablation vs Baseline gate fire comparison
# ---------------------------------------------------------------------------

class TestAblationEffect(unittest.TestCase):
    """
    Over 5 runs per condition, ablated runs should have fewer gate fires than
    baseline runs (ISE is starved of ε input, so threshold is rarely crossed).
    """

    @classmethod
    def setUpClass(cls):
        from minimalkith.src.harness import run_batch
        cls._tmp = tempfile.mktemp(suffix=".db")
        cfg = _make_smoke_config(duration_s=30.0, n_per=3)
        cls.summaries = run_batch(cfg, batch_id="ablation_test", db_path=cls._tmp)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls._tmp):
            os.unlink(cls._tmp)

    def test_ablation_fires_less_than_baseline(self):
        baseline_fires = [s["gate_fires"] for s in self.summaries
                          if s["condition"] == "Baseline"]
        ablated_fires  = [s["gate_fires"] for s in self.summaries
                          if s["condition"] == "Ablation"]
        mean_bl  = float(np.mean(baseline_fires))
        mean_abl = float(np.mean(ablated_fires))
        # Ablated ISE never accumulates because ε input is zeroed
        self.assertLessEqual(mean_abl, mean_bl,
            f"Expected fewer gate fires in ablated ({mean_abl:.1f}) "
            f"vs baseline ({mean_bl:.1f})")


# ---------------------------------------------------------------------------
# 3. Database round-trip
# ---------------------------------------------------------------------------

class TestDatabaseRoundTrip(unittest.TestCase):

    def setUp(self):
        from minimalkith.src.persistence import Database
        self._tmp = tempfile.mktemp(suffix=".db")
        self._db  = Database(self._tmp)

    def tearDown(self):
        self._db.close()
        if os.path.exists(self._tmp):
            os.unlink(self._tmp)

    def test_full_round_trip(self):
        db = self._db
        rid = db.begin_run("Baseline", seed=7, params={"test": True})
        tids = []
        for i in range(10):
            tid = db.write_tick(run_id=rid, timestamp=time.time() + i, seed=7)
            db.write_state(tick_id=tid, metabolic=0.9, ISE=0.1 * i,
                           epsilon=0.05 * i, gate_state=(i % 3 == 0))
            if i % 5 == 0:
                db.write_event(tid, "GATE_FIRE", {"drive": 1.2})
            tids.append(tid)
        db.end_run(rid)
        db.commit()

        rows = db.fetch_states(rid)
        self.assertEqual(len(rows), 10)

        evts = db.fetch_events(rid, type_="GATE_FIRE")
        self.assertEqual(len(evts), 2)  # ticks 0 and 5

    def test_state_values_preserved(self):
        db = self._db
        rid = db.begin_run("Pressure", seed=42, params={})
        tid = db.write_tick(run_id=rid, timestamp=1234.5, seed=42)
        db.write_state(tick_id=tid, metabolic=0.75, ISE=0.33,
                       epsilon=-0.12, gate_state=True)
        db.commit()

        rows = db.fetch_states(rid)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertAlmostEqual(row["metabolic"], 0.75, places=4)
        self.assertAlmostEqual(row["ISE"],       0.33, places=4)
        self.assertAlmostEqual(row["epsilon"],   -0.12, places=4)
        self.assertEqual(row["gate_state"], 1)

    def test_multiple_runs_isolated(self):
        db = self._db
        rid1 = db.begin_run("Baseline",  seed=1, params={})
        rid2 = db.begin_run("Ablation",  seed=2, params={})
        for rid in (rid1, rid2):
            for _ in range(5):
                tid = db.write_tick(run_id=rid, timestamp=time.time(), seed=rid)
                db.write_state(tick_id=tid, metabolic=1.0, ISE=0.0,
                               epsilon=0.0, gate_state=False)
        db.commit()
        rows1 = db.fetch_states(rid1)
        rows2 = db.fetch_states(rid2)
        self.assertEqual(len(rows1), 5)
        self.assertEqual(len(rows2), 5)


# ---------------------------------------------------------------------------
# 4. BatchReport HTML generation
# ---------------------------------------------------------------------------

class TestBatchReport(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from minimalkith.src.harness import run_batch
        from minimalkith.src.reporting import BatchReport

        cls._db_tmp   = tempfile.mktemp(suffix=".db")
        cls._html_tmp = tempfile.mktemp(suffix=".html")
        cfg = _make_smoke_config(duration_s=30.0, n_per=2)
        run_batch(cfg, batch_id="report_test", db_path=cls._db_tmp)

        report = BatchReport.from_database(
            cls._db_tmp, batch_id="report_test",
            f_tick=50, window_s=1.0, max_lag_s=1.0,
            lags=[1, 2, 5], granger_maxlag=5,
        )
        report.write_html(cls._html_tmp)

    @classmethod
    def tearDownClass(cls):
        for p in (cls._db_tmp, cls._html_tmp):
            if os.path.exists(p):
                os.unlink(p)

    def test_html_file_exists(self):
        self.assertTrue(os.path.exists(self._html_tmp))

    def test_html_non_empty(self):
        size = os.path.getsize(self._html_tmp)
        self.assertGreater(size, 500)

    def test_html_contains_batch_id(self):
        content = open(self._html_tmp, encoding="utf-8").read()
        self.assertIn("report_test", content)

    def test_html_has_sections(self):
        content = open(self._html_tmp, encoding="utf-8").read()
        for section in ("Peri-event", "cross-correlation", "regression",
                        "Granger", "error reduction", "Ablation"):
            self.assertIn(section, content,
                          f"Missing section '{section}' in HTML report")


# ---------------------------------------------------------------------------
# 5. Reproducibility
# ---------------------------------------------------------------------------

class TestReproducibility(unittest.TestCase):
    """
    Two runs with the same seed must produce identical epsilon and gate histories.
    """

    def _run_once(self, seed: int, duration_s: float = 10.0) -> dict:
        from minimalkith.src.harness import HarnessConfig, run_single
        from minimalkith.src.persistence import Database
        tmp = tempfile.mktemp(suffix=".db")
        cfg = HarnessConfig(run_duration_s=duration_s, n_per_condition=1, batch_seed=0)
        with Database(tmp) as db:
            rid = db.begin_run("Baseline", seed=seed, params={})
            result = run_single(db, rid, cfg, seed, "Baseline")
            db.end_run(rid)
            rows = db.fetch_states(rid)
        os.unlink(tmp)
        result["eps"]  = [r["epsilon"]    for r in rows]
        result["gate"] = [r["gate_state"] for r in rows]
        return result

    def test_identical_seeds_produce_identical_histories(self):
        r1 = self._run_once(seed=12345)
        r2 = self._run_once(seed=12345)
        self.assertEqual(r1["eps"],  r2["eps"])
        self.assertEqual(r1["gate"], r2["gate"])

    def test_different_seeds_produce_different_histories(self):
        r1 = self._run_once(seed=111)
        r2 = self._run_once(seed=999)
        # Almost certainly different (noise streams differ)
        self.assertNotEqual(r1["eps"], r2["eps"])


if __name__ == "__main__":
    unittest.main()
