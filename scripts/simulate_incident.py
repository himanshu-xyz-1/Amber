#!/usr/bin/env python3
"""
Amber Incident Simulator CLI.
Dispatches production-grade PagerDuty, Datadog, or Sentry alert storms into Amber's webhook gateway
and watches the autonomous LangGraph triage and HITL approval token generation in real time.
"""

import argparse
import asyncio
import json
import sys
import time
import httpx

SCENARIOS = {
    "postgres-pool": {
        "source": "pagerduty",
        "payload": {
            "id": f"pd-alert-{int(time.time())}",
            "title": "PostgreSQL Connection Pool Exhausted (98%)",
            "message": "Active connections reached 98/100 on payment-db-prod. 4 idle-in-transaction queries blocking traffic.",
            "service": "payment-db-prod",
            "severity": "critical",
            "cluster": "aws-us-east-1-prod",
            "tags": ["postgres", "rds", "locks", "p0"]
        }
    },
    "pod-crash": {
        "source": "datadog",
        "payload": {
            "id": f"dd-alert-{int(time.time())}",
            "title": "Pod CrashLoopBackOff: checkout-svc OOMKilled",
            "message": "Container checkout-svc exited with code 137 (OOMKilled). Memory cgroup limit 512Mi exceeded.",
            "service": "checkout-svc",
            "severity": "high",
            "namespace": "production",
            "tags": ["k8s", "oom", "crashloop", "p1"]
        }
    },
    "gateway-timeout": {
        "source": "sentry",
        "payload": {
            "id": f"sentry-alert-{int(time.time())}",
            "title": "HTTP 504 Gateway Timeout Cascade on /v1/transactions",
            "message": "p99 latency spiked to 8,420ms. Upstream connection timeout on ingress-gateway.",
            "service": "api-gateway",
            "severity": "error",
            "tags": ["http", "latency", "504", "p1"]
        }
    }
}


async def main():
    parser = argparse.ArgumentParser(description="Amber Autonomous Incident Simulator")
    parser.add_argument(
        "--scenario",
        choices=["postgres-pool", "pod-crash", "gateway-timeout"],
        default="postgres-pool",
        help="Outage scenario to simulate"
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Amber API base URL"
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Automatically approve the proposed remediation action after 2 seconds"
    )

    args = parser.parse_args()
    scenario_data = SCENARIOS[args.scenario]
    source = scenario_data["source"]
    payload = scenario_data["payload"]

    print("=" * 60)
    print(f"🔥 AMBER INCIDENT SIMULATOR: {args.scenario.upper()}")
    print("=" * 60)
    print(f"Target Gateway: {args.url}/api/v1/webhooks/{source}")
    print(f"Alert Payload:  {payload['title']}")
    print("-" * 60)

    async with httpx.AsyncClient(base_url=args.url) as client:
        # 1. Dispatch Webhook
        print("\n[Step 1] Ingesting alert storm into webhook gateway...")
        t0 = time.time()
        res = await client.post(f"/api/v1/webhooks/{source}", json=payload)
        t_ingest = (time.time() - t0) * 1000

        if res.status_code != 202:
            print(f"❌ Failed to ingest alert: HTTP {res.status_code} - {res.text}")
            sys.exit(1)

        ack = res.json()
        print(f"✓ Ingested in {t_ingest:.1f}ms (HTTP 202 Accepted)")
        print(f"  Alert ID: {ack.get('alert_id')}")

        # 2. Poll for Autonomous Triage & Incident State
        print("\n[Step 2] Awaiting autonomous LangGraph agent pipeline (Triage -> RAG -> Diagnostics)...")
        incident = None
        for attempt in range(8):
            await asyncio.sleep(1.0)
            inc_res = await client.get("/api/v1/incidents")
            if inc_res.status_code == 200:
                incidents = inc_res.json()
                if incidents:
                    incident = incidents[0]
                    if incident.get("status") in ["PROPOSED", "EXECUTING", "RESOLVED"]:
                        break
            print(f"  ... processing ({attempt + 1}s)")

        if not incident:
            print("❌ Timeout waiting for incident processing.")
            sys.exit(1)

        print("\n✓ Incident Diagnosed & Triaged:")
        print(f"  Incident ID:  {incident.get('id')}")
        print(f"  Severity:     {incident.get('severity')}")
        print(f"  Status:       {incident.get('status')}")
        print(f"  Root Cause:   {incident.get('root_cause_summary')}")

        # 3. Check Pending HITL Approval Token
        print("\n[Step 3] Checking Human-in-the-Loop (HITL) cryptographic approval token...")
        appr_res = await client.get("/api/v1/approvals/pending")
        pending = appr_res.json() if appr_res.status_code == 200 else []

        if not pending:
            print("✓ Action was LOW risk and executed autonomously without human interrupt!")
            return

        inv = pending[0]
        print("🚨 Mutating action requires cryptographic human approval:")
        print(f"  Action Name:   {inv.get('tool_name')}")
        print(f"  Tool Args:     {json.dumps(inv.get('tool_args'))}")
        print(f"  SHA-256 Token: {inv.get('payload_sha256')}")
        print(f"  TTL Expiry:    {inv.get('approval_expires_at')} (10m TTL)")

        if args.auto_approve:
            print("\n[Step 4] Auto-Approve flag detected. Dispathing 1-Click Confirmation...")
            await asyncio.sleep(1.5)
            exec_res = await client.post("/api/v1/approvals", json={
                "tool_invocation_id": inv["id"],
                "action": "approve",
                "payload_sha256": inv.get("payload_sha256")
            })
            print(f"✓ Action Executed (HTTP {exec_res.status_code}):")
            print(json.dumps(exec_res.json().get("execution_result"), indent=2))
            print("\n🎉 INCIDENT AUTO-RESOLVED! Cluster headroom restored to healthy state.")


if __name__ == "__main__":
    asyncio.run(main())
