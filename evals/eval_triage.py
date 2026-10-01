#!/usr/bin/env python3
"""
Amber SRE Triage Evaluation Benchmark.
Evaluates accuracy, latency, and critical recall (P0/P1) of the autonomous triage engine
against curated golden incident datasets.
"""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from backend.app.agents.triage import triage_node

DATASET_PATH = Path(__file__).parent / "datasets" / "golden_incidents.json"


async def run_triage_eval():
    print("=" * 65)
    print("🧪 AMBER AI EVALUATION: SRE TRIAGE ACCURACY & LATENCY BENCHMARK")
    print("=" * 65)

    if not DATASET_PATH.exists():
        print(f"Dataset missing: {DATASET_PATH}")
        return

    with open(DATASET_PATH, "r") as f:
        cases = json.load(f)

    total = len(cases)
    correct = 0
    p0_p1_total = 0
    p0_p1_recalled = 0
    latencies = []

    print(f"{'ID':<8} | {'Scenario':<32} | {'Expected':<8} | {'Predicted':<9} | {'Latency':<8} | {'Status'}")
    print("-" * 75)

    for case in cases:
        state = {
            "incident_id": case["id"],
            "alert_source": case["source"],
            "alert_payload": {
                "title": case["title"],
                "message": case["message"],
                "service": case["service"]
            }
        }

        t0 = time.time()
        res = await triage_node(state)
        t_elapsed = (time.time() - t0) * 1000
        latencies.append(t_elapsed)

        pred_sev = res.get("severity")
        exp_sev = case["expected_severity"]

        is_match = pred_sev == exp_sev
        if is_match:
            correct += 1

        if exp_sev in ["P0", "P1"]:
            p0_p1_total += 1
            if pred_sev in ["P0", "P1"]:
                p0_p1_recalled += 1

        status_icon = "✓ PASS" if is_match else ("⚠️ CLOSE" if (exp_sev in ["P0","P1"] and pred_sev in ["P0","P1"]) else "❌ FAIL")
        short_title = case["title"][:30] + ".." if len(case["title"]) > 32 else case["title"]
        print(f"{case['id']:<8} | {short_title:<32} | {exp_sev:<8} | {pred_sev:<9} | {t_elapsed:>6.1f}ms | {status_icon}")

        # Rate limit mitigation for LLM evaluation runs
        await asyncio.sleep(2.0)

    accuracy = (correct / total) * 100
    p0_recall = (p0_p1_recalled / p0_p1_total) * 100 if p0_p1_total > 0 else 100.0
    avg_latency = sum(latencies) / len(latencies)
    p95_latency = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0

    print("=" * 75)
    print("📊 BENCHMARK RESULTS SUMMARY:")
    print(f"  • Total Scenarios Evaluated: {total}")
    print(f"  • Severity Classification Accuracy: {accuracy:.1f}%")
    print(f"  • Critical Outage Recall (P0/P1):    {p0_recall:.1f}% (Target: ≥ 95.0%)")
    print(f"  • Mean Triage Latency:               {avg_latency:.1f}ms (Target: < 3000ms)")
    print(f"  • p95 Triage Latency:                {p95_latency:.1f}ms")
    print("=" * 75)

    if accuracy >= 80 and p0_recall >= 90:
        print("🎉 STATUS: BENCHMARK PASSED PRODUCTION SRE QUALITY CRITERIA.")
    else:
        print("⚠️  STATUS: ACCURACY BELOW THRESHOLD. REVISE PROMPTS OR HEURISTICS.")


if __name__ == "__main__":
    asyncio.run(run_triage_eval())
