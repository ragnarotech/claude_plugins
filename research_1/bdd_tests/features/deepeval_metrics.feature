Feature: DeepEval Quality Metrics
  As a QA engineer
  I want to evaluate agent response quality using AI metrics
  So that I can ensure consistent, high-quality outputs

  Background:
    Given the LLM evaluator uses model "gpt-4"
    And the default threshold is 0.7

  @metrics @relevancy
  Scenario: Response relevancy for weather query
    Given today is "1/7/2025"
    When the user says "What should I wear tomorrow to Ocean City, NJ"
    Then the answer relevancy score should be at least 0.8

  @metrics @faithfulness
  Scenario: Response faithfulness to context
    Given today is "1/7/2025"
    And retrieval context:
      """
      Weather forecast for Ocean City, NJ on 1/8/2025:
      Temperature: 64F
      Wind: 10mph from Southwest
      Conditions: Partly cloudy
      """
    When the user says "What should I wear tomorrow to Ocean City, NJ"
    Then the faithfulness score should be at least 0.8
    And the agent response should contain "64"

  @metrics @mcp
  Scenario: MCP tool selection quality
    Given today is "1/7/2025"
    When the user says "What should I wear tomorrow to Ocean City, NJ"
    Then the MCP use score should be at least 0.7

  @metrics @custom
  Scenario: Custom evaluation criteria
    Given today is "1/7/2025"
    And custom evaluation criteria:
      """
      - Provides specific clothing recommendations
      - Mentions temperature or weather conditions
      - Is helpful and actionable
      - Does not include irrelevant information
      """
    When the user says "What should I wear tomorrow to Ocean City, NJ"
    Then the custom criteria score should be at least 0.75

  @metrics @comprehensive
  Scenario: All quality checks pass
    Given today is "1/7/2025"
    When the user says "What should I wear tomorrow to Ocean City, NJ"
    Then the response should pass all quality checks
