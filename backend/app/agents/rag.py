from .state import AmberGraphState

async def rag_node(state: AmberGraphState) -> dict:
    """
    RAG node for retrieving relevant runbooks based on severity and alert info.
    """
    severity = state.get("severity", "P4")
    affected_service = state.get("affected_service", "unknown")
    
    # Mock search logic
    matched_runbooks = []
    if severity in ["P0", "P1"]:
        matched_runbooks.append({
            "title": f"Incident Response for {affected_service} Outage",
            "content_snippet": "Immediate escalation required. Check metrics and restart failing pods.",
            "confidence": 0.95
        })
    else:
        matched_runbooks.append({
            "title": f"Troubleshooting {affected_service}",
            "content_snippet": "Review logs for warnings. Monitor system load.",
            "confidence": 0.75
        })
        
    # TODO: Integrate real pgvector + BM25 hybrid search here
    
    return {
        "matched_runbooks": matched_runbooks,
        "runbook_instructions": "Follow runbook steps carefully.",
        "current_node": "rag"
    }
