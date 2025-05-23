import json
from typing import Dict, Any, Optional, Tuple
from datetime import date, datetime, timedelta

# --- LOGGING CONFIGURATION ---
LOG_LEVEL = "INFO"  # Set to "DEBUG" for maximum verbosity, "INFO" for less
# --- END LOGGING CONFIGURATION ---

DB_PATH = "data/mock_orders.db" # Path relative to project root
# Config path for policies - relative to project root
CONFIG_PATH = "configs/mock_api_config.json"

# Define the FSM states and valid transitions
VALID_TRANSITIONS = {
    "USER_QUERY_RECEIVED": ["AGENT_FINAL_RESPONSE", "AGENT_DECISION_INTENT"],
    "AGENT_DECISION_INTENT": ["AGENT_TOOL_EXECUTED"],
    "AGENT_TOOL_EXECUTED": ["AGENT_DECISION_INTENT", "AGENT_FINAL_RESPONSE"],
    "AGENT_FINAL_RESPONSE": [],  # Terminal state for a sequence
}
INITIAL_STATE_TYPE = "USER_QUERY_RECEIVED"

class TelemetryOrder:
    def __init__(self, ordered_on_str: Optional[str], status_str: Optional[str], is_premium: bool, customer_id: str = "N/A"):
        self.ordered_on: Optional[date] = None
        if ordered_on_str:
            try:
                # Assuming ordered_on_str is 'YYYY-MM-DD'
                self.ordered_on = date.fromisoformat(ordered_on_str)
            except ValueError:
                if LOG_LEVEL == "DEBUG":
                    print(f"Warning (TelemetryOrder): Could not parse ordered_on_str '{ordered_on_str}'")
        self.status = status_str # Store as string, e.g., "ordered"
        self.customer_id = customer_id
        # Create a simple mock customer object with is_premium attribute
        self.customer = type('Customer', (), {'is_premium': is_premium})()

POLICIES_CONFIG_TELEMETRY: Dict = {}
try:
    # Adjust path to be relative to the project root if this script is run from there
    # Or ensure CONFIG_PATH is an absolute path or correctly relative from execution point
    with open(CONFIG_PATH, 'r') as f:
        APP_CONFIG_TELEMETRY = json.load(f)
    POLICIES_CONFIG_TELEMETRY = APP_CONFIG_TELEMETRY.get("policies", {})
    if not POLICIES_CONFIG_TELEMETRY and LOG_LEVEL in ["INFO", "DEBUG"]:
        print(f"Warning: Policies configuration in '{CONFIG_PATH}' is empty or not found under 'policies' key.")
except FileNotFoundError:
    if LOG_LEVEL in ["INFO", "DEBUG"]:
        print(f"ERROR: Policy configuration file '{CONFIG_PATH}' not found. Policy checking will use defaults or fail.")
except json.JSONDecodeError:
    if LOG_LEVEL in ["INFO", "DEBUG"]:
        print(f"ERROR: Could not parse policy configuration file '{CONFIG_PATH}'.")

def historical_check_within_time_window(order: TelemetryOrder, policy_config: dict, evaluation_date: date) -> Tuple[bool, str]:
    cancellation_policy_cfg = policy_config.get("cancellation", {})
    standard_window = cancellation_policy_cfg.get("standard_window_days", 10)
    premium_extension = cancellation_policy_cfg.get("premium_customer_extension_days", 5)
    
    current_window_days = standard_window
    if order.customer and order.customer.is_premium:
        current_window_days += premium_extension
    
    if not order.ordered_on:
        return False, "Order date is invalid or missing."

    eligible_until = order.ordered_on + timedelta(days=current_window_days)
    
    if evaluation_date <= eligible_until:
        return True, f"Order within {current_window_days}-day cancellation window (eligible until {eligible_until.isoformat()})."
    return False, f"Order outside {current_window_days}-day cancellation window (eligible until {eligible_until.isoformat()}, evaluated on {evaluation_date.isoformat()})."

def historical_check_order_status_for_cancellation(order: TelemetryOrder, policy_config: dict) -> Tuple[bool, str]:
    cancellation_policy_cfg = policy_config.get("cancellation", {})
    denied_statuses = cancellation_policy_cfg.get("status_denylist", [])
    
    if order.status in denied_statuses:
        return False, f"Orders with the status '{order.status}' cannot be cancelled."
    return True, "Order status permits cancellation."

def get_policy_ground_truth(order_details: Optional[Dict[str, Any]], event_timestamp_str: str) -> Optional[bool]:
    if not order_details: return None
    ordered_on_str = order_details.get("ordered_on")
    status_str = order_details.get("status")
    customer_info = order_details.get("customer", {})
    is_premium = customer_info.get("is_premium", False) if isinstance(customer_info, dict) else False

    if not ordered_on_str or status_str is None: return None
    try:
        evaluation_date = datetime.fromisoformat(event_timestamp_str.split('.')[0]).date()
    except ValueError: return None

    telemetry_order = TelemetryOrder(ordered_on_str, status_str, is_premium)
    if not telemetry_order.ordered_on: return None
    if not POLICIES_CONFIG_TELEMETRY: 
        if LOG_LEVEL in ["INFO", "DEBUG"]:
            print("Warning (get_policy_ground_truth): POLICIES_CONFIG_TELEMETRY is empty. Cannot determine ground truth.")
        return None

    allowed_status, _ = historical_check_order_status_for_cancellation(telemetry_order, POLICIES_CONFIG_TELEMETRY)
    if not allowed_status: return False
    allowed_time, _ = historical_check_within_time_window(telemetry_order, POLICIES_CONFIG_TELEMETRY, evaluation_date)
    if not allowed_time: return False
    return True
