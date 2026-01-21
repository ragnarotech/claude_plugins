# BDD DeepEval MCP Testing Framework

A comprehensive end-to-end testing framework for Pydantic AI Agents with MCP Server using pytest-bdd and DeepEval.

## Features

- **BDD Testing**: Gherkin feature files with pytest-bdd for business-readable tests
- **MCP Tool Verification**: Verify correct tool calls with parameters (including optional params)
- **Conversational Testing**: Multi-turn conversation testing with clarifying questions
- **DeepEval Metrics**: LLM-based quality evaluation (relevancy, faithfulness, custom criteria)
- **S3/DVC Data**: Compliance-friendly test data storage (data in S3, pointers in Git)
- **Elasticsearch Reporting**: Test results with DeepEval metrics stored in Elasticsearch
- **Kubernetes Ready**: Run tests in-cluster with production agent access

## Project Structure

```
bdd_tests/
├── features/               # Gherkin feature files
│   ├── mcp_tools.feature
│   ├── conversations.feature
│   └── deepeval_metrics.feature
├── tests/
│   ├── conftest.py        # Pytest fixtures
│   └── step_defs/         # BDD step definitions
│       ├── common_steps.py
│       ├── mcp_steps.py
│       ├── conversation_steps.py
│       ├── deepeval_steps.py
│       └── data_steps.py
├── src/
│   ├── agent_wrapper.py   # Pydantic AI agent wrapper
│   ├── mcp_verifier.py    # MCP tool verification utilities
│   ├── data_loader.py     # S3/DVC test data loader
│   └── elk_reporter.py    # Elasticsearch reporter
├── data/                  # Test data (tracked by DVC)
│   ├── .gitignore
│   └── test_cases.json.dvc
├── k8s/                   # Kubernetes manifests
│   ├── test-job.yaml
│   └── serviceaccount.yaml
├── .github/workflows/     # CI/CD
│   └── test.yaml
├── Dockerfile
├── pyproject.toml
├── pytest.ini
└── requirements.txt
```

## Installation

### Local Development

```bash
# Install dependencies
pip install -e .

# Configure your Pydantic AI agent
# Edit tests/conftest.py and replace the mock agent with your actual agent
```

### Configure DVC (Optional)

```bash
# Initialize DVC
dvc init

# Configure S3 remote (replace with your bucket)
dvc remote add -d s3remote s3://your-bucket/dvc-cache

# Add test data
dvc add data/test_cases.json
dvc push
```

## Quick Start

### 1. Configure Your Agent

Edit `tests/conftest.py` and replace the placeholder agent:

```python
@pytest.fixture(scope="session")
def agent_instance():
    from your_agent_package import create_agent
    return create_agent()
```

### 2. Run Tests Locally

```bash
# Run all tests
pytest tests/ -v

# Run specific markers
pytest tests/ -v -m mcp          # MCP tool tests
pytest tests/ -v -m conversation # Conversation tests
pytest tests/ -v -m metrics      # DeepEval metric tests
```

### 3. Run with DeepEval Metrics

```bash
# Set OpenAI API key for DeepEval
export OPENAI_API_KEY="sk-..."

# Run metric tests
pytest tests/ -v -m metrics
```

## Writing Tests

### Example: MCP Tool Test

**Feature file** (`features/mcp_tools.feature`):
```gherkin
Scenario: Weather tool with date calculation
  Given today is "1/7/2025"
  When the user says "What should I wear tomorrow to Ocean City, NJ"
  Then the agent should call "weather_tool"
  And the tool parameters should include:
    | city  | Ocean City |
    | state | NJ         |
    | date  | 1/8/2025   |
  And the agent response should mention appropriate clothing
```

### Example: Conversational Test

```gherkin
Scenario: Agent asks for location when not provided
  Given today is "1/7/2025"
  And a new conversation
  When the user says "I'm visiting my mom tomorrow, What should I wear?"
  Then the agent should ask about "location"
  When the user responds "Ocean City, NJ"
  Then after the conversation, the tool "weather_tool" should have been called
```

### Example: DeepEval Metrics

```gherkin
Scenario: Response relevancy for weather query
  Given today is "1/7/2025"
  When the user says "What should I wear tomorrow to Ocean City, NJ"
  Then the answer relevancy score should be at least 0.8
```

## Kubernetes Deployment

### Prerequisites

1. Kubernetes cluster with kubectl access
2. S3 bucket for test data
3. Elasticsearch cluster (optional)
4. Container registry

### Deploy

```bash
# Build and push Docker image
docker build -t your-registry/bdd-deepeval-tests:latest .
docker push your-registry/bdd-deepeval-tests:latest

# Create secrets
kubectl create secret generic openai-credentials \
  --from-literal=api-key=sk-...

kubectl create secret generic elasticsearch-credentials \
  --from-literal=username=test_reporter \
  --from-literal=password=...

# Deploy service account and job
kubectl apply -f k8s/serviceaccount.yaml
kubectl apply -f k8s/test-job.yaml

# Watch logs
kubectl logs -f job/bdd-deepeval-tests
```

## Environment Variables

### Local Development
- `OPENAI_API_KEY`: OpenAI API key for DeepEval metrics
- `TEST_DATA_BUCKET`: S3 bucket for test data (optional)

### Kubernetes
- `TEST_DATA_BUCKET`: S3 bucket name
- `AWS_REGION`: AWS region
- `ES_HOST`: Elasticsearch host
- `ES_USERNAME`: Elasticsearch username
- `ES_PASSWORD`: Elasticsearch password
- `GIT_COMMIT`: Git commit SHA
- `GIT_BRANCH`: Git branch name
- `TEST_ENV`: Environment name (kubernetes, local, etc.)

## Test Data Management

### Schema

Test data follows this JSON schema:

```json
{
  "test_cases": [
    {
      "id": "weather_001",
      "input": "What should I wear tomorrow?",
      "mock_date": "1/7/2025",
      "expected_tool": "weather_tool",
      "expected_params": {
        "city": "Ocean City",
        "state": "NJ"
      },
      "expected_output": "...",
      "tags": ["weather", "smoke"]
    }
  ]
}
```

### Loading Test Data

```python
# In step definitions
@given('test cases are loaded from dataset "weather_scenarios"')
def load_dataset(test_context, load_test_cases, dataset_name):
    test_cases = load_test_cases(dataset_name)
    test_context["test_cases"] = test_cases
```

## Elasticsearch Reporting

When `ES_HOST` environment variable is set, test results are automatically sent to Elasticsearch with:

- Test metadata (name, outcome, duration)
- DeepEval metric scores
- MCP tool calls
- Agent responses
- Git metadata

View results in Kibana by creating visualizations on the `bdd-test-results` index.

## CI/CD Integration

The framework includes a GitHub Actions workflow (`.github/workflows/test.yaml`) that:

1. Runs tests locally (without integration markers)
2. Builds Docker image
3. Deploys Kubernetes Job
4. Waits for completion
5. Streams logs
6. Cleans up resources

## Configuration Notes

### Replace Placeholders

Before deploying:

1. **k8s/test-job.yaml**: Replace `your-registry` and `your-test-data-bucket`
2. **k8s/serviceaccount.yaml**: Replace `ACCOUNT_ID` with AWS account ID
3. **.dvc/config**: Replace `your-bucket-name` with S3 bucket
4. **tests/conftest.py**: Replace mock agent with your actual agent

## Troubleshooting

### Tests fail with "No module named 'deepeval'"

Install dependencies: `pip install -e .`

### Agent wrapper doesn't extract tool calls

Verify your agent's response format includes `tool_results()` method. Adjust `agent_wrapper.py` if needed.

### S3 data not loading

1. Verify `TEST_DATA_BUCKET` environment variable is set
2. Check IAM permissions for S3 access
3. For local development, ensure `dvc pull` has been run

### Kubernetes Job fails

1. Check logs: `kubectl logs job/bdd-deepeval-tests`
2. Verify secrets exist: `kubectl get secrets`
3. Check service account permissions
4. Verify agent is accessible from the pod

## License

Apache 2.0

## Support

For issues and questions, please open an issue in the repository.
