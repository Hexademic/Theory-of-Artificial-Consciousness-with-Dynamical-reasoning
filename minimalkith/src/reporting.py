"""
reporting.py — Automated one-page HTML report generator for MinimalKith batches.

Generates a self-contained HTML file summarising all six analysis outputs for a
given batch.  Optionally embeds base64-encoded matplotlib figures.

Usage:
    from minimalkith.src.reporting import BatchReport
    report = BatchReport.from_database("data/runs/batch_001.db")
    report.write_html("reports/batch_001.html")
"""

from __future__ import annotations

import base64
import io
import json
import logging
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from .persistence import Database
from .analysis import (
    compute_peri_event_histogram,
    lagged_cross_correlation,
    time_lagged_regression,
    granger_test,
    pre_post_error_reduction,
    ablation_effect_size,
)

logger = logging.getLogger("MK.Reporting")

# Try matplotlib for figure embedding
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    MPL = True
except ImportError:
    plt = None
    MPL = False


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class RunSummary:
    run_id:     int
    condition:  str
    seed:       int
    n_ticks:    int
    gate_fires: int
    mean_eps:   float
    max_eps:    float
    mean_ise:   float


@dataclass
class BatchAnalysis:
    batch_id:     str
    n_runs:       int
    conditions:   List[str]
    run_summaries: List[RunSummary]
    peri_event:   Optional[Dict] = None
    xcorr:        Optional[Dict] = None
    regression:   Optional[Dict] = None
    granger:      Optional[Dict] = None
    error_red:    Optional[Dict] = None
    ablation:     Optional[Dict] = None


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

class BatchReport:
    """
    Loads data from a Database and runs all six analyses, then renders HTML.
    """

    def __init__(self, analysis: BatchAnalysis):
        self._analysis = analysis

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_database(
        cls,
        db_path:    str,
        batch_id:   str = "unknown",
        f_tick:     int = 50,
        window_s:   float = 2.0,
        max_lag_s:  float = 2.0,
        lags:       Optional[List[int]] = None,
        granger_maxlag: int = 10,
        pre_window: float = 1.0,
        post_window: float = 1.0,
    ) -> "BatchReport":
        """
        Read all runs from the database, run analyses, return a BatchReport.
        """
        lags = lags or list(range(1, 11))

        with Database(db_path) as db:
            runs = db.fetch_runs()
            if not runs:
                raise ValueError(f"No runs found in {db_path}")

            summaries: List[RunSummary] = []
            eps_by_cond: Dict[str, List[np.ndarray]] = {}
            gate_by_cond: Dict[str, List[np.ndarray]] = {}
            ise_by_cond:  Dict[str, List[np.ndarray]] = {}
            gate_times_all: List[np.ndarray] = []

            for run in runs:
                rid  = run["run_id"]
                cond = run["condition"]
                rows = db.fetch_states(rid)
                if not rows:
                    continue

                eps_arr  = np.array([r["epsilon"]    for r in rows])
                gate_arr = np.array([r["gate_state"] for r in rows], dtype=float)
                ise_arr  = np.array([r["ISE"]        for r in rows])

                gate_fires = int(gate_arr.sum())
                summaries.append(RunSummary(
                    run_id=rid,
                    condition=cond,
                    seed=run["seed"],
                    n_ticks=len(rows),
                    gate_fires=gate_fires,
                    mean_eps=float(np.mean(np.abs(eps_arr))),
                    max_eps=float(np.max(np.abs(eps_arr))),
                    mean_ise=float(ise_arr.mean()),
                ))

                eps_by_cond.setdefault(cond, []).append(eps_arr)
                gate_by_cond.setdefault(cond, []).append(gate_arr)
                ise_by_cond.setdefault(cond, []).append(ise_arr)

                gate_times = np.where(gate_arr > 0)[0].astype(float)
                if len(gate_times):
                    gate_times_all.append(gate_times)

        # Choose the first Baseline run for within-run analyses
        baseline_eps  = eps_by_cond.get("Baseline",  [None])[0]
        baseline_gate = gate_by_cond.get("Baseline", [None])[0]
        baseline_ise  = ise_by_cond.get("Baseline",  [None])[0]
        gate_times    = gate_times_all[0] if gate_times_all else np.array([])

        peri  = None
        xcorr = None
        reg   = None
        gran  = None
        err_r = None
        abla  = None

        if baseline_eps is not None and len(gate_times):
            peri  = compute_peri_event_histogram(baseline_eps, gate_times, window_s, f_tick)
            xcorr = lagged_cross_correlation(baseline_eps, baseline_gate, max_lag_s, f_tick)
            reg   = time_lagged_regression(baseline_gate, baseline_eps, baseline_ise, lags)
            gran  = granger_test(baseline_gate, baseline_eps, granger_maxlag)
            err_r = pre_post_error_reduction(baseline_eps, gate_times, pre_window, post_window, f_tick)

        # Ablation effect size: compare Baseline vs Ablation per metric
        if "Baseline" in eps_by_cond and "Ablation" in eps_by_cond:
            conn_metrics = {
                "gate_fires": [float(s.gate_fires) for s in summaries if s.condition == "Baseline"],
                "mean_eps":   [s.mean_eps          for s in summaries if s.condition == "Baseline"],
                "mean_ise":   [s.mean_ise           for s in summaries if s.condition == "Baseline"],
            }
            abla_metrics = {
                "gate_fires": [float(s.gate_fires) for s in summaries if s.condition == "Ablation"],
                "mean_eps":   [s.mean_eps          for s in summaries if s.condition == "Ablation"],
                "mean_ise":   [s.mean_ise           for s in summaries if s.condition == "Ablation"],
            }
            abla = ablation_effect_size(conn_metrics, abla_metrics)

        analysis = BatchAnalysis(
            batch_id=batch_id,
            n_runs=len(summaries),
            conditions=sorted(set(s.condition for s in summaries)),
            run_summaries=summaries,
            peri_event=peri,
            xcorr=xcorr,
            regression=reg,
            granger=gran,
            error_red=err_r,
            ablation=abla,
        )
        return cls(analysis)

    # ------------------------------------------------------------------
    # HTML rendering
    # ------------------------------------------------------------------

    def write_html(self, out_path: str) -> str:
        """
        Render and write the HTML report.  Returns the path written.
        """
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        html = self._render_html()
        Path(out_path).write_text(html, encoding="utf-8")
        logger.info(f"[Report] Written to {out_path}")
        return out_path

    def _render_html(self) -> str:
        a = self._analysis
        ts = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
        sections = [
            self._section_overview(),
            self._section_condition_table(),
            self._section_peri_event(),
            self._section_xcorr(),
            self._section_regression(),
            self._section_granger(),
            self._section_error_reduction(),
            self._section_ablation(),
        ]
        body = "\n".join(sections)
        return _HTML_TEMPLATE.format(
            batch_id=a.batch_id,
            timestamp=ts,
            n_runs=a.n_runs,
            body=body,
        )

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------

    def _section_overview(self) -> str:
        a = self._analysis
        conds = ", ".join(a.conditions)
        return f"""
<section>
<h2>Batch overview</h2>
<table>
  <tr><th>Batch ID</th><td><code>{a.batch_id}</code></td></tr>
  <tr><th>Total runs</th><td>{a.n_runs}</td></tr>
  <tr><th>Conditions</th><td>{conds}</td></tr>
</table>
</section>"""

    def _section_condition_table(self) -> str:
        rows_html = ""
        # Group by condition
        by_cond: Dict[str, List[RunSummary]] = {}
        for s in self._analysis.run_summaries:
            by_cond.setdefault(s.condition, []).append(s)

        for cond, slist in sorted(by_cond.items()):
            n        = len(slist)
            mean_gf  = float(np.mean([s.gate_fires for s in slist]))
            mean_eps = float(np.mean([s.mean_eps   for s in slist]))
            mean_ise = float(np.mean([s.mean_ise   for s in slist]))
            rows_html += (
                f"<tr><td>{cond}</td><td>{n}</td>"
                f"<td>{mean_gf:.1f}</td>"
                f"<td>{mean_eps:.4f}</td>"
                f"<td>{mean_ise:.4f}</td></tr>\n"
            )

        return f"""
<section>
<h2>Condition summary</h2>
<table>
  <tr><th>Condition</th><th>N</th><th>Mean gate fires</th><th>Mean |ε|</th><th>Mean ISE</th></tr>
  {rows_html}
</table>
</section>"""

    def _section_peri_event(self) -> str:
        d = self._analysis.peri_event
        if d is None:
            return "<section><h2>1. Peri-event histogram</h2><p><em>No data.</em></p></section>"
        jd = d.get("json", {})
        fig_html = _embed_figure(d.get("plot"))
        return f"""
<section>
<h2>1. Peri-event histogram</h2>
<p>Events: <strong>{jd.get('n_events', '—')}</strong> &nbsp;|&nbsp;
   Pre-gate peak ε: <strong>{jd.get('pre_peak_eps', float('nan')):.4f}</strong> &nbsp;|&nbsp;
   Window: ±{jd.get('window_s', '?')} s</p>
{fig_html}
</section>"""

    def _section_xcorr(self) -> str:
        d = self._analysis.xcorr
        if d is None:
            return "<section><h2>2. Lagged cross-correlation</h2><p><em>No data.</em></p></section>"
        jd = d.get("json", {})
        causal = "✓ Yes" if jd.get("causal") else "✗ No"
        fig_html = _embed_figure(d.get("plot"))
        return f"""
<section>
<h2>2. Lagged cross-correlation</h2>
<p>Peak lag: <strong>{jd.get('peak_lag_s', 0):.3f} s</strong> &nbsp;|&nbsp;
   Peak r: <strong>{jd.get('peak_r', 0):.4f}</strong> &nbsp;|&nbsp;
   Causal (ε → gate): <strong>{causal}</strong></p>
{fig_html}
</section>"""

    def _section_regression(self) -> str:
        d = self._analysis.regression
        if d is None:
            return "<section><h2>3. Time-lagged regression</h2><p><em>No data.</em></p></section>"
        jd = d.get("json", {})
        best = jd.get("best_lag", {})
        fig_html = _embed_figure(d.get("plot"))
        best_txt = (
            f"lag={best.get('lag', '?')} "
            f"R²={best.get('r2', 0):.4f} "
            f"p={best.get('p', 1):.4f}"
        ) if best else "—"
        return f"""
<section>
<h2>3. Time-lagged regression (gate ~ ε + ISE)</h2>
<p>Best lag: <strong>{best_txt}</strong></p>
{fig_html}
</section>"""

    def _section_granger(self) -> str:
        d = self._analysis.granger
        if d is None:
            return "<section><h2>4. Granger causality</h2><p><em>No data.</em></p></section>"
        jd = d.get("json", {})
        overall = "✓ Yes" if jd.get("granger_causal_overall") else "✗ No"
        sig_lags = jd.get("significant_lags", [])
        fig_html = _embed_figure(d.get("plot"))
        return f"""
<section>
<h2>4. Granger causality (ε → gate)</h2>
<p>Overall: <strong>{overall}</strong> &nbsp;|&nbsp;
   Significant lags (α={jd.get('alpha', 0.01)}): <strong>{sig_lags or 'none'}</strong></p>
{fig_html}
</section>"""

    def _section_error_reduction(self) -> str:
        d = self._analysis.error_red
        if d is None:
            return "<section><h2>5. Pre/post error reduction</h2><p><em>No data.</em></p></section>"
        jd = d.get("json", {})
        if "error" in jd:
            return f"<section><h2>5. Pre/post error reduction</h2><p><em>{jd['error']}</em></p></section>"
        sig = "✓ Yes" if jd.get("significant") else "✗ No"
        fig_html = _embed_figure(d.get("plot"))
        return f"""
<section>
<h2>5. Pre/post error reduction</h2>
<p>Mean pre: <strong>{jd.get('mean_pre', 0):.4f}</strong> &nbsp;|&nbsp;
   Mean post: <strong>{jd.get('mean_post', 0):.4f}</strong> &nbsp;|&nbsp;
   Reduction: <strong>{jd.get('reduction_pct', 0):.1f}%</strong> &nbsp;|&nbsp;
   t={jd.get('t_statistic', 0):.2f} p={jd.get('p_value', 1):.4f} &nbsp;|&nbsp;
   Significant: <strong>{sig}</strong></p>
{fig_html}
</section>"""

    def _section_ablation(self) -> str:
        d = self._analysis.ablation
        if d is None:
            return "<section><h2>6. Ablation effect sizes</h2><p><em>No data.</em></p></section>"
        results = d.get("values", {})
        rows_html = ""
        for metric, v in results.items():
            sig = "✓" if v.get("significant") else ""
            rows_html += (
                f"<tr><td>{metric}</td>"
                f"<td>{v['connected_mean']:.4f}</td>"
                f"<td>{v['ablated_mean']:.4f}</td>"
                f"<td>{v['cohens_d']:.3f}</td>"
                f"<td>{v['p_value']:.4f}</td>"
                f"<td>{sig}</td></tr>\n"
            )
        fig_html = _embed_figure(d.get("plot"))
        return f"""
<section>
<h2>6. Ablation effect sizes (Baseline vs Ablation)</h2>
<table>
  <tr><th>Metric</th><th>Connected mean</th><th>Ablated mean</th>
      <th>Cohen's d</th><th>p-value</th><th>Sig.*</th></tr>
  {rows_html}
</table>
<p><em>* α = 0.01 (Mann-Whitney U)</em></p>
{fig_html}
</section>"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _embed_figure(fig) -> str:
    """Return an <img> tag with base64-encoded PNG, or empty string."""
    if fig is None or not MPL:
        return ""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    plt.close(fig)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f'<img src="data:image/png;base64,{b64}" style="max-width:100%;"/>'


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>MinimalKith Batch Report — {batch_id}</title>
<style>
  body  {{ font-family: sans-serif; max-width: 960px; margin: 2em auto; color: #222; }}
  h1   {{ border-bottom: 2px solid #444; padding-bottom: 0.3em; }}
  h2   {{ color: #333; margin-top: 2em; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1em 0; }}
  th,td {{ border: 1px solid #ccc; padding: 0.4em 0.7em; text-align: left; }}
  th   {{ background: #f0f0f0; }}
  img  {{ border: 1px solid #ddd; margin: 0.5em 0; }}
  code {{ background: #f6f6f6; padding: 0.1em 0.3em; border-radius: 3px; }}
  section {{ margin-bottom: 2em; }}
  footer {{ font-size: 0.8em; color: #888; margin-top: 3em; border-top: 1px solid #eee; padding-top: 0.5em; }}
</style>
</head>
<body>
<h1>MinimalKith Batch Report</h1>
<p><strong>Batch:</strong> <code>{batch_id}</code> &nbsp;|&nbsp;
   <strong>Runs:</strong> {n_runs} &nbsp;|&nbsp;
   <strong>Generated:</strong> {timestamp}</p>

{body}

<footer>Generated by MinimalKith reporting.py · Constitutional Phenomenology Framework</footer>
</body>
</html>
"""
