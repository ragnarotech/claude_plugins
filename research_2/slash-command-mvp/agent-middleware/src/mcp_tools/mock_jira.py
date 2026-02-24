"""
Mock Jira MCP tools implemented as in-process Python functions.

# DECISION: Mock MCP tools are implemented as in-process Python functions for MVP.
# Why: Avoids running separate MCP server processes, simpler local dev and testing.
#   No subprocess management, no stdio/SSE transport setup, no port conflicts.
# Production: Separate MCP server processes with stdio or SSE transport,
#   registered via mcp.json configuration. Real Jira API calls via the Jira REST API v3.
#   Authentication via OAuth 2.0 or API token (from K8s Secret).
# Standard: MCP tools protocol (model-controlled invocation).
#   See: https://modelcontextprotocol.io/docs/concepts/tools
# Alternative: Considered subprocess MCP servers but adds too much operational complexity
#   for MVP -- process lifecycle management, health checks, restart logic.

# MCP_MAPPING: Each function here corresponds to one MCP tool definition.
#   name         → tool["name"] in the Anthropic API tools list
#   docstring    → tool["description"]
#   parameters   → tool["input_schema"]["properties"]
#   return dict  → tool_result content (serialised to JSON in the agentic loop)
"""

MOCK_TICKETS = {
    "PROJ-1234": {
        "id": "PROJ-1234",
        "title": "Fix authentication timeout in API gateway",
        "description": (
            "Users are being logged out unexpectedly after 15 minutes. "
            "The JWT token expiry is set correctly but the refresh token flow seems broken."
        ),
        "priority": "High",
        "status": "In Progress",
        "assignee": "alice@company.com",
        "reporter": "bob@company.com",
        "components": ["api-gateway", "auth-service"],
        "created": "2026-02-20T09:00:00Z",
        "updated": "2026-02-22T14:30:00Z",
        "labels": ["bug", "auth", "critical-path"],
    },
    "PROJ-5678": {
        "id": "PROJ-5678",
        "title": "Add rate limiting to public API endpoints",
        "description": (
            "We need to implement rate limiting on our public REST API to prevent abuse. "
            "Target: 100 req/min per IP for unauthenticated, 1000/min for authenticated."
        ),
        "priority": "Medium",
        "status": "To Do",
        "assignee": None,
        "reporter": "charlie@company.com",
        "components": ["api-gateway"],
        "created": "2026-02-21T10:00:00Z",
        "updated": "2026-02-21T10:00:00Z",
        "labels": ["enhancement", "api", "security"],
    },
    "PROJ-9999": {
        "id": "PROJ-9999",
        "title": "Upgrade Kubernetes cluster to 1.30",
        "description": "Current cluster is on 1.28, need to upgrade to 1.30 before EOL.",
        "priority": "Low",
        "status": "Backlog",
        "assignee": "david@company.com",
        "reporter": "alice@company.com",
        "components": ["infrastructure"],
        "created": "2026-02-15T08:00:00Z",
        "updated": "2026-02-15T08:00:00Z",
        "labels": ["maintenance", "k8s"],
    },
}

# Tickets assigned to the current mock user
MOCK_USER_TICKETS = ["PROJ-1234", "PROJ-5678"]


def jira_get_ticket(ticket_number: str) -> dict:
    """Fetch Jira ticket details. Returns ticket data or error."""
    ticket = MOCK_TICKETS.get(ticket_number.upper())
    if not ticket:
        return {
            "error": f"Ticket {ticket_number} not found",
            "available": list(MOCK_TICKETS.keys()),
        }
    return ticket


def jira_update_ticket(ticket_number: str, fields: dict) -> dict:
    """Update Jira ticket fields. Returns updated ticket acknowledgement."""
    ticket = MOCK_TICKETS.get(ticket_number.upper())
    if not ticket:
        return {"error": f"Ticket {ticket_number} not found"}
    # In mock: acknowledge the update without mutating MOCK_TICKETS (stateless for MVP).
    # Production: PATCH /rest/api/3/issue/{issueIdOrKey} with OAuth token.
    updated_fields = list(fields.keys())
    return {
        "success": True,
        "ticket_id": ticket_number,
        "updated_fields": updated_fields,
        "message": f"Successfully updated {ticket_number}: {', '.join(updated_fields)}",
    }


def jira_list_tickets(assignee: str | None = None) -> dict:
    """List tickets. If assignee provided, filter by assignee."""
    # DECISION: For MVP, always return MOCK_USER_TICKETS regardless of assignee param.
    # Production: JQL query: assignee = currentUser() AND resolution = Unresolved
    tickets = []
    for ticket_id in MOCK_USER_TICKETS:
        ticket = MOCK_TICKETS.get(ticket_id)
        if ticket:
            tickets.append(
                {
                    "id": ticket["id"],
                    "title": ticket["title"],
                    "priority": ticket["priority"],
                    "status": ticket["status"],
                }
            )
    return {"tickets": tickets, "total": len(tickets)}
