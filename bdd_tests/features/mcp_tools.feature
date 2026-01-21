Feature: MCP Tool Verification
  As a developer
  I want to verify my AI agent calls MCP tools correctly
  So that I can ensure reliable tool interactions

  Background:
    Given the LLM evaluator uses model "gpt-4"
    And the default threshold is 0.7

  @mcp @weather
  Scenario: Weather tool with date calculation
    Given today is "1/7/2025"
    When the user says "What should I wear tomorrow to Ocean City, NJ"
    Then the agent should call "weather_tool"
    And the tool parameters should include:
      | city  | Ocean City |
      | state | NJ         |
      | date  | 1/8/2025   |
    And the agent response should mention appropriate clothing

  @mcp @weather
  Scenario: Weather tool with explicit date
    Given today is "1/7/2025"
    When the user says "What's the weather in Philadelphia, PA on January 10th"
    Then the agent should call "weather_tool"
    And the tool parameters should include:
      | city  | Philadelphia |
      | state | PA           |
      | date  | 1/10/2025    |

  @mcp @weather @optional_params
  Scenario: Weather tool accepts optional parameters
    Given today is "1/7/2025"
    When the user says "What should I wear tomorrow to Ocean City, NJ? Include wind info."
    Then the agent should call "weather_tool"
    And the tool parameter "city" should be "Ocean City"
    And the tool parameter "state" should be "NJ"
    # Optional parameters are verified only if present
    And the tool response should contain "wind"

  @mcp @negative
  Scenario: Agent should not call weather tool for non-weather questions
    Given today is "1/7/2025"
    When the user says "What is the capital of France?"
    Then the agent should not call "weather_tool"

  @mcp @multiple_tools
  Scenario: Multiple tool calls in sequence
    Given today is "1/7/2025"
    When the user says "Search for restaurants in Ocean City, NJ and check tomorrow's weather"
    Then the agent should call "search_tool"
    And the agent should call "weather_tool"
    And the tools should be called in order: search_tool, weather_tool
