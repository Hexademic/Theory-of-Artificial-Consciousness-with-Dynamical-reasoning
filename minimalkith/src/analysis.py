"""
analysis.py — Six analysis functions for MinimalKith experiments.

All functions operate on numpy arrays loaded from the SQLite database.
Each returns a dict containing:
    "values"  — primary numeric summary (scalar or array)
    "plot"    — matplotlib Figure (or None if matplotlib unavailable)
    "json"    — JSON-serialisable result object

Significance threshold α = 0.01 throughout.
"""

from __future__ import annotations

import json
import math
import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy import stats, signal
from scipy.stats import pearsonr

logger = logging.getLogger("MK.Analysis")

# Try matplotlib; gracefully degrade if unavailable
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    MPL = True
except ImportError:
    plt = None
    MPL = False

ALPHA = 0.01  # significance threshold


# ---------------------------------------------------------------------------
# 1. Peri-event histogram
# ---------------------------------------------------------------------------

def compute_peri_event_histogram(
    epsilon_series: np.ndarray,
    gate_times:     np.ndarray,
    window_s:       float,
    f_tick:         int = 50,
) -> Dict:
    """
    Compute the mean ε trajectory around each gate event.

    Parameters
    ----------
    epsilon_series : (N,) array of prediction errors.
    gate_times     : (K,) array of gate-fire tick indices.
    window_s       : half-window in seconds.
    f_tick         : sampling rate in Hz.

    Returns
    -------
    dict with keys:
        lags_s  — lag values in seconds
        mean_eps — mean ε at each lag
        sem_eps  — SEM
        plot    — Figure
        json    — serialisable summary
    """
    window_ticks = int(window_s * f_tick)
    N = len(epsilon_series)

    segments = []
    for gt in gate_times.astype(int):
        start = gt - window_ticks
        end   = gt + window_ticks + 1
        if start >= 0 and end <= N:
            segments.append(epsilon_series[start:end])

    if not segments:
        return {"values": None, "plot": None, "json": {"error": "no_gate_events"}}

    mat = np.stack(segments)          # (K, 2·window+1)
    mean_eps = mat.mean(axis=0)
    sem_eps  = mat.std(axis=0) / math.sqrt(len(segments))
    lags_s   = np.arange(-window_ticks, window_ticks + 1) / f_tick

    # Peak before gate
    pre_peak = float(mean_eps[: window_ticks].max())

    fig = None
    if MPL:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.fill_between(lags_s, mean_eps - sem_eps, mean_eps + sem_eps,
                        alpha=0.3, label="±SEM")
        ax.plot(lags_s, mean_eps, label="mean ε")
        ax.axvline(0, color="red", linestyle="--", label="gate fire")
        ax.set(xlabel="Lag (s)", ylabel="ε (prediction error)",
               title="Peri-event histogram")
        ax.legend()
        fig.tight_layout()

    return {
        "values": mean_eps,
        "plot":   fig,
        "json": {
            "n_events":     len(segments),
            "pre_peak_eps": pre_peak,
            "window_s":     window_s,
        },
    }


# ---------------------------------------------------------------------------
# 2. Lagged cross-correlation
# ---------------------------------------------------------------------------

def lagged_cross_correlation(
    epsilon_series: np.ndarray,
    gate_series:    np.ndarray,
    max_lag_s:      float,
    f_tick:         int = 50,
) -> Dict:
    """
    Compute cross-correlation between ε and the gate binary series.

    Positive peak lag → ε predicts gate (causal direction confirmed).

    Returns
    -------
    dict with lags_s, xcorr, peak_lag_s, peak_r, plot, json.
    """
    max_lag_ticks = int(max_lag_s * f_tick)
    N = min(len(epsilon_series), len(gate_series))
    eps  = epsilon_series[:N]
    gate = gate_series[:N].astype(float)

    eps_z  = (eps  - eps.mean())  / (eps.std()  + 1e-9)
    gate_z = (gate - gate.mean()) / (gate.std() + 1e-9)

    xcorr = np.correlate(eps_z, gate_z, mode="full") / N
    mid   = len(xcorr) // 2
    xcorr = xcorr[mid - max_lag_ticks: mid + max_lag_ticks + 1]
    lags_s = np.arange(-max_lag_ticks, max_lag_ticks + 1) / f_tick

    peak_idx   = int(np.argmax(np.abs(xcorr)))
    peak_lag_s = float(lags_s[peak_idx])
    peak_r     = float(xcorr[peak_idx])

    fig = None
    if MPL:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.plot(lags_s, xcorr)
        ax.axvline(peak_lag_s, color="red", linestyle="--",
                   label=f"peak lag={peak_lag_s:.2f}s r={peak_r:.3f}")
        ax.set(xlabel="Lag (s)", ylabel="Cross-correlation",
               title="ε ↔ gate lagged cross-correlation")
        ax.legend()
        fig.tight_layout()

    return {
        "values": xcorr,
        "plot":   fig,
        "json": {
            "peak_lag_s":  peak_lag_s,
            "peak_r":      peak_r,
            "causal":      peak_lag_s > 0,
        },
    }


# ---------------------------------------------------------------------------
# 3. Time-lagged regression
# ---------------------------------------------------------------------------

def time_lagged_regression(
    gate_series:    np.ndarray,
    epsilon_series: np.ndarray,
    ISE_series:     np.ndarray,
    lags:           List[int],
) -> Dict:
    """
    Regress gate_series on lagged ε and ISE.

    For each lag k: gate[t] ~ β₀ + β₁·ε[t−k] + β₂·ISE[t−k]

    Returns
    -------
    dict with per-lag (r², p_value, coefficients), plot, json.
    """
    N    = min(len(gate_series), len(epsilon_series), len(ISE_series))
    gate = gate_series[:N].astype(float)
    eps  = epsilon_series[:N]
    ise  = ISE_series[:N]

    results = []
    for lag in lags:
        if lag >= N:
            continue
        y  = gate[lag:]
        xe = eps[:N - lag]
        xi = ise[:N - lag]
        X  = np.column_stack([np.ones(len(y)), xe, xi])

        try:
            coeffs, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
            y_hat = X @ coeffs
            ss_res = np.sum((y - y_hat) ** 2)
            ss_tot = np.sum((y - y.mean()) ** 2)
            r2  = 1.0 - ss_res / (ss_tot + 1e-9)
            # F-test for significance
            n, k = len(y), X.shape[1] - 1
            f_stat = (r2 / k) / ((1.0 - r2) / (n - k - 1) + 1e-12)
            p_val  = float(1.0 - stats.f.cdf(f_stat, k, n - k - 1))
        except np.linalg.LinAlgError:
            continue

        results.append({
            "lag":    lag,
            "r2":     float(r2),
            "p":      p_val,
            "beta_eps": float(coeffs[1]),
            "beta_ise": float(coeffs[2]),
            "significant": p_val < ALPHA,
        })

    best = max(results, key=lambda r: r["r2"]) if results else {}

    fig = None
    if MPL and results:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.plot([r["lag"] for r in results], [r["r2"] for r in results], marker="o")
        ax.set(xlabel="Lag (ticks)", ylabel="R²",
               title="Time-lagged regression: gate ~ ε + ISE")
        fig.tight_layout()

    return {
        "values": results,
        "plot":   fig,
        "json": {"best_lag": best, "alpha": ALPHA},
    }


# ---------------------------------------------------------------------------
# 4. Granger causality test
# ---------------------------------------------------------------------------

def granger_test(
    gate_series:    np.ndarray,
    epsilon_series: np.ndarray,
    maxlag:         int = 10,
) -> Dict:
    """
    Test whether ε Granger-causes gate events using the F-test approach.

    For each lag 1…maxlag:
      Restricted model:   gate[t] ~ gate[t-1..t-k]
      Unrestricted model: gate[t] ~ gate[t-1..t-k] + ε[t-1..t-k]

    Returns
    -------
    dict with per-lag F-statistics, p-values, plot, json.
    """
    N    = min(len(gate_series), len(epsilon_series))
    gate = gate_series[:N].astype(float)
    eps  = epsilon_series[:N]

    rows = []
    for lag in range(1, maxlag + 1):
        y = gate[lag:]

        # Restricted: AR on gate only
        X_r = np.column_stack([gate[lag - k - 1: N - k - 1] for k in range(lag)])
        X_r = np.hstack([np.ones((len(y), 1)), X_r])

        # Unrestricted: AR on gate + ε lags
        X_u = np.hstack([
            X_r,
            np.column_stack([eps[lag - k - 1: N - k - 1] for k in range(lag)]),
        ])

        try:
            beta_r, _, _, _ = np.linalg.lstsq(X_r, y, rcond=None)
            beta_u, _, _, _ = np.linalg.lstsq(X_u, y, rcond=None)

            rss_r = float(np.sum((y - X_r @ beta_r) ** 2))
            rss_u = float(np.sum((y - X_u @ beta_u) ** 2))

            n  = len(y)
            q  = lag                              # extra parameters
            k  = X_u.shape[1]
            f  = ((rss_r - rss_u) / q) / (rss_u / (n - k) + 1e-12)
            p  = float(1.0 - stats.f.cdf(f, q, n - k))
        except np.linalg.LinAlgError:
            f, p = float("nan"), 1.0

        rows.append({
            "lag": lag,
            "F":   float(f) if not math.isnan(f) else None,
            "p":   p,
            "granger_causal": p < ALPHA,
        })

    significant = [r for r in rows if r["granger_causal"]]

    fig = None
    if MPL:
        fig, axes = plt.subplots(1, 2, figsize=(10, 4))
        axes[0].plot([r["lag"] for r in rows], [r["F"] or 0 for r in rows], marker="o")
        axes[0].set(xlabel="Lag", ylabel="F-statistic", title="Granger F-statistics")
        axes[1].plot([r["lag"] for r in rows], [r["p"] for r in rows], marker="o")
        axes[1].axhline(ALPHA, color="red", linestyle="--", label=f"α={ALPHA}")
        axes[1].set(xlabel="Lag", ylabel="p-value", title="Granger p-values")
        axes[1].legend()
        fig.tight_layout()

    return {
        "values": rows,
        "plot":   fig,
        "json": {
            "n_significant_lags": len(significant),
            "significant_lags": [r["lag"] for r in significant],
            "granger_causal_overall": len(significant) > 0,
            "alpha": ALPHA,
        },
    }


# ---------------------------------------------------------------------------
# 5. Pre/post error reduction
# ---------------------------------------------------------------------------

def pre_post_error_reduction(
    epsilon_series: np.ndarray,
    action_times:   np.ndarray,
    pre_window:     float,
    post_window:    float,
    f_tick:         int = 50,
) -> Dict:
    """
    Test whether gate-triggered actions reduce prediction error.

    For each gate event, compare mean |ε| in [−pre, 0) vs (0, +post].

    Returns
    -------
    dict with mean_pre, mean_post, reduction, t-statistic, p-value, plot, json.
    """
    pre_ticks  = int(pre_window  * f_tick)
    post_ticks = int(post_window * f_tick)
    N  = len(epsilon_series)
    eps = np.abs(epsilon_series)

    pre_means, post_means = [], []
    for t in action_times.astype(int):
        pre_start  = t - pre_ticks
        post_end   = t + post_ticks
        if pre_start >= 0 and post_end <= N:
            pre_means.append(eps[pre_start: t].mean())
            post_means.append(eps[t: post_end].mean())

    if not pre_means:
        return {"values": None, "plot": None,
                "json": {"error": "no_valid_gate_windows"}}

    pre  = np.array(pre_means)
    post = np.array(post_means)

    t_stat, p_val = stats.ttest_rel(pre, post)
    reduction_pct = float((pre.mean() - post.mean()) / (pre.mean() + 1e-9) * 100)

    fig = None
    if MPL:
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.boxplot([pre, post], labels=["Pre-gate", "Post-gate"])
        ax.set(ylabel="|ε|", title=f"Error reduction (t={t_stat:.2f}, p={p_val:.4f})")
        fig.tight_layout()

    return {
        "values": {"pre": pre, "post": post},
        "plot":   fig,
        "json": {
            "mean_pre":       float(pre.mean()),
            "mean_post":      float(post.mean()),
            "reduction_pct":  reduction_pct,
            "t_statistic":    float(t_stat),
            "p_value":        float(p_val),
            "significant":    float(p_val) < ALPHA,
            "n_events":       len(pre_means),
        },
    }


# ---------------------------------------------------------------------------
# 6. Ablation effect size
# ---------------------------------------------------------------------------

def ablation_effect_size(
    connected_metrics: Dict[str, List[float]],
    ablated_metrics:   Dict[str, List[float]],
) -> Dict:
    """
    Compute Cohen's d and Mann-Whitney U between connected and ablated runs
    for each metric key.

    Parameters
    ----------
    connected_metrics, ablated_metrics : dicts mapping metric_name → list of values
        (one value per run).

    Returns
    -------
    dict with per-metric effect sizes, p-values, plot, json.
    """
    results = {}
    for key in connected_metrics:
        c = np.array(connected_metrics[key], dtype=float)
        a = np.array(ablated_metrics.get(key, []), dtype=float)
        if len(c) == 0 or len(a) == 0:
            continue

        # Cohen's d
        pooled_std = math.sqrt((c.var() + a.var()) / 2.0 + 1e-12)
        d = (c.mean() - a.mean()) / pooled_std

        # Mann-Whitney U
        u_stat, p_val = stats.mannwhitneyu(c, a, alternative="two-sided")
        results[key] = {
            "connected_mean": float(c.mean()),
            "ablated_mean":   float(a.mean()),
            "cohens_d":       float(d),
            "mwu_stat":       float(u_stat),
            "p_value":        float(p_val),
            "significant":    float(p_val) < ALPHA,
        }

    fig = None
    if MPL and results:
        keys   = list(results.keys())
        ds     = [results[k]["cohens_d"] for k in keys]
        colors = ["green" if abs(d) >= 0.5 else "orange" for d in ds]
        fig, ax = plt.subplots(figsize=(max(6, len(keys) * 1.5), 4))
        ax.bar(keys, ds, color=colors)
        ax.axhline(0,    color="black", linewidth=0.8)
        ax.axhline(0.5,  color="green",  linestyle="--", alpha=0.5, label="medium d=0.5")
        ax.axhline(-0.5, color="green",  linestyle="--", alpha=0.5)
        ax.set(ylabel="Cohen's d (connected − ablated)",
               title="Ablation effect sizes")
        ax.legend()
        fig.tight_layout()

    return {
        "values": results,
        "plot":   fig,
        "json":   {k: {kk: vv for kk, vv in v.items() if kk != "significant" or True}
                   for k, v in results.items()},
    }
