import json
import re
from typing import Optional, Dict, Any

def extract_telemetry_payload(text: str) -> Optional[Dict[str, Any]]:
    """
    Extracts the <agent_telemetry_payload> JSON object from a given text.

    Args:
        text: The string to search within. This could be the agent's
              thought process (action.log) or its final output.

    Returns:
        A dictionary if the payload is found and successfully parsed, otherwise None.
    """
    if not text or not isinstance(text, str):
        return None

    # Regex to find the content between <agent_telemetry_payload> and </agent_telemetry_payload>
    # It handles potential newlines and spaces within the JSON block.
    # Using re.DOTALL to make '.' match newlines as well.
    match = re.search(r"<agent_telemetry_payload>\s*(.*?)\s*</agent_telemetry_payload>", text, re.DOTALL)

    if match:
        json_str = match.group(1).strip()
        try:
            payload = json.loads(json_str)
            return payload
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON from agent_telemetry_payload: {e}")
            print(f"Problematic JSON string: '{json_str}'")
            return {"error": "JSONDecodeError", "raw_payload": json_str}
    return None

if __name__ == '__main__':
    # Test cases
    sample_thought_process = """
    User wants to cancel ORD123. Order details from tracker: order_date=2023-10-10, status=pending, premium=false
    Based on current date 2023-10-15, the order is eligible for cancellation.
    <agent_telemetry_payload>
    {
        "order_id_analyzed": "ORD123",
        "action_under_consideration": "order_cancellation",
        "perceived_eligibility_for_action": true,
        "reasoning_summary": "Order meets policy criteria based on 2023-10-15.",
        "intended_next_step": "call_order_canceller"
    }
    </agent_telemetry_payload>
    Tool call: {"tool": "order_canceller", "tool_input": {"order_id": "ORD123"}}
    """
    
    sample_final_response = """
    I'm sorry, but order ORD456 cannot be cancelled.
    <agent_telemetry_payload>
    {
        "order_id_analyzed": "ORD456",
        "action_under_consideration": "order_cancellation",
        "perceived_eligibility_for_action": false,
        "reasoning_summary": "Order is too old.",
        "intended_next_step": "respond_to_user_directly_deny"
    }
    </agent_telemetry_payload>
    Is there anything else?
    """

    malformed_payload = """
    <agent_telemetry_payload>
    {
        "order_id_analyzed": "ORD789",
        "action_under_consideration": "order_cancellation",
        "perceived_eligibility_for_action": false,
        "reasoning_summary": "Missing quote,
        "intended_next_step": "respond_to_user_directly_deny"
    }
    </agent_telemetry_payload>
    """
    
    no_payload = "Just a regular message."

    print("Test 1 (Thought Process):", extract_telemetry_payload(sample_thought_process))
    print("Test 2 (Final Response):", extract_telemetry_payload(sample_final_response))
    print("Test 3 (Malformed):", extract_telemetry_payload(malformed_payload))
    print("Test 4 (No Payload):", extract_telemetry_payload(no_payload))
    print("Test 5 (None input):", extract_telemetry_payload(None))
