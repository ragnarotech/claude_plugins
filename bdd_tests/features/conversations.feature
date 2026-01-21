Feature: Conversational MCP Tool Usage
  As a developer
  I want to test multi-turn conversations where the agent gathers information
  So that I can verify correct tool usage with incomplete initial information

  Background:
    Given the LLM evaluator uses model "gpt-4"
    And the default threshold is 0.7

  @conversation @weather
  Scenario: Agent asks for location when not provided
    Given today is "1/7/2025"
    And a new conversation
    When the user says "I'm visiting my mom tomorrow, What should I wear?"
    Then the agent should ask about "location"
    When the user responds "Ocean City, NJ"
    Then after the conversation, the tool "weather_tool" should have been called
    And the final tool call parameters should include:
      | city  | Ocean City |
      | state | NJ         |
      | date  | 1/8/2025   |
    And the final agent response should mention appropriate clothing

  @conversation @weather
  Scenario: Agent asks clarifying question about date
    Given today is "1/7/2025"
    And a new conversation
    When the user says "What should I wear when I visit Philadelphia?"
    Then the agent should ask about "when"
    When the user responds "Next Monday"
    Then after the conversation, the tool "weather_tool" should have been called
    And the tool parameter "city" should be "Philadelphia"

  @conversation @multi_turn
  Scenario: Three-turn conversation with clarifications
    Given today is "1/7/2025"
    And a new conversation
    When the user says "Help me plan what to pack"
    Then the agent should ask about "destination"
    When the user responds "I'm going to the beach"
    Then the agent should ask about "location"
    When the user responds "Ocean City, NJ, this weekend"
    Then after the conversation, the tool "weather_tool" should have been called
    And the conversation should have 6 turns

  @conversation @no_tool_needed
  Scenario: Conversation resolved without tool call
    Given today is "1/7/2025"
    And a new conversation
    When the user says "What's the best way to stay warm in winter?"
    Then the agent should not call "weather_tool"
    And the final agent response should contain "layer"
