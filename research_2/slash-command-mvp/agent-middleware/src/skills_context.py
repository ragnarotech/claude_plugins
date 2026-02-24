"""
Skills context manager: maintains the set of active skills and injects their
markdown content as system prompt addenda for the agent.

# DECISION: Skills injected as system prompt addenda.
# Why: Simplest approach -- the agent receives extra instructions without any
#   special handling needed on the agent side. Claude parses and follows
#   markdown-formatted instructions reliably.
# Production: Use dynamic system prompt composition based on conversation
#   context analysis (embedding similarity between the user message and each
#   skill's description vector). Prevents context window bloat from injecting
#   all skills regardless of relevance.
# Alternative: Considered a separate system message type for skills (rejected:
#   CopilotKit doesn't support this natively and Anthropic's /v1/messages API
#   has a single system parameter).

# DECISION: Module-level singleton for MVP.
# Why: Skills activation state is session-wide; all request handlers share it.
# Production: Per-conversation state stored in a session store (Redis) keyed
#   by conversation ID. The singleton approach would not scale to multi-user
#   concurrent sessions.
"""


class SkillsContextManager:
    """Tracks active skills and builds system prompt addenda for the agent."""

    def __init__(self):
        # name → raw SKILL.md content (from the registry)
        self._active_skills: dict[str, str] = {}
        # Metadata-only list (no skill_md) for autocomplete / listing
        self._available_skills: list[dict] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def set_available_skills(self, skills: list[dict]):
        """Populate the list of available skills (called at startup)."""
        self._available_skills = skills

    def activate_skill(self, name: str, skill_md: str):
        """Activate a skill, adding its markdown content to the context.

        Idempotent: re-activating an already-active skill replaces its content.
        """
        self._active_skills[name] = skill_md

    def deactivate_skill(self, name: str):
        """Deactivate a skill, removing it from the context.

        No-op if the skill is not currently active.
        """
        self._active_skills.pop(name, None)

    # ------------------------------------------------------------------
    # System prompt construction
    # ------------------------------------------------------------------

    def get_system_prompt_addendum(self) -> str:
        """Build the skills addendum appended to the agent's system prompt.

        Returns an empty string when no skills are active.

        # DECISION: Skills are injected verbatim as markdown sections.
        # Why: The prompt-registry stores SKILL.md files with structured
        #   markdown (frontmatter + headings). Claude reliably follows
        #   instructions expressed as markdown headings and bullet points.
        # Production: Truncate skill_md to a max token budget; summarise with
        #   a smaller/cheaper model if the full content would overflow the
        #   context window.
        """
        if not self._active_skills:
            return ""

        parts = ["\n\n## Active Skills\n\nThe following skills are currently active:\n"]
        for name, skill_md in self._active_skills.items():
            parts.append(f"### Skill: {name}\n\n{skill_md}\n")
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Auto-discovery
    # ------------------------------------------------------------------

    def find_matching_skills(self, message: str) -> list[str]:
        """Return skill names whose keywords appear in the message.

        # DECISION: Keyword heuristic for skill auto-discovery (MVP).
        # Why: Simplest approach; no external dependencies, zero latency.
        # Production: Use embedding similarity -- compute cosine distance between
        #   the message embedding and each skill description embedding
        #   (pre-computed and cached at startup). Threshold at ~0.75 cosine sim.
        # Alternative: Regex matching per skill (too brittle, hard to maintain);
        #   always injecting all skills (too much context consumption; risks
        #   confusing the model with irrelevant instructions).
        """
        keywords_to_skill: dict[str, str] = {
            "review": "code-review",
            "pr": "code-review",
            "pull request": "code-review",
            "incident": "incident-response",
            "outage": "incident-response",
            "p1": "incident-response",
            "p2": "incident-response",
            "on-call": "incident-response",
        }
        matched: set[str] = set()
        message_lower = message.lower()
        for keyword, skill_name in keywords_to_skill.items():
            if keyword in message_lower:
                matched.add(skill_name)
        return list(matched)


# Module-level singleton.
skills_context = SkillsContextManager()
