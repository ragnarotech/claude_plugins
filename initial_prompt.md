# Goal
I want a fully flushed out (End to end) implementation of a BDD DeepEval testing framework.

# Production System Description
* Pydantic AI Agent - Utilizing AGUI protocol 
* Includes MCP Server with multiple tools
* local openai api LLM
* Already running in kubernetes namespace
* Has existing CI/CD pipeline

# Test System
## Required Tech Stack
* python-bdd
* deepeval
* pytest
* dvc

## Optional Tech Stack
* elastic-apm
* elastic

## Test System Requirements
* Utilizes python-bdd
* Run locally and in kubernetes
* Test data MUST NOT be downloaded onto the shared CI/CD Infastructure.  It can only exist on local machines and in kubernetes
* Test results for each test must be stored in elastic search index (could use elastic apm)
* Must be able to test correct MCP tool was executed even if optional parameters are provided
* Must be able to test conversational MCP tool usage when incomplete information is provided to the agent
* Must be able to test agent output for correctness
* Must be able to accept mock "Current Date" to help with date conversions

# Example prompts
## MCP Tool Test
Given: Today is 1/7/2025
User Prompt: "What should I wear tomorrow to Ocean City, NJ tomorrow"
Verify Tool Called: weather_tool
Verify Tool Parameters: city=Ocean City state=NJ date=1/8/2025
Verify Tool Response: "{temp: 64, wind: 10, wind_direction: "southwest" }
Agent Response: "It will be cold tomorrow, wear a sweatshirt"

## Conversation Tool Test
Given: Today is 1/7/2025
User Prompt: "I'm visiting my mom tomorrow, What should I wear?"
Agent Response: "Where does your mom live?"
User Response: "Ocean City, NJ"
Verify Tool Called: weather_tool
Verify Tool Parameters: city=Ocean City state=NJ date=1/8/2025
Verify Tool Response: "{temp: 64, wind: 10, wind_direction: "southwest" }
Agent Response: "It will be cold tomorrow, wear a sweatshirt"

# Utilize Research Docs
## Initial Research
* **Research Prompt**: "Due to specific internal compliance requirements, I need to run end to end tests and integration test on a container within our kubernetes cluster.  Our tests are written in python using pytest.  Are there any existing patterns to do this?  I'm also planning on storing results in elastic search kabana and generate dashboards for public consumption.  I likely also need to store expected test outputs and maybe test inputs due to compliance concerns where I can't store that information in the test source control. This is to test an AI agent and MCP server utilizing AGUI.  And Include AI deep eval testing."
* **Research Results**: [End-to-End](research/End-to-End.md)

## Follow up
* **Follow up prompt**: "Are there Cucumber BDD Gherkin syntax testing frameworks for python deepeval : https://github.com/confident-ai/deepeval. How well would something like this fit into the above system"
* **Follow up response**: [Python BDD Framework for DeepEval](research/Python%20BDD%20Framework%20for%20DeepEval%20LLM%20Testing.md)

## Follow up #2
* **Follow up prompt**: "I'm also wondering if Gherkin syntax could help with the compliance needs of keep the test inputs and expected outputs outside of source control"
* **Follow up response**: [DVC Stored Gherkin](research/DVC%20Stored%20Gherkin.md)

## Sample Code Generation
Code was generated based off the Research Docs but not the specific requirements listed above.  It can be utilized for inspiration. 
[Sample Code](sample_code/)