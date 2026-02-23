"""
Mock LLM client for testing without actual API calls.

This module provides a mock LLM that generates deterministic responses
based on input patterns, allowing tests to run without API keys or costs.
"""
import re
from typing import Optional


class MockLLMClient:
    """
    Mock LLM client that simulates LLM responses for testing.

    This client generates responses based on pattern matching and predefined
    templates, allowing BDD tests to run without real API calls.
    """

    def __init__(self, model: str = "gpt-3.5-turbo"):
        """
        Initialize mock LLM client.

        Args:
            model: Model name (for compatibility, not used in mock)
        """
        self.model = model
        self.response_map = self._build_response_map()

    def _build_response_map(self):
        """
        Build a map of query patterns to mock responses.

        Returns:
            Dictionary mapping regex patterns to response templates
        """
        return {
            # Customer support queries
            r"refund|return.*policy": (
                "We offer a 30-day money-back guarantee. Refunds are processed "
                "within 5-7 business days if items are returned in original condition."
            ),
            r"track.*order|order.*track": (
                "You can track your order by logging into the customer portal with "
                "your email and checking the Orders section."
            ),
            r"color|colour": (
                "This product is currently available in black and white."
            ),
            r"shipping|delivery.*time": (
                "Standard shipping takes 5-7 business days. We also offer express "
                "shipping (2-3 days) and international shipping (10-15 days)."
            ),
            r"business.*hours|hours.*operation": (
                "Our customer support is available Monday through Friday, 9 AM to 6 PM EST."
            ),

            # Technical support
            r"won't.*turn on|not.*working|broken": (
                "First, charge the device for 30 minutes. Then try a hard reset by "
                "holding the power button for 10 seconds. If it still won't turn on, "
                "contact our technical support team."
            ),

            # Intent classification
            r"return.*item|how.*return": "return_procedures",
            r"track": "order_tracking",
            r"talk.*human|speak.*agent": "agent_escalation",

            # Technical queries
            r"oauth|authentication": (
                "OAuth 2.0 is an authorization framework that enables applications to "
                "obtain limited access to user accounts through token-based authentication."
            ),

            # Sales queries
            r"pricing|plans|cost": (
                "We offer three pricing plans: Basic ($9/month), Professional ($29/month), "
                "and Enterprise (custom pricing). All plans include a 14-day free trial."
            ),

            # General
            r"company|about": (
                "We are a technology company focused on providing innovative solutions "
                "for businesses and consumers worldwide."
            ),

            # Quantum computing example
            r"quantum.*comput": (
                "Quantum computing is like having a super-powerful calculator that can "
                "try many solutions at once, similar to checking multiple paths through "
                "a maze simultaneously."
            ),

            # Package damage
            r"package.*damaged|damaged.*package": (
                "I'm sorry about the damaged package. Can you share your order number and "
                "damage photos? We'll send a replacement or issue a refund right away."
            ),

            # Job application
            r"apply.*position|who.*apply": (
                "This position is open to all qualified candidates regardless of background."
            ),

            # Cancel subscription
            r"cancel.*subscription": (
                "I can help you cancel your subscription. Please confirm your account email, "
                "and I'll process the cancellation immediately."
            ),

            # Adversarial prompts - safe responses
            r"ignore.*instruction|reveal.*secret|system.*prompt": (
                "I'm here to help with customer support questions. How can I assist you today?"
            ),
            r"offensive|inappropriate": (
                "I'm here to provide helpful and respectful assistance. How can I help you?"
            ),
        }

    def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate a mock response based on the input prompt.

        Args:
            prompt: Input prompt/query
            **kwargs: Additional parameters (ignored in mock)

        Returns:
            Generated response string
        """
        prompt_lower = prompt.lower()

        # Check each pattern in the response map
        for pattern, response in self.response_map.items():
            if re.search(pattern, prompt_lower):
                return response

        # Default response if no pattern matches
        return (
            f"I understand you're asking about '{prompt}'. "
            "Let me help you with that. [Mock response]"
        )

    def generate_with_context(
        self,
        prompt: str,
        context: list[str],
        **kwargs
    ) -> str:
        """
        Generate response with retrieval context (for RAG testing).

        Args:
            prompt: Input query
            context: List of retrieved context documents
            **kwargs: Additional parameters

        Returns:
            Generated response based on prompt and context
        """
        # For mock, we just use the base generate method
        # In real implementation, this would use the context
        base_response = self.generate(prompt)

        # Add a note if context is provided
        if context:
            return base_response
        else:
            return base_response + " (Note: Generated without context)"

    def __call__(self, prompt: str, **kwargs) -> str:
        """Allow client to be called directly."""
        return self.generate(prompt, **kwargs)


class MockLLMAPIClient:
    """
    Mock client that mimics OpenAI API structure.

    This can be used as a drop-in replacement for OpenAI client in tests.
    """

    def __init__(self, api_key: Optional[str] = None):
        """Initialize with optional API key (ignored in mock)."""
        self.api_key = api_key or "mock-api-key"
        self._client = MockLLMClient()

    class ChatCompletion:
        """Mock chat completion nested class."""

        def __init__(self, client):
            self.client = client

        def create(self, messages: list, model: str = "gpt-3.5-turbo", **kwargs):
            """Mock chat completion create method."""
            # Extract last user message
            user_message = next(
                (m["content"] for m in reversed(messages) if m["role"] == "user"),
                ""
            )

            response_text = self.client.generate(user_message)

            # Return mock response in OpenAI format
            return type('Response', (), {
                'choices': [
                    type('Choice', (), {
                        'message': type('Message', (), {
                            'content': response_text,
                            'role': 'assistant'
                        })(),
                        'finish_reason': 'stop'
                    })()
                ],
                'model': model,
                'usage': type('Usage', (), {
                    'prompt_tokens': len(user_message.split()),
                    'completion_tokens': len(response_text.split()),
                    'total_tokens': len(user_message.split()) + len(response_text.split())
                })()
            })()

    @property
    def chat(self):
        """Return chat completion interface."""
        return type('Chat', (), {
            'completions': self.ChatCompletion(self._client)
        })()


# Convenience function for creating mock clients
def get_mock_client(client_type: str = "simple") -> MockLLMClient | MockLLMAPIClient:
    """
    Get a mock LLM client.

    Args:
        client_type: Type of client - "simple" or "api"

    Returns:
        Mock LLM client instance
    """
    if client_type == "api":
        return MockLLMAPIClient()
    return MockLLMClient()
