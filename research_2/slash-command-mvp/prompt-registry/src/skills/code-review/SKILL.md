---
name: code-review
description: Review code changes for quality, security, and best practices
tools:
  - git_list_commits
  - jira_get_ticket
tags:
  - development
  - quality
---

# Code Review Skill

When asked to review code, follow these steps:

1. Use the `git_list_commits` tool to fetch recent changes
2. Analyze the diff for:
   - Security vulnerabilities (injection attacks, exposed secrets, insecure dependencies)
   - Performance issues (N+1 queries, unnecessary loops, missing indexes)
   - Code style violations (naming, formatting, complexity)
   - Missing tests or insufficient coverage
3. If a ticket number is mentioned, use `jira_get_ticket` to understand requirements
4. Provide a structured review with:
   - **Summary**: Overall assessment (Approved/Changes Requested/Blocked)
   - **Issues**: Each issue with severity (Critical/High/Medium/Low), file, line, and suggestion
   - **Positive Feedback**: What was done well
   - **Questions**: Any clarifications needed before approval
