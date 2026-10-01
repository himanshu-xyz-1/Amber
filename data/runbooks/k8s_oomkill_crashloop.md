# Runbook: Kubernetes Pod CrashLoopBackOff & OOMKilled Remediation

**Category:** Kubernetes / Compute  
**Severity Tier:** P1  
**Target Services:** `api-gateway`, `checkout-svc`, `inventory-worker`  

---

## 1. Incident Overview
Microservice container exits repeatedly with Exit Code 137 (SIGKILL issued by Linux Out-Of-Memory killer) or unhandled runtime panic, leading to Kubernetes entering `CrashLoopBackOff` backoff cycle.

## 2. Diagnostic Investigation
1. Execute `fetch_pod_logs` with `tail_lines=100` and automatic secret/PII redaction.
2. Inspect if container exceeded memory cgroup limits (`limits.memory`).
3. Check deployment commit timestamp to determine if a recent deployment occurred within 30 minutes.

## 3. Safe Remediation Protocol
- **Action A (Recent Deployment):** Propose `rollback_deployment` to previous stable container image revision.
- **Action B (Single Pod Leak):** Propose `restart_service_pod` to flush memory leaks while triggering autoscaling.
- **Safety Bounds:**
  - Deployment rollback requires target image existence verification.
  - Pod restart throttled to max 1 restart per 30 minutes to prevent restart storm cascades.
  - Require SHA-256 cryptographic human approval token.
