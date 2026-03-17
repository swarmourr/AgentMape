"""
LLM Council Evaluator Agent — MAPE-K Pegasus Workflow System
Port 8084

Decoupled from Planner via file-based pipeline:
  pipeline_data/planner_output/pending/   ← reads input files
  pipeline_data/planner_output/processed/ ← moves processed files here
  pipeline_data/evaluator_output/         ← writes final verdicts (shared)
  Evaluator/results/                      ← local copy of all results
"""

import asyncio
import glob
import json
import logging
import os
import uuid
from datetime import datetime
from enum import Enum
from typing import Dict, Any, List, Optional

import aiohttp
from aiohttp import web

from metrics_registry import MetricsRegistry
from council_manager import CouncilManager, EvaluationContext
from aggregator import Aggregator

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger("evaluator")


# ─────────────────────────────────────────────────────────────────────────────
# Terminal colours (consistent with rest of project)
# ─────────────────────────────────────────────────────────────────────────────

class TerminalColor(Enum):
    RED          = "\033[91m"
    GREEN        = "\033[92m"
    YELLOW       = "\033[93m"
    CYAN         = "\033[96m"
    BRIGHT_WHITE = "\033[97m"
    BRIGHT_CYAN  = "\033[96;1m"
    BRIGHT_GREEN = "\033[92;1m"
    BRIGHT_MAGENTA = "\033[95;1m"
    RESET        = "\033[0m"

    def apply(self, text: str) -> str:
        return f"{self.value}{text}{TerminalColor.RESET.value}"


# ─────────────────────────────────────────────────────────────────────────────
# Core Evaluator
# ─────────────────────────────────────────────────────────────────────────────

class LLMEvaluator:
    """
    Orchestrates the full evaluation pipeline:
    File watcher → EvaluationContext → CouncilManager → Aggregator → Save results
    """

    def __init__(self, config_file: str = "evaluator_config.json"):
        self.config = self._load_config(config_file)
        self.config_file = config_file

        self.metrics_registry = MetricsRegistry(config_file)
        self.council_manager  = CouncilManager(self.config)
        self.aggregator       = Aggregator()

        # Resolve pipeline_data relative to this file's location
        base = os.path.dirname(os.path.abspath(__file__))
        pipeline_root = os.path.normpath(
            os.path.join(base, self.config.get("pipeline_data_dir", "../pipeline_data"))
        )

        self.pending_dir   = os.path.join(pipeline_root, "planner_output", "pending")
        self.processed_dir = os.path.join(pipeline_root, "planner_output", "processed")
        self.shared_out    = os.path.join(pipeline_root, "evaluator_output")
        self.local_out     = os.path.join(base, "results")

        for d in [self.pending_dir, self.processed_dir, self.shared_out, self.local_out]:
            os.makedirs(d, exist_ok=True)

        self._processed_count = 0
        self._failed_count    = 0

    # ── Config ──────────────────────────────────────────────────────────────

    def _load_config(self, path: str) -> Dict[str, Any]:
        try:
            with open(path) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Config load error: {e}")
            return {}

    def reload_config(self):
        self.config = self._load_config(self.config_file)
        self.council_manager = CouncilManager(self.config)

    # ── File watcher ─────────────────────────────────────────────────────────

    async def watch_loop(self):
        interval = self.config.get("watch_interval_seconds", 5)
        logger.info(f"File watcher started — polling every {interval}s")

        while True:
            try:
                pending = sorted(glob.glob(os.path.join(self.pending_dir, "*.json")))
                for file_path in pending:
                    await self._process_file(file_path)
            except Exception as e:
                logger.error(f"Watch loop error: {e}")
            await asyncio.sleep(interval)

    async def _process_file(self, file_path: str):
        """Claim, process, and move a single pipeline file"""
        processing_path = file_path + ".processing"
        try:
            os.rename(file_path, processing_path)   # atomic claim
        except OSError:
            return  # already claimed by another instance

        filename = os.path.basename(file_path)
        print(f"\n{'='*80}")
        print(f"{TerminalColor.BRIGHT_CYAN.apply('📥 NEW PLANNER OUTPUT DETECTED')}")
        print(f"{TerminalColor.CYAN.apply('File:')} {filename}")
        print(f"{'='*80}")

        try:
            with open(processing_path) as f:
                data = json.load(f)

            result = await asyncio.get_event_loop().run_in_executor(
                None, self._evaluate_sync, data
            )

            self._save_results(data.get("workflow_id", "unknown"), result)

            # Move to processed
            processed_path = os.path.join(self.processed_dir, filename)
            os.rename(processing_path, processed_path)

            self._processed_count += 1
            action = result.get("final_verdict", {}).get("action", "unknown")
            print(f"{TerminalColor.BRIGHT_GREEN.apply('✓ Evaluation complete')} — action: {action}\n")

        except Exception as e:
            logger.error(f"Failed to process {filename}: {e}", exc_info=True)
            self._failed_count += 1
            # Return file to pending so it can be retried
            try:
                os.rename(processing_path, file_path)
            except OSError:
                pass

    # ── Evaluation pipeline ───────────────────────────────────────────────────

    def _evaluate_sync(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Full synchronous evaluation — runs inside executor"""
        workflow_id          = data.get("workflow_id", "unknown")
        analyzer_result      = data.get("analyzer_result", {})
        plans                = data.get("plans", {})
        catalogs             = data.get("catalogs", {})
        workflow_files       = data.get("workflow_files", {})
        parent_error_analysis = data.get("parent_error_analysis", {})
        request_metrics      = data.get("custom_metrics", [])

        plan_labels = list(plans.keys())
        logger.info(f"Evaluating workflow {workflow_id} — {len(plan_labels)} plan(s)")

        print(f"{TerminalColor.YELLOW.apply('Workflow:')} {workflow_id}")
        print(f"{TerminalColor.YELLOW.apply('Plans:')} {', '.join(plan_labels)}")

        # ── Metrics ──────────────────────────────────────────────────────────
        base_metrics = self.metrics_registry.get_all()
        metrics = self.metrics_registry.merge_request_metrics(base_metrics, request_metrics)
        print(f"{TerminalColor.YELLOW.apply('Metrics:')} {', '.join(m['name'] for m in metrics)}")

        # ── Build context (once, all tiers cached) ───────────────────────────
        context = EvaluationContext(
            workflow_id=workflow_id,
            analyzer_result=analyzer_result,
            plans=plans,
            metrics=metrics,
            catalogs=catalogs,
            workflow_files=workflow_files,
            parent_error_analysis=parent_error_analysis
        )
        context.build_all_tiers()

        # ── Run council ───────────────────────────────────────────────────────
        print(f"\n{TerminalColor.BRIGHT_MAGENTA.apply('🏛  COUNCIL EVALUATION')}")
        print(f"{'─'*60}")
        council_evaluations = self.council_manager.run_council(context)

        successful_count = sum(
            1 for e in council_evaluations.values() if e.get("_status") == "success"
        )
        print(f"Council: {successful_count}/{len(council_evaluations)} member(s) responded")

        # ── Aggregation ───────────────────────────────────────────────────────
        strategy = self.config.get("aggregation_strategy", "borda_count")
        tier_weights = {
            int(k): float(v)
            for k, v in self.config.get("tier_weights", {"1": 1.0, "2": 0.75, "3": 0.5}).items()
        }

        print(f"\n{TerminalColor.BRIGHT_MAGENTA.apply('⚖  AGGREGATION')} — strategy: {strategy}")
        print(f"{'─'*60}")

        aggregated = self.aggregator.aggregate(
            strategy, council_evaluations, plan_labels, metrics, tier_weights
        )

        for plan, score in sorted(aggregated["plan_scores"].items(), key=lambda x: -x[1]):
            marker = " ← winner" if plan == aggregated["winner"] else ""
            print(f"  {TerminalColor.CYAN.apply(plan)}: {score}{marker}")

        print(f"Inter-council agreement: {aggregated['inter_council_agreement']:.0%}")
        if aggregated.get("vetoed_plans"):
            print(f"{TerminalColor.YELLOW.apply('Vetoed:')} {aggregated['vetoed_plans']}")

        # ── Quality gate ──────────────────────────────────────────────────────
        threshold = self.config.get("quality_gate_threshold", 0.70)
        quality_gate = self._apply_quality_gate(aggregated, threshold)

        # ── Final verdict ─────────────────────────────────────────────────────
        verdict = self._build_verdict(aggregated, quality_gate, plans, council_evaluations)

        print(f"\n{TerminalColor.BRIGHT_MAGENTA.apply('📋 FINAL VERDICT')}")
        print(f"{'─'*60}")
        print(f"  Action:     {TerminalColor.BRIGHT_GREEN.apply(verdict['action'])}")
        print(f"  Winner:     {verdict.get('winning_model', 'none')}")
        print(f"  Confidence: {verdict['overall_confidence']:.0%}")
        if verdict.get("warnings"):
            for w in verdict["warnings"]:
                print(f"  {TerminalColor.YELLOW.apply('⚠')} {w}")

        return {
            "workflow_id":          workflow_id,
            "evaluation_id":        str(uuid.uuid4()),
            "timestamp":            datetime.now().isoformat(),
            "input_file":           data.get("_source_file", ""),
            "aggregation_strategy": strategy,

            "input": {
                "analyzer_result":      analyzer_result,
                "plans_received":       plans,
                "catalogs":             catalogs,
                "workflow_files":       workflow_files,
                "parent_error_analysis": parent_error_analysis
            },

            "metrics_used":        metrics,
            "council_evaluations": council_evaluations,
            "aggregated":          aggregated,
            "quality_gate":        quality_gate,
            "final_verdict":       verdict
        }

    def _apply_quality_gate(
        self,
        aggregated: Dict[str, Any],
        threshold: float
    ) -> Dict[str, Any]:
        winner        = aggregated.get("winner")
        plan_scores   = aggregated.get("plan_scores", {})
        winner_score  = plan_scores.get(winner, 0.0)
        vetoed        = aggregated.get("vetoed_plans", [])

        # Normalise score for strategies that use raw counts (borda, majority)
        strategy = aggregated.get("strategy", "borda_count")
        if strategy in ("borda_count", "majority"):
            max_score = max(plan_scores.values()) if plan_scores else 1.0
            normalised = winner_score / max_score if max_score > 0 else 0.0
        else:
            normalised = winner_score

        passed = (normalised >= threshold) and (winner not in vetoed)

        return {
            "passed":        passed,
            "winner_score":  round(winner_score, 4),
            "normalised":    round(normalised, 4),
            "threshold":     threshold,
            "veto_flags":    vetoed
        }

    def _build_verdict(
        self,
        aggregated:          Dict[str, Any],
        quality_gate:        Dict[str, Any],
        plans:               Dict[str, Any],
        council_evaluations: Dict[str, Any]
    ) -> Dict[str, Any]:

        winner       = aggregated.get("winner")
        winning_plan = plans.get(winner) if winner else None
        passed       = quality_gate.get("passed", False)
        agreement    = aggregated.get("inter_council_agreement", 0.0)

        # Determine action
        if not winning_plan:
            action = "hold_for_review"
        elif not passed:
            action = "hold_for_review"
        elif agreement < 0.5:
            action = "hold_for_review"
        else:
            action = "forward_to_executor"

        # Collect warnings
        warnings = []
        if not passed:
            warnings.append(
                f"Winner score {quality_gate['normalised']:.0%} below threshold {quality_gate['threshold']:.0%}"
            )
        if agreement < 0.5:
            warnings.append(f"Low council agreement ({agreement:.0%}) — members disagree on best plan")
        if aggregated.get("vetoed_plans"):
            warnings.append(f"Vetoed plans: {aggregated['vetoed_plans']}")

        # Collect all contradictions from all members
        all_contradictions = []
        for ev in council_evaluations.values():
            for c in ev.get("contradictions", []):
                if c.get("plan") == winner:
                    all_contradictions.append(c)

        # Dissenting opinions (members who ranked winner lower)
        dissenting = []
        for member_label, ev in council_evaluations.items():
            if ev.get("_status") != "success":
                continue
            ranking = ev.get("ranking", [])
            if ranking and ranking[0] != winner:
                dissenting.append(
                    f"{member_label} preferred {ranking[0]} over {winner}"
                )

        confidence = quality_gate.get("normalised", 0.0) * agreement if passed else quality_gate.get("normalised", 0.0)

        return {
            "action":               action,
            "winning_model":        winner,
            "winning_plan":         winning_plan,
            "overall_confidence":   round(confidence, 4),
            "warnings":             warnings,
            "contradictions_on_winner": all_contradictions,
            "dissenting_opinions":  dissenting
        }

    # ── Save results ──────────────────────────────────────────────────────────

    def _save_results(self, workflow_id: str, result: Dict[str, Any]):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{workflow_id}__{ts}__evaluator.json"

        # Shared pipeline output
        shared_wf_dir = os.path.join(self.shared_out, workflow_id)
        os.makedirs(shared_wf_dir, exist_ok=True)
        shared_path = os.path.join(shared_wf_dir, filename)

        # Local copy
        local_wf_dir = os.path.join(self.local_out, workflow_id)
        os.makedirs(local_wf_dir, exist_ok=True)
        local_path = os.path.join(local_wf_dir, filename)

        for path in [shared_path, local_path]:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(result, f, indent=2, default=str)
                logger.info(f"Results saved: {path}")
            except Exception as e:
                logger.error(f"Failed to save results to {path}: {e}")

        print(f"  {TerminalColor.GREEN.apply('💾 Saved:')} {local_path}")

    # ── Manual evaluation (called from API) ───────────────────────────────────

    def evaluate_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate a manually submitted payload (not from file)"""
        result = self._evaluate_sync(data)
        self._save_results(data.get("workflow_id", "manual"), result)
        return result


# ─────────────────────────────────────────────────────────────────────────────
# HTTP API
# ─────────────────────────────────────────────────────────────────────────────

class EvaluatorAPI:

    def __init__(self, evaluator: LLMEvaluator):
        self.evaluator = evaluator
        self.app = web.Application()
        self._setup_routes()

    def _setup_routes(self):
        r = self.app.router
        r.add_get("/health",                              self.health)
        r.add_post("/api/evaluate",                       self.manual_evaluate)
        r.add_get("/api/evaluations",                     self.list_evaluations)
        r.add_get("/api/evaluations/{workflow_id}",       self.get_evaluations)
        r.add_get("/api/evaluations/{workflow_id}/latest",self.get_latest)
        r.add_get("/api/metrics",                         self.list_metrics)
        r.add_post("/api/metrics",                        self.add_metric)
        r.add_delete("/api/metrics/{name}",               self.remove_metric)
        r.add_put("/api/config/strategy",                 self.set_strategy)

    # ── Health ────────────────────────────────────────────────────────────────

    async def health(self, request: web.Request) -> web.Response:
        council = self.evaluator.config.get("council_models", [])
        return web.json_response({
            "status":                "running",
            "agent":                 "evaluator",
            "port":                  self.evaluator.config.get("http_port", 8084),
            "council_models":        [m["label"] for m in council],
            "aggregation_strategy":  self.evaluator.config.get("aggregation_strategy"),
            "quality_gate_threshold": self.evaluator.config.get("quality_gate_threshold"),
            "processed_count":       self.evaluator._processed_count,
            "failed_count":          self.evaluator._failed_count,
            "timestamp":             datetime.now().isoformat()
        })

    # ── Manual evaluate ───────────────────────────────────────────────────────

    async def manual_evaluate(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, self.evaluator.evaluate_payload, data
            )
            return web.json_response({"status": "ok", "evaluation": result})
        except Exception as e:
            logger.error(f"Manual evaluate error: {e}", exc_info=True)
            return web.json_response({"status": "error", "error": str(e)}, status=500)

    # ── Evaluations ───────────────────────────────────────────────────────────

    async def list_evaluations(self, request: web.Request) -> web.Response:
        """List all workflow IDs that have evaluation results"""
        local_out = self.evaluator.local_out
        try:
            workflow_ids = [
                d for d in os.listdir(local_out)
                if os.path.isdir(os.path.join(local_out, d))
            ]
            return web.json_response({"workflow_ids": sorted(workflow_ids)})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def get_evaluations(self, request: web.Request) -> web.Response:
        """Return all evaluation files for a workflow"""
        wf_id = request.match_info["workflow_id"]
        wf_dir = os.path.join(self.evaluator.local_out, wf_id)
        if not os.path.isdir(wf_dir):
            return web.json_response({"error": "not found"}, status=404)
        results = []
        for f in sorted(glob.glob(os.path.join(wf_dir, "*.json"))):
            try:
                with open(f) as fp:
                    results.append(json.load(fp))
            except Exception:
                pass
        return web.json_response({"workflow_id": wf_id, "evaluations": results})

    async def get_latest(self, request: web.Request) -> web.Response:
        """Return the most recent evaluation for a workflow"""
        wf_id = request.match_info["workflow_id"]
        wf_dir = os.path.join(self.evaluator.local_out, wf_id)
        files = sorted(glob.glob(os.path.join(wf_dir, "*.json")))
        if not files:
            return web.json_response({"error": "not found"}, status=404)
        try:
            with open(files[-1]) as f:
                return web.json_response(json.load(f))
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    # ── Metrics ───────────────────────────────────────────────────────────────

    async def list_metrics(self, request: web.Request) -> web.Response:
        return web.json_response({"metrics": self.evaluator.metrics_registry.get_all()})

    async def add_metric(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
            name        = body.get("name", "").strip()
            description = body.get("description", "").strip()
            weight      = int(body.get("weight", 2))
            if not name or not description:
                return web.json_response({"error": "name and description required"}, status=400)
            ok = self.evaluator.metrics_registry.add_metric(name, description, weight)
            if ok:
                return web.json_response({"status": "added", "metric": name})
            return web.json_response({"error": f"metric '{name}' already exists"}, status=409)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def remove_metric(self, request: web.Request) -> web.Response:
        name = request.match_info["name"]
        ok = self.evaluator.metrics_registry.remove_metric(name)
        if ok:
            return web.json_response({"status": "removed", "metric": name})
        return web.json_response({"error": f"metric '{name}' not found or is builtin"}, status=404)

    # ── Config ────────────────────────────────────────────────────────────────

    async def set_strategy(self, request: web.Request) -> web.Response:
        try:
            body     = await request.json()
            strategy = body.get("strategy", "").strip()
            if strategy not in Aggregator.STRATEGIES:
                return web.json_response({
                    "error": f"invalid strategy, choose from {Aggregator.STRATEGIES}"
                }, status=400)
            # Update in-memory config
            self.evaluator.config["aggregation_strategy"] = strategy
            # Persist to config file
            if os.path.exists(self.evaluator.config_file):
                with open(self.evaluator.config_file) as f:
                    cfg = json.load(f)
                cfg["aggregation_strategy"] = strategy
                with open(self.evaluator.config_file, "w") as f:
                    json.dump(cfg, f, indent=4)
            return web.json_response({"status": "updated", "aggregation_strategy": strategy})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    evaluator = LLMEvaluator("evaluator_config.json")
    api       = EvaluatorAPI(evaluator)
    port      = evaluator.config.get("http_port", 8084)

    runner = web.AppRunner(api.app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    # Print startup banner
    print(f"\n{'='*80}")
    print(f"{TerminalColor.BRIGHT_CYAN.apply('  LLM COUNCIL EVALUATOR  —  MAPE-K Pegasus Workflow System')}")
    print(f"{'='*80}")
    print(f"{TerminalColor.CYAN.apply('🌐 HTTP API:')}  http://localhost:{port}")
    council = evaluator.config.get("council_models", [])
    print(f"{TerminalColor.CYAN.apply('🏛  Council:')}")
    for m in council:
        tier = m.get('tier', 2)
        print(f"    • {m['label']}  (tier {tier})")
    print(f"{TerminalColor.CYAN.apply('⚖  Strategy:')}  {evaluator.config.get('aggregation_strategy')}")
    print(f"{TerminalColor.CYAN.apply('🎯 Threshold:')} {evaluator.config.get('quality_gate_threshold')}")
    print(f"{TerminalColor.CYAN.apply('📂 Watching:')}  {evaluator.pending_dir}")
    print(f"\n{TerminalColor.BRIGHT_CYAN.apply('📋 Available Endpoints:')}")
    print(f"   GET  /health")
    print(f"   POST /api/evaluate                      — manual trigger")
    print(f"   GET  /api/evaluations                   — list all workflow IDs")
    print(f"   GET  /api/evaluations/{{id}}              — all evaluations for workflow")
    print(f"   GET  /api/evaluations/{{id}}/latest       — most recent verdict")
    print(f"   GET  /api/metrics                       — list metrics")
    print(f"   POST /api/metrics                       — add user metric")
    print(f"   DELETE /api/metrics/{{name}}              — remove user metric")
    print(f"   PUT  /api/config/strategy               — switch aggregation strategy")
    print(f"\n{TerminalColor.CYAN.apply('Press Ctrl+C to stop')}")
    print(f"{'='*80}\n")

    # Start file watcher alongside HTTP server
    watcher_task = asyncio.create_task(evaluator.watch_loop())

    try:
        await asyncio.Future()   # run forever
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Shutting down evaluator…")
        watcher_task.cancel()
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
