from datetime import datetime
from .state import AmberGraphState

async def investigation_node(state: AmberGraphState) -> dict:
    """
    Investigation node for running read-only diagnostic tools.
    """
    severity = state.get("severity", "P4")
    
    # Mock diagnostic tool execution
    diagnostic_results = [
        {
            "tool_name": "check_service_health",
            "result": "Service is experiencing high latency.",
            "timestamp": datetime.utcnow().isoformat()
        },
        {
            "tool_name": "query_db_metrics",
            "result": "Connection pool saturated.",
            "timestamp": datetime.utcnow().isoformat()
        }
    ]
    
    # TODO: Integrate real LLM reasoning chain to analyze results and propose remediation
    root_cause_summary = "High latency likely caused by saturated DB connection pool."
    
    proposed_tools = []
    if severity in ["P0", "P1"]:
        proposed_tools.append({
            "tool_name": "restart_service",
            "args": {"service": state.get("affected_service", "unknown")},
            "risk_level": "HIGH",
            "reversible": False
        })
    else:
        proposed_tools.append({
            "tool_name": "clear_cache",
            "args": {"service": state.get("affected_service", "unknown")},
            "risk_level": "LOW",
            "reversible": True
        })
        
    remediation_plan = f"Execute {proposed_tools[0]['tool_name']} to alleviate issues."
    
    return {
        "diagnostic_results": diagnostic_results,
        "root_cause_summary": root_cause_summary,
        "proposed_tools": proposed_tools,
        "remediation_plan": remediation_plan,
        "current_node": "investigation"
    }
