import time
from typing import Dict, Any
from .state import AmberGraphState

async def triage_node(state: AmberGraphState) -> dict:
    """
    Triage node for incident severity classification.
    Runs in <3 seconds.
    """
    start_time = time.time()
    alert_payload = state.get("alert_payload", {})
    description = alert_payload.get("description", "").lower()
    title = alert_payload.get("title", "").lower()
    
    combined_text = f"{title} {description}"
    
    # Mock logic for determining severity based on keywords
    severity = "P4"
    if any(kw in combined_text for kw in ["critical", "connection pool", "crash", "oom"]):
        severity = "P0"
    elif any(kw in combined_text for kw in ["error", "timeout", "degraded"]):
        severity = "P2"
        
    # TODO: Integrate real LLM call (Claude 3.5 Sonnet / GPT-4o-mini) here for precise triage reasoning
    
    elapsed_time = time.time() - start_time
    
    return {
        "severity": severity,
        "triage_reasoning": f"Rule-based mock match completed in {elapsed_time:.3f}s. Contains keywords for {severity}.",
        "affected_service": alert_payload.get("service", "unknown"),
        "current_node": "triage"
    }
