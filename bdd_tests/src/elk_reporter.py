"""
Custom Elasticsearch reporter for DeepEval metrics.

Extends pytest-elk-reporter to include DeepEval metric scores in test results.
"""
import os
import json
from datetime import datetime
from typing import Any

from elasticsearch import Elasticsearch


class DeepEvalResultReporter:
    """
    Reports test results with DeepEval metrics to Elasticsearch.

    Complements pytest-elk-reporter by adding structured metric data.
    """

    def __init__(
        self,
        es_host: str | None = None,
        es_index: str = "bdd-test-results",
        es_username: str | None = None,
        es_password: str | None = None,
    ):
        """
        Initialize reporter.

        Args:
            es_host: Elasticsearch host (from ES_HOST env if not provided)
            es_index: Index name for test results
            es_username: Optional username for authentication
            es_password: Optional password for authentication
        """
        self.es_host = es_host or os.environ.get("ES_HOST", "localhost:9200")
        self.es_index = es_index
        self.es_username = es_username or os.environ.get("ES_USERNAME")
        self.es_password = es_password or os.environ.get("ES_PASSWORD")
        self._client = None

    @property
    def client(self) -> Elasticsearch:
        """Lazy-load Elasticsearch client."""
        if self._client is None:
            auth = None
            if self.es_username and self.es_password:
                auth = (self.es_username, self.es_password)

            self._client = Elasticsearch(
                [f"http://{self.es_host}"],
                basic_auth=auth,
            )
        return self._client

    def ensure_index_exists(self):
        """Create index with proper mapping if it doesn't exist."""
        if not self.client.indices.exists(index=self.es_index):
            mapping = {
                "mappings": {
                    "properties": {
                        "@timestamp": {"type": "date"},
                        "test_id": {"type": "keyword"},
                        "test_name": {"type": "keyword"},
                        "feature": {"type": "keyword"},
                        "scenario": {"type": "keyword"},
                        "outcome": {"type": "keyword"},
                        "duration_seconds": {"type": "float"},
                        "error_message": {"type": "text"},

                        # DeepEval metrics
                        "metrics": {
                            "type": "object",
                            "properties": {
                                "relevancy_score": {"type": "float"},
                                "faithfulness_score": {"type": "float"},
                                "mcp_use_score": {"type": "float"},
                                "custom_criteria_score": {"type": "float"},
                            }
                        },

                        # MCP tool tracking
                        "tools_called": {"type": "keyword"},
                        "tool_call_count": {"type": "integer"},

                        # Test metadata
                        "mock_date": {"type": "keyword"},
                        "user_prompt": {"type": "text"},
                        "agent_response": {"type": "text"},

                        # Execution context
                        "environment": {"type": "keyword"},
                        "git_commit": {"type": "keyword"},
                        "branch": {"type": "keyword"},
                    }
                }
            }
            self.client.indices.create(index=self.es_index, body=mapping)

    def report_test_result(
        self,
        test_id: str,
        test_name: str,
        outcome: str,
        duration: float,
        metrics: dict[str, float] | None = None,
        tool_calls: list[str] | None = None,
        test_context: dict[str, Any] | None = None,
        error_message: str | None = None,
    ):
        """
        Report a single test result to Elasticsearch.

        Args:
            test_id: Unique test identifier
            test_name: Human-readable test name
            outcome: Test outcome (passed, failed, skipped)
            duration: Test duration in seconds
            metrics: DeepEval metric scores
            tool_calls: List of MCP tools called
            test_context: Additional test context
            error_message: Error message if test failed
        """
        self.ensure_index_exists()

        context = test_context or {}

        doc = {
            "@timestamp": datetime.utcnow().isoformat(),
            "test_id": test_id,
            "test_name": test_name,
            "outcome": outcome,
            "duration_seconds": duration,
            "error_message": error_message,

            "metrics": metrics or {},
            "tools_called": tool_calls or [],
            "tool_call_count": len(tool_calls) if tool_calls else 0,

            "mock_date": context.get("mock_date"),
            "user_prompt": context.get("user_prompt"),
            "agent_response": context.get("agent_response", {}).get("output") if context.get("agent_response") else None,

            "environment": os.environ.get("TEST_ENV", "local"),
            "git_commit": os.environ.get("GIT_COMMIT"),
            "branch": os.environ.get("GIT_BRANCH"),
        }

        self.client.index(index=self.es_index, document=doc)

    def report_batch(self, results: list[dict[str, Any]]):
        """Report multiple test results in a single batch."""
        self.ensure_index_exists()

        actions = []
        for result in results:
            actions.append({"index": {"_index": self.es_index}})
            actions.append(result)

        if actions:
            self.client.bulk(body=actions)
