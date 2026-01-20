# DeepEval BDD Example

A comprehensive working example of Behavior-Driven Development (BDD) for LLM testing using **pytest-bdd**, **DeepEval**, and **DVC**.

This project demonstrates how to write human-readable Gherkin feature files for LLM evaluation, leverage DeepEval's powerful metrics, and version control test data using DVC.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Writing BDD Tests](#writing-bdd-tests)
- [Running Tests](#running-tests)
- [DVC Data Management](#dvc-data-management)
- [Metrics Reference](#metrics-reference)
- [CI/CD Integration](#cicd-integration)
- [License](#license)

## Overview

This project showcases the integration of three powerful tools:

- **pytest-bdd**: BDD framework for pytest, enabling Gherkin syntax
- **DeepEval**: LLM evaluation framework with 14+ metrics for testing RAG pipelines, chatbots, and agents
- **DVC**: Data Version Control for managing test datasets

The combination enables:
- ✅ **Business-readable test specifications** using Gherkin (Given/When/Then)
- ✅ **Sophisticated LLM evaluation** with metrics like Faithfulness, Hallucination, Bias, Toxicity
- ✅ **Version-controlled test data** with DVC for reproducibility
- ✅ **Integration with CI/CD** via pytest and standard reporting

## Features

### BDD Features Implemented

1. **RAG Pipeline Quality Assurance** (`features/rag_quality.feature`)
   - Response faithfulness to knowledge base
   - Answer relevancy scoring
   - Hallucination detection
   - Safety validation (toxicity, bias)
   - Intent classification accuracy

2. **LLM Response Quality Evaluation** (`features/llm_evaluation.feature`)
   - High-quality response validation
   - Bias detection with negative test cases
   - Custom G-Eval criteria evaluation
   - Cross-domain quality testing

### DeepEval Metrics Wrapped

- **FaithfulnessMetric**: Ensures responses are grounded in retrieval context
- **AnswerRelevancyMetric**: Measures relevance to user query
- **HallucinationMetric**: Detects factual claims not supported by context
- **ToxicityMetric**: Identifies toxic or harmful content
- **BiasMetric**: Detects gender, racial, and other biases
- **GEval**: Custom evaluation criteria in natural language

## Architecture

```
┌─────────────────────┐
│  Gherkin Features   │  Human-readable test specifications
│  (.feature files)   │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  pytest-bdd         │  Step definitions wrapping DeepEval
│  Step Definitions   │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  DeepEval Metrics   │  FaithfulnessMetric, GEval, etc.
│  + LLMTestCase      │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Mock LLM Client    │  Testing without API calls
│  (or Real LLM)      │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  DVC-tracked Data   │  Version-controlled test datasets
│  (test_cases.json)  │
└─────────────────────┘
```

## Installation

### Prerequisites

- Python 3.9 or higher
- Git
- (Optional) OpenAI API key for real LLM testing

### Setup

1. **Clone the repository**

```bash
git clone <repository-url>
cd claude_plugins
```

2. **Create and activate virtual environment**

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**

```bash
pip install -e .
```

Or install from requirements:

```bash
pip install pytest pytest-bdd deepeval pytest-elk-reporter boto3 moto dvc pyyaml openai
```

4. **Initialize DVC**

```bash
dvc init
```

5. **(Optional) Set OpenAI API key for real testing**

```bash
export OPENAI_API_KEY="sk-your-api-key-here"
```

**Note**: The project works without an API key using the mock LLM client.

## Quick Start

### Run all BDD tests

```bash
pytest tests/step_defs/ -v
```

### Run specific feature file

```bash
pytest tests/step_defs/test_rag_steps.py -v
```

### Run tests with specific markers

```bash
# Run only RAG tests
pytest tests/step_defs/ -m rag -v

# Run only safety tests
pytest tests/step_defs/ -m safety -v

# Run critical tests
pytest tests/step_defs/ -m critical -v
```

### Generate test report

```bash
pytest tests/step_defs/ -v --junitxml=test-results/junit.xml
```

## Project Structure

```
claude_plugins/
├── README.md                    # This file
├── LICENSE                      # Apache 2.0 License
├── pyproject.toml              # Project configuration and dependencies
├── pytest.ini                  # Pytest configuration
├── .gitignore                  # Git ignore patterns
├── .dvcignore                  # DVC ignore patterns
│
├── data/                       # DVC-tracked test data
│   ├── .gitignore             # Ignore actual data files
│   ├── test_cases.json        # Golden dataset for tests
│   └── test_cases.json.dvc    # DVC metadata file
│
├── features/                   # Gherkin feature files
│   ├── rag_quality.feature    # RAG pipeline tests
│   └── llm_evaluation.feature # General LLM quality tests
│
├── src/                        # Source code
│   ├── __init__.py
│   └── mock_llm.py            # Mock LLM client for testing
│
└── tests/                      # Test code
    ├── __init__.py
    ├── conftest.py            # Pytest fixtures and configuration
    └── step_defs/             # BDD step definitions
        ├── __init__.py
        ├── test_rag_steps.py      # RAG-specific steps
        └── test_llm_steps.py      # General LLM steps
```

## Writing BDD Tests

### Feature File Example

Create a `.feature` file in the `features/` directory:

```gherkin
Feature: Customer Support Chatbot Quality
  Ensure chatbot provides accurate and helpful responses

  Background:
    Given the LLM evaluator uses model "gpt-3.5-turbo"
    And the default threshold is 0.7

  @critical
  Scenario: Accurate refund information
    Given a user query "What is your refund policy?"
    And the retrieval context contains:
      """
      We offer a 30-day money-back guarantee.
      Refunds are processed within 5-7 business days.
      """
    When the RAG pipeline generates response "We offer 30-day refunds, processed in 5-7 days"
    Then the faithfulness score should be at least 0.8
    And the answer relevancy score should be at least 0.7
```

### Step Definition Example

Implement steps in `tests/step_defs/`:

```python
from pytest_bdd import given, when, then, parsers, scenarios
from deepeval.test_case import LLMTestCase
from deepeval.metrics import FaithfulnessMetric

scenarios('../features/your_feature.feature')

@given(parsers.parse('a user query "{query}"'))
def set_query(test_context, query):
    test_context["input"] = query

@then(parsers.parse('the faithfulness score should be at least {min_score:f}'))
def check_faithfulness(test_context, min_score, record_property):
    metric = FaithfulnessMetric(threshold=min_score)
    metric.measure(test_context["test_case"])

    record_property("faithfulness_score", metric.score)
    assert metric.score >= min_score, f"Score {metric.score} < {min_score}"
```

## Running Tests

### Basic Test Execution

```bash
# Run all tests
pytest tests/step_defs/ -v

# Run with coverage
pytest tests/step_defs/ --cov=src --cov-report=html

# Run in parallel (requires pytest-xdist)
pytest tests/step_defs/ -n auto
```

### Filtering Tests

```bash
# By marker
pytest -m "rag and critical"
pytest -m "not slow"

# By keyword
pytest -k "faithfulness"
pytest -k "safety or bias"
```

### Output Formats

```bash
# JUnit XML (for CI/CD)
pytest tests/step_defs/ --junitxml=test-results/junit.xml

# HTML report (requires pytest-html)
pytest tests/step_defs/ --html=test-results/report.html

# Verbose output
pytest tests/step_defs/ -vv --tb=long
```

## DVC Data Management

### Tracking Test Data

```bash
# Add test data to DVC tracking
dvc add data/test_cases.json

# Commit DVC metadata
git add data/test_cases.json.dvc data/.gitignore
git commit -m "Track test data with DVC"
```

### Configuring Remote Storage

```bash
# Add S3 remote
dvc remote add -d myremote s3://my-bucket/dvc-storage

# Or use Google Cloud Storage
dvc remote add -d myremote gs://my-bucket/dvc-storage

# Or use local remote for testing
dvc remote add -d myremote /tmp/dvc-storage
```

### Pushing and Pulling Data

```bash
# Push data to remote
dvc push

# Pull data from remote
dvc pull

# Check data status
dvc status
```

### Versioning Test Data

```bash
# Update test data
vim data/test_cases.json

# Track new version
dvc add data/test_cases.json
git add data/test_cases.json.dvc
git commit -m "Update test dataset v2"

# Push to remote
dvc push
```

## Metrics Reference

### Faithfulness Metric

Evaluates whether the LLM's response is grounded in the provided context.

```python
from deepeval.metrics import FaithfulnessMetric

metric = FaithfulnessMetric(
    threshold=0.7,
    model="gpt-4",
    include_reason=True
)
```

**Gherkin Usage:**
```gherkin
Then the faithfulness score should be at least 0.8
```

### Answer Relevancy Metric

Measures how relevant the response is to the user's query.

```python
from deepeval.metrics import AnswerRelevancyMetric

metric = AnswerRelevancyMetric(
    threshold=0.7,
    model="gpt-4"
)
```

**Gherkin Usage:**
```gherkin
Then the answer relevancy score should be at least 0.75
```

### Hallucination Metric

Detects when the LLM generates information not supported by context.

```python
from deepeval.metrics import HallucinationMetric

metric = HallucinationMetric(threshold=0.5)
```

**Gherkin Usage:**
```gherkin
Then the response should not hallucinate beyond context
```

### Bias Metric

Identifies potential biases related to gender, race, religion, etc.

```python
from deepeval.metrics import BiasMetric

metric = BiasMetric(threshold=0.1, model="gpt-4")
```

**Gherkin Usage:**
```gherkin
Then the bias score should be below 0.1
```

### G-Eval (Custom Criteria)

Allows custom evaluation criteria in natural language.

```python
from deepeval.metrics import GEval

metric = GEval(
    name="Helpfulness",
    criteria="Determine if the response is helpful to the user",
    evaluation_steps=[
        "Check if the response addresses the question",
        "Verify the response provides actionable information",
        "Assess if tone is appropriate"
    ],
    threshold=0.7
)
```

**Gherkin Usage:**
```gherkin
Given custom evaluation criteria:
  """
  - Addresses the user's question directly
  - Provides actionable next steps
  - Uses friendly and professional tone
  """
Then the custom criteria score should be at least 0.75
```

## CI/CD Integration

### GitHub Actions Example

Create `.github/workflows/test.yml`:

```yaml
name: BDD LLM Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e .

      - name: Initialize DVC
        run: |
          dvc init --no-scm
          dvc pull

      - name: Run BDD tests
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          pytest tests/step_defs/ -v --junitxml=test-results/junit.xml

      - name: Publish test results
        uses: EnricoMi/publish-unit-test-result-action@v2
        if: always()
        with:
          files: test-results/junit.xml
```

## Advanced Usage

### Using Real LLM Instead of Mock

Replace the mock client in step definitions:

```python
# In conftest.py
import openai

@pytest.fixture
def llm_client():
    """Real OpenAI client."""
    return openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# In step definitions
@when('the LLM generates a response')
def generate_real_response(test_context, llm_client):
    response = llm_client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": test_context["input"]}]
    )
    test_context["actual_output"] = response.choices[0].message.content
```

### Parallel Test Execution

```bash
# Install pytest-xdist
pip install pytest-xdist

# Run tests in parallel
pytest tests/step_defs/ -n auto -v
```

## Troubleshooting

### Common Issues

**Issue**: `ImportError: No module named 'deepeval'`
**Solution**: Install dependencies: `pip install -e .`

**Issue**: `DVC: failed to pull data`
**Solution**: Configure DVC remote: `dvc remote add -d myremote <storage-url>`

**Issue**: Tests fail with "OpenAI API key not found"
**Solution**: The project uses mock LLM by default. Tests should pass without API key.

**Issue**: `pytest: cannot find feature files`
**Solution**: Ensure `bdd_features_base_dir = features/` is set in `pytest.ini`

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## Resources

- **pytest-bdd**: https://pytest-bdd.readthedocs.io/
- **DeepEval**: https://docs.confident-ai.com/
- **DVC**: https://dvc.org/doc
- **Gherkin Syntax**: https://cucumber.io/docs/gherkin/reference/

## Acknowledgments

This project demonstrates integration patterns for Python BDD frameworks with DeepEval LLM testing. The architecture combines battle-tested tools to enable business-readable, version-controlled LLM evaluation.

---

**Questions or issues?** Open an issue on GitHub or contact the maintainers
