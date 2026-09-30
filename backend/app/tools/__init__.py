from backend.app.tools.base import tool_registry

# Import to trigger registration
import backend.app.tools.diagnostics
import backend.app.tools.remediation

__all__ = ["tool_registry"]
