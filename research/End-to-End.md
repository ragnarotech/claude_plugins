# End-to-end testing for AI agents in Kubernetes: a comprehensive architecture guide

Running pytest-based end-to-end tests for AI agents inside Kubernetes requires orchestrating multiple complex systems—from test execution infrastructure to compliance-friendly data storage to LLM evaluation frameworks. **The most effective architecture combines Kubernetes Jobs for test execution, DVC for external test data versioning, DeepEval for AI accuracy assessment, and pytest-elk-reporter for results streaming to Elasticsearch.** This approach delivers CI/CD-triggered tests with clear pass/fail signals while keeping sensitive test data outside source control and providing rich observability through Kibana dashboards.

---

## Kubernetes Job patterns form the foundation of in-cluster test execution

The Kubernetes Job resource provides the core primitive for running pytest test suites inside a cluster. A well-designed test Job incorporates **timeout protection, automatic cleanup, resource limits, and proper restart policies**—all essential for reliable CI/CD integration.

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: pytest-integration-tests
  labels:
    test-type: integration
spec:
  backoffLimit: 2                    # Retry failed tests up to 2 times
  activeDeadlineSeconds: 1800        # 30-minute hard timeout
  ttlSecondsAfterFinished: 3600      # Auto-cleanup after 1 hour
  template:
    spec:
      restartPolicy: Never           # Required for test Jobs
      serviceAccountName: test-runner-sa
      containers:
      - name: pytest-runner
        image: your-registry/pytest-tests:v1.2.3
        command: ["pytest"]
        args:
          - "-v"
          - "--timeout=300"          # Per-test timeout
          - "--junitxml=/results/report.xml"
          - "tests/"
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
```

**Critical configuration parameters** that prevent common failures include `restartPolicy: Never` (Jobs require this—using `Always` causes infinite restart loops), `activeDeadlineSeconds` for overall Job timeout, and `ttlSecondsAfterFinished` for automatic garbage collection. The `backoffLimit` should typically be **0 or 1 for test Jobs**—retrying flaky AI tests rarely helps and wastes resources.

For tests requiring database dependencies, Kubernetes 1.28+ introduced **native sidecar containers** that elegantly solve the lifecycle problem:

```yaml
spec:
  initContainers:
  - name: postgres
    image: postgres:15
    restartPolicy: Always    # Makes this a sidecar that runs alongside main container
    env:
    - name: POSTGRES_PASSWORD
      value: "testpassword"
    readinessProbe:
      exec:
        command: ["pg_isready", "-U", "postgres"]
      initialDelaySeconds: 5
      periodSeconds: 5
  containers:
  - name: pytest
    image: tests:latest
    command: ["pytest", "-v", "tests/integration/"]
```

---

## CI/CD integration requires careful handling of Job lifecycle events

The fundamental challenge in CI/CD integration is **waiting for a Kubernetes Job to reach either completion or failure state**—`kubectl wait` only supports waiting for a single condition. The solution uses parallel wait processes:

```yaml
# GitHub Actions workflow
name: Integration Tests
on: [push, pull_request]

jobs:
  k8s-test:
    runs-on: ubuntu-latest
    timeout-minutes: 60
    steps:
      - uses: actions/checkout@v4
      
      - name: Configure kubectl
        run: echo "${{ secrets.KUBECONFIG }}" | base64 -d > $HOME/.kube/config
        
      - name: Run Test Job
        run: |
          kubectl delete job test-job --ignore-not-found
          kubectl apply -f test-job.yaml
          
          # Wait for pod to be ready
          kubectl wait --for=condition=ready \
            $(kubectl get pod -l job-name=test-job -o name) \
            --timeout=120s
          
          # Stream logs in real-time
          kubectl logs -f job/test-job &
          
          # Wait for EITHER complete OR failed
          kubectl wait --for=condition=complete job/test-job --timeout=1800s &
          completion_pid=$!
          kubectl wait --for=condition=failed job/test-job --timeout=1800s && exit 1 &
          failure_pid=$!
          
          wait -n $completion_pid $failure_pid
```

For the daily CronJob fallback requirement, configure a scheduled test execution:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: daily-ai-tests
spec:
  schedule: "0 3 * * *"              # Daily at 3 AM UTC
  concurrencyPolicy: Forbid          # Prevent overlapping runs
  successfulJobsHistoryLimit: 5
  failedJobsHistoryLimit: 10
  jobTemplate:
    spec:
      activeDeadlineSeconds: 3600    # 1 hour timeout
      template:
        spec:
          restartPolicy: Never
          containers:
          - name: test-runner
            image: myregistry/ai-tests:latest
            command: ["pytest", "tests/", "-v"]
```

The **kubectl wait-job krew plugin** provides a cleaner alternative that handles both conditions automatically and returns appropriate exit codes, eliminating the parallel-wait workaround.

---

## S3-backed test fixtures keep sensitive data outside source control

For compliance requirements mandating test data externalization, **a combination of DVC for versioning and custom pytest fixtures for runtime loading** provides the most robust solution. The pattern separates version tracking (Git-stored `.dvc` metafiles) from actual data storage (S3).

```python
# conftest.py - S3 test fixture loading
import os
import json
import pytest
import boto3
from functools import lru_cache

TEST_DATA_BUCKET = os.environ.get("TEST_DATA_BUCKET", "test-fixtures")

@pytest.fixture(scope="session")
def s3_client():
    """Session-scoped S3 client for test data access."""
    return boto3.client(
        "s3",
        region_name=os.environ.get("AWS_REGION", "us-east-1")
    )

@pytest.fixture
def load_test_input(s3_client):
    """Factory fixture to load test inputs from S3."""
    @lru_cache(maxsize=100)  # Cache to avoid repeated downloads
    def _load(key: str):
        response = s3_client.get_object(Bucket=TEST_DATA_BUCKET, Key=key)
        content = response["Body"].read()
        return json.loads(content) if key.endswith(".json") else content
    return _load

@pytest.fixture
def load_expected_output(s3_client):
    """Factory fixture to load expected outputs from S3."""
    def _load(test_name: str, output_name: str = "expected.json"):
        key = f"expected_outputs/{test_name}/{output_name}"
        response = s3_client.get_object(Bucket=TEST_DATA_BUCKET, Key=key)
        return json.loads(response["Body"].read())
    return _load
```

**DVC setup** for version-controlled test data that stays synchronized with code:

```bash
# Initialize DVC and configure S3 remote
dvc init
dvc remote add -d testdata s3://company-test-data/dvc-cache
dvc remote modify testdata profile aws-test-profile

# Track test fixtures (creates .dvc pointer file for Git)
dvc add tests/fixtures/
git add tests/fixtures.dvc tests/.gitignore
git commit -m "Track test fixtures with DVC"

# Push data to S3
dvc push
```

This pattern ensures test data is **versioned alongside code commits**—`dvc checkout` after `git checkout` restores the exact test data for any historical commit.

---

## Elasticsearch reporting through pytest-elk-reporter enables rich dashboards

The **pytest-elk-reporter** plugin provides direct integration between pytest and Elasticsearch, streaming results as tests complete:

```ini
# pytest.ini
[pytest]
es_address = elasticsearch.monitoring:9200
es_user = pytest_reporter
es_password = ${ES_PASSWORD}
es_index_name = pytest-results
```

For richer reporting with custom metrics—essential for AI evaluation results—extend with custom hooks:

```python
# conftest.py - Custom Elasticsearch reporter with AI metrics
import datetime
from elasticsearch import Elasticsearch
import pytest

@pytest.fixture(scope="session", autouse=True)
def setup_elk_reporting(request):
    """Add custom session data to all test reports."""
    elk = request.config.pluginmanager.get_plugin("elk-reporter-runtime")
    if elk:
        elk.session_data.update({
            "environment": os.environ.get("TEST_ENV", "local"),
            "ai_model_version": os.environ.get("MODEL_VERSION"),
            "test_suite": "ai-agent-integration"
        })

def test_ai_response_quality(request, elk_reporter, ai_agent):
    """Test with custom metric reporting to Elasticsearch."""
    response = ai_agent.query("What is the capital of France?")
    
    # Add AI-specific metrics to this test's Elasticsearch document
    elk_reporter.append_test_data(request, {
        "response_latency_ms": response.latency * 1000,
        "token_count": response.tokens_used,
        "faithfulness_score": evaluate_faithfulness(response),
        "relevancy_score": evaluate_relevancy(response)
    })
    
    assert "Paris" in response.text
```

**Elasticsearch index mapping** optimized for pytest results with AI evaluation metrics:

```json
{
  "mappings": {
    "properties": {
      "@timestamp": { "type": "date" },
      "test_id": { "type": "keyword" },
      "outcome": { "type": "keyword" },
      "duration_seconds": { "type": "float" },
      "faithfulness_score": { "type": "float" },
      "relevancy_score": { "type": "float" },
      "response_latency_ms": { "type": "float" },
      "failure": {
        "type": "object",
        "properties": {
          "message": { "type": "text" },
          "exception_type": { "type": "keyword" }
        }
      }
    }
  }
}
```

Kibana visualizations for the public dashboard should include: **outcome pie chart** (pass/fail/skip distribution), **score trends over time** (line charts for faithfulness and relevancy), **latency percentiles**, and a **failed tests table** with failure messages.

---

## DeepEval provides comprehensive AI accuracy evaluation with native pytest integration

DeepEval stands out as the most complete LLM evaluation framework with native pytest support—it's effectively **"pytest for LLMs"** with 50+ research-backed metrics. The framework evaluates semantic correctness rather than exact string matching, essential for non-deterministic AI outputs.

```python
# test_ai_agent.py
import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase
from deepeval.metrics import (
    FaithfulnessMetric,
    AnswerRelevancyMetric,
    GEval
)

# Custom metric for domain-specific evaluation
correctness_metric = GEval(
    name="Correctness",
    criteria="Determine if the actual output correctly answers the question based on the expected output.",
    evaluation_params=["ACTUAL_OUTPUT", "EXPECTED_OUTPUT"],
    threshold=0.7,
    model="gpt-4o"
)

@pytest.fixture
def faithfulness_metric():
    return FaithfulnessMetric(
        threshold=0.7,
        model="gpt-4o",
        include_reason=True
    )

def test_ai_agent_response(ai_agent, load_test_input, load_expected_output, faithfulness_metric):
    """Test AI agent response with DeepEval metrics."""
    input_data = load_test_input("queries/customer_support_001.json")
    expected = load_expected_output("customer_support_001")
    
    # Call the AI agent
    response = ai_agent.query(input_data["query"])
    
    test_case = LLMTestCase(
        input=input_data["query"],
        actual_output=response.text,
        expected_output=expected["answer"],
        retrieval_context=response.sources  # For RAG faithfulness checking
    )
    
    assert_test(test_case, [faithfulness_metric, AnswerRelevancyMetric(threshold=0.7)])
```

**Key DeepEval metrics** for AI agent testing:
- **Faithfulness**: Detects hallucinations by checking if the response contradicts the retrieval context
- **Answer Relevancy**: Evaluates whether the response actually addresses the input query
- **Task Completion**: For agentic workflows, measures overall execution success
- **Tool Correctness**: Verifies proper tool selection and parameter passing

For handling non-deterministic outputs, DeepEval uses **LLM-as-judge evaluation** with semantic analysis rather than exact matching. Setting `threshold=0.7` provides reasonable tolerance for output variation while catching genuine quality issues. Running tests with `deepeval test run test_ai_agent.py` adds LLM-specific features like hyperparameter logging and cloud reporting.

---

## MCP server testing requires protocol-aware fixtures and mocking

Testing MCP (Model Context Protocol) servers requires understanding the protocol's client-server architecture with tools, resources, and prompts as core primitives. The **MCP Inspector** provides visual debugging, while **mcp-testing-kit** enables programmatic unit testing:

```python
# test_mcp_server.py
import pytest
from fastmcp import FastMCP, Client
from mcp.types import TextContent

mcp = FastMCP("AI Agent Server")

@mcp.tool()
async def query_knowledge_base(query: str, max_results: int = 5) -> dict:
    """Query the knowledge base and return relevant documents."""
    # Implementation details...
    pass

class TestMCPServer:
    @pytest.mark.asyncio
    async def test_tool_registration(self):
        """Verify tools are registered correctly."""
        async with Client(mcp) as client:
            tools = await client.list_tools()
            tool_names = [t.name for t in tools]
            assert "query_knowledge_base" in tool_names
    
    @pytest.mark.asyncio
    async def test_tool_execution(self):
        """Test tool executes with correct parameters."""
        async with Client(mcp) as client:
            result = await client.call_tool(
                "query_knowledge_base",
                arguments={"query": "test query", "max_results": 3}
            )
            assert isinstance(result[0], TextContent)
            assert len(result) > 0
    
    @pytest.mark.asyncio
    async def test_tool_parameter_validation(self):
        """Verify parameter schema validation."""
        async with Client(mcp) as client:
            with pytest.raises(Exception):  # Should reject invalid params
                await client.call_tool(
                    "query_knowledge_base",
                    arguments={"invalid_param": "value"}
                )
```

For **AG-UI protocol testing**, which handles agent-to-frontend streaming communication, test the event sequence emission:

```python
# test_ag_ui_agent.py
import pytest
from ag_ui.client import AbstractAgent, EventType, RunAgentInput
from rx import operators as ops

class TestAGUIAgent:
    @pytest.mark.asyncio
    async def test_event_sequence(self, ai_agent):
        """Verify correct AG-UI event emission order."""
        input_data = RunAgentInput(
            threadId="test-thread",
            runId="test-run",
            messages=[{"role": "user", "content": "Hello"}],
            tools=[],
            state={}
        )
        
        events = await ai_agent.stream(input_data).pipe(
            ops.to_list()
        ).run()
        
        # Verify lifecycle events
        assert events[0].type == EventType.RUN_STARTED
        assert events[-1].type == EventType.RUN_FINISHED
        
        # Verify message streaming events exist
        assert any(e.type == EventType.TEXT_MESSAGE_CONTENT for e in events)
```

---

## Compliance-friendly test data management combines encryption, access control, and synthetic data

For sensitive test data that must remain outside source control, implement **layered security with KMS encryption, IAM access control, and audit logging**:

```hcl
# Terraform - Compliant S3 test data bucket
resource "aws_s3_bucket_server_side_encryption_configuration" "test_data" {
  bucket = aws_s3_bucket.test_data.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.test_data_key.arn
    }
  }
}

# IAM policy - Least privilege for test runners
data "aws_iam_policy_document" "test_data_access" {
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:GetObjectVersion", "s3:ListBucket"]
    resources = [
      aws_s3_bucket.test_data.arn,
      "${aws_s3_bucket.test_data.arn}/*"
    ]
  }
  statement {
    effect    = "Allow"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [aws_kms_key.test_data_key.arn]
  }
}
```

For HIPAA or SOC2 compliance, **never use real PII in test data**. Instead, use synthetic data generators like **Tonic.ai, Synthesized, or MOSTLY AI** that preserve data relationships and statistical properties while eliminating compliance risk. Automate synthetic data generation in CI/CD:

```yaml
# Generate fresh synthetic test data weekly
name: Refresh Synthetic Test Data
on:
  schedule:
    - cron: '0 0 * * 0'
jobs:
  generate:
    runs-on: ubuntu-latest
    steps:
      - name: Generate synthetic data
        run: |
          synthesized generate --config synthetic-config.yaml \
            --output s3://test-data-bucket/synthetic/
      - name: Update DVC tracking
        run: |
          dvc add tests/fixtures/synthetic/
          dvc push
```

---

## Helm chart pattern provides reusable test infrastructure

A Helm chart encapsulating the complete test infrastructure enables consistent deployment across environments:

```yaml
# values.yaml
testRunner:
  image: your-registry/ai-tests
  tag: v1.2.3
  
  job:
    backoffLimit: 1
    activeDeadlineSeconds: 1800
    ttlSecondsAfterFinished: 3600
  
  resources:
    requests:
      memory: "1Gi"
      cpu: "500m"
    limits:
      memory: "2Gi"
      cpu: "2000m"

elasticsearch:
  host: elasticsearch.monitoring:9200
  indexPrefix: pytest-results

s3:
  testDataBucket: company-test-data
  region: us-east-1

deepeval:
  threshold: 0.7
  model: gpt-4o
```

---

## Common anti-patterns to avoid

| Anti-pattern | Impact | Correct approach |
|--------------|--------|------------------|
| Using `latest` image tag | Non-reproducible tests | Pin specific version tags |
| No resource limits | Tests can starve cluster | Always set requests and limits |
| `restartPolicy: Always` in Jobs | Infinite restart loops | Use `Never` for test Jobs |
| Hardcoded credentials | Security risk, rotation failures | Use Secrets Manager or Vault |
| Test data in Git | Compliance violations, repo bloat | Use DVC with S3 backend |
| No timeout configuration | Hung tests block pipelines | Set both Job and pytest timeouts |
| Running tests in production namespace | Risk of affecting production | Use dedicated test namespaces |

---

## Conclusion

Building a robust end-to-end testing system for AI agents in Kubernetes requires thoughtful integration of multiple components. **The recommended architecture uses Kubernetes Jobs with proper lifecycle management for test execution, DVC for compliant test data versioning in S3, DeepEval for semantic AI evaluation, and pytest-elk-reporter for Elasticsearch results streaming.** 

Key implementation priorities should be: first, establish the Kubernetes Job infrastructure with proper timeouts and cleanup; second, configure DVC and S3 fixtures for external test data; third, integrate DeepEval metrics for AI accuracy assessment; fourth, set up Elasticsearch reporting with Kibana dashboards. For MCP server testing, the mcp-testing-kit provides essential in-memory testing capabilities, while AG-UI testing requires event sequence validation through RxJS-based patterns.

The compliance requirements—keeping sensitive test data outside source control—are well-served by the DVC pattern, which maintains version correlation between code and test data while storing actual data in encrypted S3 buckets with IAM access control and CloudTrail audit logging.