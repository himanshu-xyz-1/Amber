import pytest
from backend.app.tools.base import tool_registry, RiskLevel
from backend.app.tools.diagnostics import QueryDatabaseMetrics, CheckServiceHealth
from backend.app.tools.remediation import KillDatabaseConnections, RollbackDeployment


def test_tool_registry_registration():
    tools = tool_registry.list_tools()
    assert len(tools) >= 6
    names = [t["name"] for t in tools]
    assert "query_db_metrics" in names
    assert "kill_db_connections" in names
    assert "rollback_deployment" in names


def test_kill_db_connections_safety_guardrails():
    kill_tool = tool_registry.get("kill_db_connections")
    assert kill_tool is not None
    assert kill_tool.risk_level == RiskLevel.HIGH

    # Disallow empty list
    assert not kill_tool.validate_args(pids=[])
    # Disallow PID <= 1
    assert not kill_tool.validate_args(pids=[1])
    assert not kill_tool.validate_args(pids=[0])
    assert not kill_tool.validate_args(pids=[-42])
    # Disallow excessive batch size (> 5)
    assert not kill_tool.validate_args(pids=[10, 11, 12, 13, 14, 15])
    # Allow safe valid batch
    assert kill_tool.validate_args(pids=[412, 415, 419])


@pytest.mark.asyncio
async def test_diagnostics_execution():
    db_tool = tool_registry.get("query_db_metrics")
    assert db_tool is not None
    res = await db_tool.execute(threshold_seconds=60)
    assert res.success is True
    assert "pool_utilization_pct" in res.data
    assert "slow_queries" in res.data
