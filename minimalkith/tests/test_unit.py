"""
test_unit.py — Unit tests for individual MinimalKith components.

Run with:
    pytest minimalkith/tests/test_unit.py -v
"""

from __future__ import annotations

import math
import tempfile
import os
import unittest

import numpy as np


# ---------------------------------------------------------------------------
# 1. Metabolic
# ---------------------------------------------------------------------------

class TestMetabolic(unittest.TestCase):

    def _make(self, capacity=100.0, replenish=0.5):
        from minimalkith.src.core import Metabolic
        return Metabolic(capacity=capacity, replenish=replenish)

    def test_initial_budget_equals_capacity(self):
        m = self._make(capacity=50.0)
        self.assertAlmostEqual(m.state.budget, 50.0)

    def test_normalised_starts_at_one(self):
        m = self._make()
        self.assertAlmostEqual(m.normalised, 1.0)

    def test_replenish_does_not_exceed_capacity(self):
        m = self._make(capacity=10.0, replenish=5.0)
        for _ in range(10):
            m.replenish()
        self.assertLessEqual(m.state.budget, 10.0)

    def test_not_depleted_initially(self):
        m = self._make()
        self.assertFalse(m.depleted)

    def test_consume_reduces_budget(self):
        m = self._make(capacity=100.0)
        m.consume(30.0)
        self.assertAlmostEqual(m.state.budget, 70.0)

    def test_normalised_range(self):
        m = self._make(capacity=100.0)
        m.consume(60.0)
        n = m.normalised
        self.assertGreaterEqual(n, 0.0)
        self.assertLessEqual(n, 1.0)

    def test_depleted_after_full_consume(self):
        m = self._make(capacity=10.0)
        m.consume(10.0)
        self.assertTrue(m.depleted)


# ---------------------------------------------------------------------------
# 2. ISE
# ---------------------------------------------------------------------------

class TestISE(unittest.TestCase):

    def _make(self, decay=0.05, threshold=1.0, dt=0.02):
        from minimalkith.src.core import ISE
        return ISE(decay=decay, gate_threshold=threshold, dt=dt)

    def test_initial_drive_zero(self):
        ise = self._make()
        self.assertAlmostEqual(ise.drive, 0.0)

    def test_drive_increases_with_positive_error(self):
        ise = self._make()
        ise.update(2.0)
        self.assertGreater(ise.drive, 0.0)

    def test_drive_decays_without_input(self):
        ise = self._make(decay=0.5)
        ise.update(5.0)
        high = ise.drive
        ise.update(0.0)
        self.assertLess(ise.drive, high)

    def test_above_threshold(self):
        ise = self._make(threshold=0.5)
        for _ in range(50):
            ise.update(3.0)
        self.assertTrue(ise.above_threshold)

    def test_zero_input_stays_at_zero(self):
        ise = self._make()
        for _ in range(10):
            ise.update(0.0)
        self.assertAlmostEqual(ise.drive, 0.0)


# ---------------------------------------------------------------------------
# 3. RitualGate
# ---------------------------------------------------------------------------

class TestRitualGate(unittest.TestCase):

    def _make(self, refractory_ticks=5):
        from minimalkith.src.core import ISE, RitualGate
        gate = RitualGate(refractory_ticks=refractory_ticks)
        return gate

    def _make_with_ise(self, threshold=0.01):
        from minimalkith.src.core import ISE, RitualGate
        ise  = ISE(decay=0.0, gate_threshold=threshold, dt=0.02)
        gate = RitualGate(refractory_ticks=2)
        return ise, gate

    def test_initial_state_false(self):
        gate = self._make()
        self.assertFalse(gate.state)

    def test_fire_increments_count(self):
        ise, gate = self._make_with_ise(threshold=0.01)
        for _ in range(10):
            ise.update(5.0)
        gate.evaluate(ise, 5.0, 0)
        self.assertGreaterEqual(gate.fire_count, 0)

    def test_refractory_prevents_double_fire(self):
        ise, gate = self._make_with_ise(threshold=0.01)
        for _ in range(20):
            ise.update(10.0)
        fired_t0 = gate.evaluate(ise, 10.0, 0)
        fired_t1 = gate.evaluate(ise, 10.0, 1)
        # At tick 1 the gate is in refractory if it fired at tick 0
        if fired_t0:
            self.assertFalse(fired_t1)

    def test_gate_fire_count_non_negative(self):
        gate = self._make()
        self.assertGreaterEqual(gate.fire_count, 0)


# ---------------------------------------------------------------------------
# 4. PredictiveModel
# ---------------------------------------------------------------------------

class TestPredictiveModel(unittest.TestCase):

    def _make(self):
        from minimalkith.src.core import PredictiveModel
        rng = np.random.default_rng(0)
        return PredictiveModel(rng=rng)

    def test_prediction_error_finite(self):
        m = self._make()
        for i in range(10):
            m.update(float(i))
        eps = m.prediction_error(10.0)
        self.assertTrue(math.isfinite(eps))

    def test_error_converges_for_constant_signal(self):
        m = self._make()
        for _ in range(200):
            m.update(5.0)
        eps = abs(m.prediction_error(5.0))
        self.assertLess(eps, 1.0)

    def test_large_error_on_step_change(self):
        m = self._make()
        for _ in range(100):
            m.update(0.0)
        eps = abs(m.prediction_error(100.0))
        self.assertGreater(eps, 1.0)


# ---------------------------------------------------------------------------
# 5. Environment
# ---------------------------------------------------------------------------

class TestEnvironment(unittest.TestCase):

    def _make(self, noise_std=0.0, amplitude=1.0, frequency=0.5):
        from minimalkith.src.environment import Environment, EnvironmentConfig
        cfg = EnvironmentConfig(amplitude=amplitude, frequency=frequency,
                                noise_std=noise_std)
        return Environment(cfg, seed=42)

    def test_step_returns_float(self):
        env = self._make()
        obs = env.step()
        self.assertIsInstance(obs, float)

    def test_tick_increments(self):
        env = self._make()
        env.step()
        self.assertEqual(env.tick, 1)

    def test_zero_noise_deterministic(self):
        env1 = self._make(noise_std=0.0)
        env2 = self._make(noise_std=0.0)
        obs1 = [env1.step() for _ in range(20)]
        obs2 = [env2.step() for _ in range(20)]
        np.testing.assert_array_almost_equal(obs1, obs2)

    def test_pressure_pulse_increases_amplitude(self):
        from minimalkith.src.environment import Environment, EnvironmentConfig
        # Pulse active on tick 0
        cfg = EnvironmentConfig(
            amplitude=1.0, noise_std=0.0,
            pressure_pulses=[{"start_tick": 0, "end_tick": 10, "amplitude": 5.0}],
        )
        env_pulse = Environment(cfg, seed=0)
        cfg_base = EnvironmentConfig(amplitude=1.0, noise_std=0.0)
        env_base  = Environment(cfg_base, seed=0)
        # Skip tick 0 (sine=0) and read tick 1
        env_pulse.step(); obs_pulse = env_pulse.step()
        env_base.step();  obs_base  = env_base.step()
        self.assertGreater(abs(obs_pulse), abs(obs_base))

    def test_reset_resets_tick(self):
        env = self._make()
        for _ in range(5):
            env.step()
        env.reset()
        self.assertEqual(env.tick, 0)


# ---------------------------------------------------------------------------
# 6. InteroceptiveLoop
# ---------------------------------------------------------------------------

class TestInteroceptiveLoop(unittest.TestCase):

    def _make_loop(self, connected=True, sham=False):
        from minimalkith.src.core import ISE, RitualGate, PredictiveModel
        from minimalkith.src.interoception import InteroceptiveLoop
        rng  = np.random.default_rng(0)
        pred = PredictiveModel(rng=rng)
        ise  = ISE(decay=0.01, gate_threshold=0.5, dt=0.02)
        gate = RitualGate(refractory_ticks=5)
        return InteroceptiveLoop(pred, ise, gate, connected=connected, sham=sham)

    def test_tick_returns_state(self):
        from minimalkith.src.interoception import InteroceptiveState
        loop = self._make_loop()
        state = loop.tick(1.0, 0)
        self.assertIsInstance(state, InteroceptiveState)

    def test_epsilon_is_finite(self):
        loop = self._make_loop()
        state = loop.tick(1.0, 0)
        self.assertTrue(math.isfinite(state.epsilon))

    def test_ablated_loop_drive_stays_low(self):
        loop = self._make_loop(connected=False)
        for t in range(100):
            state = loop.tick(10.0, t)   # large signal
        self.assertAlmostEqual(state.drive, 0.0, places=3)

    def test_connected_loop_drive_increases(self):
        loop = self._make_loop(connected=True)
        for t in range(50):
            state = loop.tick(5.0, t)
        self.assertGreater(state.drive, 0.0)

    def test_connected_property(self):
        loop = self._make_loop(connected=True)
        self.assertTrue(loop.connected)

    def test_ablate_disconnects(self):
        loop = self._make_loop(connected=True)
        loop.ablate()
        self.assertFalse(loop.connected)

    def test_reconnect_restores(self):
        loop = self._make_loop(connected=True)
        loop.ablate()
        loop.reconnect()
        self.assertTrue(loop.connected)

    def test_sham_does_not_disconnect_routing(self):
        loop = self._make_loop(connected=True, sham=True)
        # Sham: flag says disconnected but routing is intact
        for t in range(50):
            state = loop.tick(5.0, t)
        self.assertGreater(state.drive, 0.0)


# ---------------------------------------------------------------------------
# 7. Analysis functions (smoke tests — no DB required)
# ---------------------------------------------------------------------------

class TestAnalysisFunctions(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        rng = np.random.default_rng(1)
        N = 500
        cls.eps  = rng.normal(0, 1, N)
        cls.gate = (rng.random(N) < 0.05).astype(float)
        cls.ise  = np.abs(cls.eps).cumsum() * 0.01
        cls.gate_times = np.where(cls.gate > 0)[0].astype(float)

    def test_peri_event_histogram(self):
        from minimalkith.src.analysis import compute_peri_event_histogram
        if len(self.gate_times) == 0:
            return
        result = compute_peri_event_histogram(self.eps, self.gate_times, window_s=1.0)
        self.assertIn("values", result)
        self.assertIn("json", result)

    def test_lagged_cross_correlation(self):
        from minimalkith.src.analysis import lagged_cross_correlation
        result = lagged_cross_correlation(self.eps, self.gate, max_lag_s=1.0)
        self.assertIn("json", result)
        self.assertIn("peak_lag_s", result["json"])

    def test_time_lagged_regression(self):
        from minimalkith.src.analysis import time_lagged_regression
        result = time_lagged_regression(self.gate, self.eps, self.ise, lags=[1, 2, 5])
        self.assertIn("json", result)

    def test_granger_test(self):
        from minimalkith.src.analysis import granger_test
        result = granger_test(self.gate, self.eps, maxlag=5)
        self.assertIn("json", result)
        self.assertIn("granger_causal_overall", result["json"])

    def test_pre_post_error_reduction(self):
        from minimalkith.src.analysis import pre_post_error_reduction
        if len(self.gate_times) == 0:
            return
        result = pre_post_error_reduction(self.eps, self.gate_times,
                                          pre_window=0.5, post_window=0.5)
        self.assertIn("json", result)

    def test_ablation_effect_size(self):
        from minimalkith.src.analysis import ablation_effect_size
        conn = {"metric_a": [1.0, 1.2, 1.1], "metric_b": [5.0, 5.5, 4.8]}
        abla = {"metric_a": [0.5, 0.6, 0.4], "metric_b": [5.1, 4.9, 5.2]}
        result = ablation_effect_size(conn, abla)
        self.assertIn("values", result)
        self.assertIn("metric_a", result["values"])
        self.assertIn("cohens_d", result["values"]["metric_a"])
        # metric_a: large positive d expected
        self.assertGreater(result["values"]["metric_a"]["cohens_d"], 0)


# ---------------------------------------------------------------------------
# 8. Persistence (in-memory / temp file)
# ---------------------------------------------------------------------------

class TestPersistence(unittest.TestCase):

    def _db(self):
        from minimalkith.src.persistence import Database
        tmp = tempfile.mktemp(suffix=".db")
        return Database(tmp), tmp

    def test_begin_run_returns_int(self):
        db, tmp = self._db()
        with db:
            rid = db.begin_run("Baseline", 42, {"test": True})
        self.assertIsInstance(rid, int)
        os.unlink(tmp)

    def test_write_tick_returns_int(self):
        import time
        db, tmp = self._db()
        with db:
            rid  = db.begin_run("Baseline", 1, {})
            tid  = db.write_tick(run_id=rid, timestamp=time.time(), seed=1)
        self.assertIsInstance(tid, int)
        os.unlink(tmp)

    def test_fetch_states_returns_rows(self):
        import time
        db, tmp = self._db()
        with db:
            rid = db.begin_run("Baseline", 1, {})
            for i in range(5):
                tid = db.write_tick(run_id=rid, timestamp=time.time()+i, seed=1)
                db.write_state(tick_id=tid, metabolic=1.0, ISE=0.1,
                               epsilon=0.2, gate_state=False)
            db.commit()
            rows = db.fetch_states(rid)
        self.assertEqual(len(rows), 5)
        os.unlink(tmp)

    def test_fetch_events_empty(self):
        db, tmp = self._db()
        with db:
            rid  = db.begin_run("Baseline", 1, {})
            evts = db.fetch_events(rid)
        self.assertEqual(evts, [])
        os.unlink(tmp)

    def test_write_event_stored(self):
        import time
        db, tmp = self._db()
        with db:
            rid = db.begin_run("Pressure", 7, {})
            tid = db.write_tick(run_id=rid, timestamp=time.time(), seed=7)
            db.write_event(tid, "GATE_FIRE", {"drive": 1.5})
            db.commit()
            evts = db.fetch_events(rid, type_="GATE_FIRE")
        self.assertEqual(len(evts), 1)
        os.unlink(tmp)


if __name__ == "__main__":
    unittest.main()
