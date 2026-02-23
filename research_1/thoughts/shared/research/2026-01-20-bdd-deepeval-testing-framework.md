---
date: 2026-01-20T23:47:13Z
researcher: Claude
git_commit: e760f01e28ecaafa3e9b896faf18611fc2a78ec3
branch: main
repository: claude_plugins
topic: "BDD DeepEval Testing Framework - Research Materials and Sample Code Review"
tags: [research, bdd, deepeval, pytest-bdd, dvc, llm-testing, mcp, agui]
status: complete
last_updated: 2026-01-20
last_updated_by: Claude
---

# Research: BDD DeepEval Testing Framework - Research Materials and Sample Code Review

**Date**: 2026-01-20T23:47:13Z
**Researcher**: Claude
**Git Commit**: e760f01e28ecaafa3e9b896faf18611fc2a78ec3
**Branch**: main
**Repository**: claude_plugins

## Research Question

Given the initial prompt (`./initial_prompt.md`), review the research material and sample code to document the existing architecture, patterns, and requirements for implementing a BDD DeepEval testing framework.

## Summary

The repository contains comprehensive research documentation and sample code for building a BDD-based LLM testing framework using pytest-bdd and DeepEval. The materials address testing a Pydantic AI Agent with MCP Server running in Kubernetes, with specific compliance requirements around test data storage and CI/CD integration.

### Key Requirements from Initial Prompt

1. **Production System**: Pydantic AI Agent with AGUI protocol, MCP Server, local OpenAI API LLM, running in Kubernetes
2. **Test Stack**: python-bdd (pytest-bdd), deepeval, pytest, dvc
3. **Compliance Constraints**: Test data must NOT be stored in shared CI/CD infrastructure; only in local machines and Kubernetes
4. **Required Capabilities**:
   - Test correct MCP tool execution (including optional parameters)
   - Test conversational MCP tool usage with incomplete information
   - Test agent output correctness
   - Accept mock "Current Date" for date conversion testing
   - Store results in Elasticsearch

## Detailed Findings

### Research Documents

#### 1. End-to-End Testing Architecture (`research/End-to-End.md`)

Documents the comprehensive architecture for running pytest-based tests inside Kubernetes:

**Kubernetes Job Patterns**:
- Uses Kubernetes Jobs with `restartPolicy: Never`, `activeDeadlineSeconds` for timeouts, `ttlSecondsAfterFinished` for cleanup
- Native sidecar containers (Kubernetes 1.28+) for database dependencies
- CronJob pattern for scheduled test execution

**CI/CD Integration**:
- Gitlab CI/CD workflow with parallel wait for Job completion/failure
- `kubectl wait` for condition monitoring
- Log streaming during execution

**S3-backed Test Fixtures**:
- DVC for versioning with S3 backend
- Pytest fixtures for runtime loading from S3
- LRU caching to avoid repeated downloads

**Elasticsearch Reporting**:
- pytest-elk-reporter for direct streaming to Elasticsearch
- Custom hooks for AI-specific metrics (faithfulness_score, relevancy_score, latency)
- Index mapping optimized for LLM evaluation results

**DeepEval Integration**:
- LLMTestCase as core data structure
- Metrics: FaithfulnessMetric, AnswerRelevancyMetric, GEval, TaskCompletion, ToolCorrectness
- Threshold-based assertions with semantic evaluation

**MCP Server Testing**:
- FastMCP with Client for in-memory testing
- Tool registration verification
- Parameter schema validation
- AG-UI protocol event sequence testing

#### 2. Python BDD Framework for DeepEval (`research/Python BDD Framework for DeepEval LLM Testing.md`)

Establishes pytest-bdd as the optimal framework due to native pytest compatibility:

**Framework Comparison**:
| Framework | pytest Integration | Verdict |
|-----------|-------------------|---------|
| pytest-bdd | Native plugin | Recommended |
| behave | Standalone | Good alternative |
| radish | Standalone | Extended features |
| lettuce | None | Discontinued |

**DeepEval API Structure**:
```python
test_case = LLMTestCase(
    input="query",
    actual_output="response",
    retrieval_context=["context"],
    expected_output="expected"
)
metric = FaithfulnessMetric(threshold=0.7, model="gpt-4")
metric.measure(test_case)
# metric.score, metric.reason, metric.is_successful()
```

**Available Metrics**:
- RAG: FaithfulnessMetric, ContextualRelevancyMetric, ContextualPrecisionMetric
- Response: AnswerRelevancyMetric, GEval
- Safety: ToxicityMetric, BiasMetric, HallucinationMetric
- Agentic: ToolCorrectnessMetric, TaskCompletionMetric

**Architecture Pattern**:
```
Gherkin Features → pytest-bdd Step Definitions → DeepEval Metrics → pytest-elk-reporter → Elasticsearch
```

#### 3. DVC-Stored Gherkin Pattern (`research/DVC Stored Gherkin.md`)

Addresses compliance requirements with "Gherkin as Schema, S3 as Data Store":

**Pattern 1 - Reference-Based Scenarios**:
```gherkin
Scenario: Evaluate responses against golden dataset
  Given test cases are loaded from dataset "customer_support/golden_v2"
  When each query is processed by the AI agent
  Then all faithfulness scores should meet the threshold
```

**Pattern 2 - Step Definitions Fetching from S3**:
```python
@given(parsers.parse('test cases are loaded from dataset "{dataset_path}"'))
def load_dataset_from_s3(dataset_path, s3_client):
    bucket = os.environ["COMPLIANCE_TEST_DATA_BUCKET"]
    key = f"golden-datasets/{dataset_path}.json"
    response = s3_client.get_object(Bucket=bucket, Key=key)
    return json.loads(response['Body'].read())['test_cases']
```

**Pattern 3 - DVC Version Correlation**:
- `.dvc` pointer files in Git (~200 bytes)
- Actual data in S3 with KMS encryption
- Git history tracks which data version used with each commit

**Compliance Mapping**:
| Artifact | Location | In Source Control? |
|----------|----------|-------------------|
| Feature files | Git | Yes |
| Step definitions | Git | Yes |
| DVC pointers | Git | Yes |
| Golden test inputs | S3 | No |
| Expected outputs | S3 | No |
| Test results | Elasticsearch | No |

### Sample Code Implementation

#### Project Structure (`sample_code/`)

```
sample_code/
├── features/
│   ├── llm_evaluation.feature    # LLM quality tests
│   └── rag_quality.feature       # RAG pipeline tests
├── tests/
│   ├── conftest.py               # Fixtures and configuration
│   └── step_defs/
│       ├── test_llm_steps.py     # LLM evaluation steps
│       └── test_rag_steps.py     # RAG-specific steps
├── src/
│   └── mock_llm.py               # Mock LLM client
├── data/
│   └── test_cases.json.dvc       # DVC pointer file
├── pyproject.toml                # Dependencies
└── pytest.ini                    # Pytest configuration
```

#### Feature Files

**RAG Quality Feature** (`features/rag_quality.feature`):
- Background: Sets model and threshold defaults
- Scenarios: Faithfulness checking, relevancy scoring, hallucination detection, safety validation, intent classification
- Uses tags: `@rag`, `@critical`, `@safety`, `@regression`

**LLM Evaluation Feature** (`features/llm_evaluation.feature`):
- Scenarios: Response quality, bias detection, toxicity checking, custom G-Eval criteria
- Scenario Outlines for cross-domain testing

#### Step Definitions

**test_rag_steps.py** (`tests/step_defs/test_rag_steps.py:1-261`):
- Loads scenarios from feature file via `scenarios('../features/rag_quality.feature')`
- Given steps: `set_model`, `set_threshold`, `set_query`, `set_retrieval_context`, `set_adversarial_prompt`, `set_expected_intent`
- When steps: `set_rag_response`, `set_safe_response`, `evaluate_semantic_similarity`
- Then steps: `check_faithfulness`, `check_relevancy`, `check_faithfulness_failure`, `check_toxicity`, `check_appropriateness`, `check_relevancy_threshold`

**test_llm_steps.py** (`tests/step_defs/test_llm_steps.py:1-272`):
- Given steps: `set_expected_output`, `set_custom_criteria`, `set_domain`, `set_query_for_domain`
- When steps: `set_llm_response`, `generate_llm_response`
- Then steps: `check_answer_relevancy`, `check_response_success`, `check_bias`, `check_toxicity_llm`, `check_bias_detected`, `check_custom_criteria`, `check_domain_relevancy`

#### Shared Fixtures (`tests/conftest.py:1-161`)

**Session-scoped**:
- `project_root`: Returns Path to project directory
- `test_data_path`: Returns path to data directory
- `load_test_cases`: Loads JSON from DVC-tracked file
- `s3_test_data`: Simulates S3 loading (wraps `load_test_cases`)
- `configure_environment`: Sets mock OpenAI API key if not present
- `configure_elk_session`: Adds session metadata to ELK reports

**Function-scoped**:
- `test_context`: Dictionary for passing data between Given/When/Then steps
- `mock_llm_client`: Returns MockLLMClient instance
- `test_prompts`: Extracts test prompts from loaded data

**Hooks**:
- `pytest_configure`: For custom markers
- `pytest_collection_modifyitems`: Adds 'bdd' marker to BDD tests

#### Mock LLM Client (`src/mock_llm.py:1-245`)

**MockLLMClient**:
- Pattern-based response generation using regex matching
- Response map covers: customer support, technical support, intent classification, adversarial prompts
- Methods: `generate(prompt)`, `generate_with_context(prompt, context)`, `__call__`

**MockLLMAPIClient**:
- Mimics OpenAI API structure
- Nested `ChatCompletion` class with `create()` method
- Returns response in OpenAI format with choices, message, usage

#### Configuration

**pyproject.toml** (`sample_code/pyproject.toml:1-62`):
```toml
dependencies = [
    "pytest>=7.4.0",
    "pytest-bdd>=7.0.0",
    "deepeval>=0.21.0",
    "pytest-elk-reporter>=0.5.0",
    "boto3>=1.28.0",
    "moto[s3]>=4.2.0",
    "dvc>=3.0.0",
    "openai>=1.0.0",
]
```

**pytest.ini** (`sample_code/pytest.ini:1-27`):
- Test paths: `tests`
- Markers: `rag`, `safety`, `regression`, `critical`, `slow`
- BDD features base dir: `features/`
- Optional ELK configuration (commented)

### Gap Analysis: Sample Code vs Requirements

The sample code provides a foundation but does not fully address the specific requirements from `initial_prompt.md`:

| Requirement | Sample Code Status |
|-------------|-------------------|
| MCP tool verification | Not implemented |
| Tool parameter validation (with optional params) | Not implemented |
| Conversational MCP tool usage | Not implemented |
| Mock "Current Date" injection | Not implemented |
| Agent output correctness | Partial (via DeepEval metrics) |
| Elasticsearch storage | Configured but not demonstrated |
| Kubernetes deployment | Documented in research, not in code |

### Example Test Cases from Initial Prompt

**MCP Tool Test** (not implemented in sample):
```gherkin
Given: Today is 1/7/2025
User Prompt: "What should I wear tomorrow to Ocean City, NJ tomorrow"
Verify Tool Called: weather_tool
Verify Tool Parameters: city=Ocean City state=NJ date=1/8/2025
Verify Tool Response: "{temp: 64, wind: 10, wind_direction: "southwest" }
Agent Response: "It will be cold tomorrow, wear a sweatshirt"
```

**Conversation Tool Test** (not implemented in sample):
```gherkin
Given: Today is 1/7/2025
User Prompt: "I'm visiting my mom tomorrow, What should I wear?"
Agent Response: "Where does your mom live?"
User Response: "Ocean City, NJ"
Verify Tool Called: weather_tool
...
```

## Code References

- `sample_code/features/rag_quality.feature:1-65` - RAG pipeline BDD scenarios
- `sample_code/features/llm_evaluation.feature:1-52` - LLM evaluation scenarios
- `sample_code/tests/conftest.py:1-161` - Pytest fixtures and configuration
- `sample_code/tests/step_defs/test_rag_steps.py:1-261` - RAG step definitions
- `sample_code/tests/step_defs/test_llm_steps.py:1-272` - LLM step definitions
- `sample_code/src/mock_llm.py:1-245` - Mock LLM client implementation
- `sample_code/pyproject.toml:1-62` - Project dependencies
- `sample_code/pytest.ini:1-27` - Pytest configuration
- `research/End-to-End.md` - Kubernetes and CI/CD patterns
- `research/Python BDD Framework for DeepEval LLM Testing.md` - Framework comparison
- `research/DVC Stored Gherkin.md` - Compliance-friendly data architecture

## Architecture Documentation

### Current Sample Code Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Feature Files                            │
│  ┌─────────────────────┐  ┌─────────────────────┐              │
│  │ rag_quality.feature │  │ llm_evaluation.feature│              │
│  └──────────┬──────────┘  └──────────┬──────────┘              │
└─────────────┼────────────────────────┼──────────────────────────┘
              │                        │
              ▼                        ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Step Definitions                            │
│  ┌─────────────────────┐  ┌─────────────────────┐              │
│  │ test_rag_steps.py   │  │ test_llm_steps.py   │              │
│  │ - Given: query,     │  │ - Given: expected,   │              │
│  │   context, prompt   │  │   criteria, domain   │              │
│  │ - When: RAG response│  │ - When: LLM response │              │
│  │ - Then: faithfulness│  │ - Then: relevancy,   │              │
│  │   relevancy, toxic  │  │   bias, toxicity     │              │
│  └──────────┬──────────┘  └──────────┬──────────┘              │
└─────────────┼────────────────────────┼──────────────────────────┘
              │                        │
              ▼                        ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Shared Fixtures (conftest.py)                │
│  ┌─────────────────┐  ┌──────────────┐  ┌────────────────┐     │
│  │ test_context    │  │ mock_llm_    │  │ load_test_     │     │
│  │ (state dict)    │  │ client       │  │ cases (DVC)    │     │
│  └────────┬────────┘  └──────┬───────┘  └───────┬────────┘     │
└───────────┼──────────────────┼──────────────────┼───────────────┘
            │                  │                  │
            ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                      External Systems                            │
│  ┌─────────────────┐  ┌──────────────┐  ┌────────────────┐     │
│  │ DeepEval        │  │ MockLLMClient│  │ DVC/S3         │     │
│  │ Metrics         │  │ (or real LLM)│  │ (test data)    │     │
│  └─────────────────┘  └──────────────┘  └────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
```

### Target Architecture (from Research)

```
┌─────────────────────────────────────────────────────────────────┐
│                     SOURCE CONTROL (Git)                         │
│  Feature Files + Step Definitions + DVC Pointers                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    KUBERNETES TEST JOB                           │
│  pytest-bdd → DeepEval → Results → Elasticsearch                │
│         ↓                                                        │
│  Fetches data from S3 (IAM role + KMS)                          │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
┌──────────────────┐ ┌──────────────┐ ┌──────────────────┐
│ S3 (Encrypted)   │ │ Elasticsearch│ │ Pydantic AI Agent│
│ Test Data + DVC  │ │ Results Index│ │ + MCP Server     │
└──────────────────┘ └──────────────┘ └──────────────────┘
```

## Related Research

- `research/End-to-End.md` - Kubernetes Job patterns, CI/CD integration, S3 fixtures, Elasticsearch reporting
- `research/Python BDD Framework for DeepEval LLM Testing.md` - Framework comparison, DeepEval API, step definition patterns
- `research/DVC Stored Gherkin.md` - Compliance architecture, Gherkin as schema, S3 data separation

## Open Questions

1. **MCP Tool Testing**: The sample code does not include step definitions for verifying MCP tool calls, parameters, or responses. This requires integration with the MCP server's tool invocation logging or mocking.

2. **Conversational Flow Testing**: Multi-turn conversation testing (agent asks clarifying question → user responds → tool called) is not implemented. Requires state management across turns.

3. **Current Date Injection**: No mechanism exists for injecting a mock "current date" for date conversion testing. The agent or test fixtures need to accept a date override.

4. **AGUI Protocol Integration**: The research documents AG-UI event sequence testing, but no sample code demonstrates this integration.

5. **Kubernetes Deployment**: While research covers Kubernetes Job patterns, no Helm charts, Job manifests, or deployment configurations exist in sample_code.

6. **Elasticsearch Integration**: pytest-elk-reporter is configured but not actively demonstrated with custom DeepEval metric reporting.
