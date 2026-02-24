---
name: incident-response
description: Triage and respond to production incidents with structured runbooks
tools:
  - jira_get_ticket
  - jira_update_ticket
tags:
  - operations
  - incidents
  - on-call
---

# Incident Response Skill

When triaging a production incident:

1. **Assess Severity**: Determine P1/P2/P3/P4 based on:
   - User impact (how many affected)
   - Revenue impact
   - Data integrity risk
   - Service availability

2. **Gather Context**:
   - If a ticket number is provided, use `jira_get_ticket` for details
   - Ask for: error messages, affected services, when it started, recent deployments

3. **Immediate Actions**:
   - P1/P2: Recommend immediate escalation steps
   - Suggest rollback if recent deployment is suspected
   - Identify mitigation vs. root cause fix

4. **Documentation**:
   - Use `jira_update_ticket` to update the incident ticket with your analysis
   - Include: timeline, impact assessment, immediate steps, and next actions

5. **Communication Template**:
   Provide a stakeholder update in this format:
   - Status: [Investigating/Identified/Mitigated/Resolved]
   - Impact: [What is affected]
   - Actions: [What is being done]
   - ETA: [Expected resolution time]
