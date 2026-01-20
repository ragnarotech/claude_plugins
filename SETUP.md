# Setup Guide

Complete setup instructions for the DeepEval BDD Example project.

## Quick Start (5 minutes)

### 1. Install Dependencies

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install all dependencies
pip install -e .

# Or install manually
pip install pytest pytest-bdd deepeval pytest-elk-reporter boto3 moto dvc pyyaml openai
```

### 2. Initialize DVC

```bash
# Initialize DVC for data versioning
dvc init

# (Optional) Configure remote storage
dvc remote add -d myremote /tmp/dvc-storage
```

### 3. Run Tests

```bash
# Run all BDD tests
pytest tests/step_defs/ -v

# Run specific test markers
pytest tests/step_defs/ -m rag -v
pytest tests/step_defs/ -m critical -v
```

## Detailed Setup

### Prerequisites

- **Python 3.9+**: Check with `python --version`
- **Git**: For version control
- **pip**: Python package manager

### Installation Steps

#### Step 1: Clone and Navigate

```bash
git clone <your-repo-url>
cd claude_plugins
```

#### Step 2: Virtual Environment

Creating a virtual environment is recommended to isolate dependencies:

```bash
# Create virtual environment
python -m venv venv

# Activate (Linux/Mac)
source venv/bin/activate

# Activate (Windows)
venv\Scripts\activate

# Verify activation
which python  # Should point to venv/bin/python
```

#### Step 3: Install Dependencies

```bash
# Install project in editable mode
pip install -e .

# Verify installation
pip list | grep -E "pytest|deepeval|dvc"
```

Expected output:
```
deepeval        0.21.x
dvc             3.x.x
pytest          7.x.x
pytest-bdd      7.x.x
```

#### Step 4: Configure DVC (Optional)

DVC is used for version controlling test data. For local testing:

```bash
# Initialize DVC
dvc init

# Create local storage
mkdir -p /tmp/dvc-storage
dvc remote add -d local /tmp/dvc-storage

# Verify configuration
dvc remote list
```

For production (S3, GCS, Azure):

```bash
# AWS S3
dvc remote add -d myremote s3://my-bucket/dvc-cache
dvc remote modify myremote region us-west-2

# Google Cloud Storage
dvc remote add -d myremote gs://my-bucket/dvc-cache

# Azure Blob Storage
dvc remote add -d myremote azure://mycontainer/path
```

#### Step 5: Verify Installation

```bash
# Test mock LLM client
python -c "from src.mock_llm import MockLLMClient; print(MockLLMClient().generate('test'))"

# Run pytest collection (don't execute)
pytest tests/step_defs/ --collect-only

# Run a simple test
pytest tests/step_defs/test_rag_steps.py -k "faithfulness" -v
```

## Running Tests

### Basic Commands

```bash
# Run all tests
pytest tests/step_defs/ -v

# Run with detailed output
pytest tests/step_defs/ -vv

# Run specific feature
pytest tests/step_defs/test_rag_steps.py -v
pytest tests/step_defs/test_llm_steps.py -v
```

### Using Markers

Tests are tagged with markers for selective execution:

```bash
# RAG-specific tests
pytest -m rag -v

# Safety/security tests
pytest -m safety -v

# Critical path tests
pytest -m critical -v

# Regression tests
pytest -m regression -v

# Combine markers
pytest -m "rag and critical" -v
pytest -m "not slow" -v
```

### Filtering by Keywords

```bash
# Run tests matching keyword
pytest -k "faithfulness" -v
pytest -k "bias or toxicity" -v
pytest -k "not hallucination" -v
```

### Test Reports

```bash
# JUnit XML (for CI/CD)
pytest tests/step_defs/ --junitxml=test-results/junit.xml

# Generate coverage report
pytest tests/step_defs/ --cov=src --cov=tests --cov-report=html

# View coverage
open htmlcov/index.html  # Mac
xdg-open htmlcov/index.html  # Linux
```

## Configuration

### pytest.ini

Pytest configuration is in `pytest.ini`:

```ini
[pytest]
testpaths = tests
python_files = test_*.py
markers =
    rag: RAG pipeline tests
    safety: Safety and toxicity tests
    critical: Critical path tests
```

Customize as needed for your project.

### pyproject.toml

Dependencies and project metadata are in `pyproject.toml`. To add new dependencies:

```toml
[project]
dependencies = [
    "pytest>=7.4.0",
    "your-new-package>=1.0.0",
]
```

Then reinstall:
```bash
pip install -e .
```

## Using Real LLMs

The project uses a mock LLM client by default. To use real OpenAI models:

### 1. Set API Key

```bash
# Export in shell
export OPENAI_API_KEY="sk-your-api-key"

# Or create .env file
echo "OPENAI_API_KEY=sk-your-api-key" > .env
```

### 2. Modify Fixtures

In `tests/conftest.py`, replace mock client:

```python
import openai

@pytest.fixture
def mock_llm_client():
    """Real OpenAI client."""
    return openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
```

### 3. Update Step Definitions

Modify `tests/step_defs/test_rag_steps.py`:

```python
@when('the LLM generates a response')
def generate_real_response(test_context, mock_llm_client):
    response = mock_llm_client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": test_context["input"]}]
    )
    test_context["actual_output"] = response.choices[0].message.content
    # Create test case...
```

## DVC Workflows

### Version Test Data

```bash
# Make changes to test data
vim data/test_cases.json

# Add to DVC tracking
dvc add data/test_cases.json

# Commit the .dvc file
git add data/test_cases.json.dvc data/.gitignore
git commit -m "Update test dataset v2"

# Push data to remote
dvc push

# Push code to git
git push
```

### Retrieve Data

```bash
# Pull latest data
dvc pull

# Pull specific version
git checkout main~1  # Go back one commit
dvc checkout  # Get data for that commit
```

### Share Data with Team

```bash
# Team member clones repo
git clone <repo-url>
cd claude_plugins

# Install dependencies
pip install -e .

# Get data
dvc pull

# Run tests
pytest tests/step_defs/ -v
```

## Troubleshooting

### Import Errors

**Problem**: `ModuleNotFoundError: No module named 'pytest_bdd'`

**Solution**:
```bash
pip install pytest-bdd
# Or reinstall all dependencies
pip install -e .
```

### DVC Errors

**Problem**: `DVC: ERROR: failed to pull data`

**Solution**:
```bash
# Check remote configuration
dvc remote list

# Configure remote if missing
dvc remote add -d myremote s3://bucket/path

# Verify credentials
dvc remote modify myremote --local access_key_id YOUR_KEY
dvc remote modify myremote --local secret_access_key YOUR_SECRET
```

### Test Discovery Issues

**Problem**: `pytest: error: file not found: tests/step_defs/`

**Solution**:
```bash
# Verify you're in project root
pwd  # Should show .../claude_plugins

# Check directory exists
ls -la tests/step_defs/

# Run from project root
cd /path/to/claude_plugins
pytest tests/step_defs/ -v
```

### DeepEval Metric Errors

**Problem**: `ImportError: cannot import name 'FaithfulnessMetric'`

**Solution**:
```bash
# Update deepeval
pip install --upgrade deepeval

# Or specify version
pip install deepeval>=0.21.0
```

### Feature File Not Found

**Problem**: `pytest_bdd.exceptions.FeatureError: Feature file not found`

**Solution**:
```bash
# Ensure bdd_features_base_dir is set in pytest.ini
grep bdd_features pytest.ini

# Should output:
# bdd_features_base_dir = features/

# Verify feature files exist
ls -la features/*.feature
```

## Development Workflow

### Adding New Scenarios

1. **Write Feature File**

Create or edit `.feature` file in `features/`:

```gherkin
Scenario: New test case
  Given a user query "new query"
  When the LLM generates a response
  Then the response should meet criteria
```

2. **Implement Steps** (if new)

Add to `tests/step_defs/test_*.py`:

```python
@then('the response should meet criteria')
def check_criteria(test_context):
    # Implementation
    pass
```

3. **Run Tests**

```bash
pytest tests/step_defs/ -k "new_test" -v
```

### Adding New Metrics

1. **Create Step Definition**

```python
from deepeval.metrics import YourNewMetric

@then(parsers.parse('the metric score should be at least {threshold:f}'))
def check_new_metric(test_context, threshold):
    metric = YourNewMetric(threshold=threshold)
    metric.measure(test_context["test_case"])
    assert metric.score >= threshold
```

2. **Use in Feature File**

```gherkin
Then the metric score should be at least 0.8
```

### Continuous Integration

#### GitHub Actions

Create `.github/workflows/test.yml`:

```yaml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.9'
      - run: pip install -e .
      - run: dvc init --no-scm
      - run: pytest tests/step_defs/ -v
```

#### GitLab CI

Create `.gitlab-ci.yml`:

```yaml
test:
  image: python:3.9
  script:
    - pip install -e .
    - pytest tests/step_defs/ -v --junitxml=report.xml
  artifacts:
    reports:
      junit: report.xml
```

## Next Steps

1. **Customize Feature Files**: Adapt scenarios to your use case
2. **Add Real LLM Integration**: Connect to OpenAI/Azure/etc.
3. **Configure DVC Remote**: Set up S3/GCS for data versioning
4. **Expand Test Coverage**: Add more scenarios and metrics
5. **Set up CI/CD**: Automate testing in your pipeline

## Resources

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-bdd Guide](https://pytest-bdd.readthedocs.io/)
- [DeepEval Docs](https://docs.confident-ai.com/)
- [DVC User Guide](https://dvc.org/doc/user-guide)
- [Gherkin Reference](https://cucumber.io/docs/gherkin/)

## Getting Help

- **Issues**: Open an issue on GitHub
- **Discussions**: Use GitHub Discussions
- **Documentation**: Check the README.md

---

**Happy Testing!** 🧪
