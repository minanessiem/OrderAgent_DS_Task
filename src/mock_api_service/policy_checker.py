from typing import List, Callable, Tuple, Dict, Any
from .models import Order
from .db import load_db_config # To get the global config
from .policy_rules import cancellation_rules # Import specific rule modules

# Global app config loaded once
APP_CONFIG = load_db_config() 
POLICIES_CONFIG = APP_CONFIG.get("policies", {})

# Define a structure for a policy check result
class PolicyDecision:
    def __init__(self, allowed: bool, message: str, violated_rule: str = None, details: Dict = None):
        self.allowed = allowed
        self.message = message
        self.violated_rule = violated_rule # Name of the function/rule that failed
        self.details = details or {}

    def __bool__(self):
        return self.allowed

# Rule registry: Maps action types to a list of rule functions
RULE_REGISTRY = {
    "cancel_order": [
        cancellation_rules.check_order_status_for_cancellation, 
        cancellation_rules.check_within_time_window,
        # other cancellation rule functions would come here
    ],
    # return if implemented would need to be added here
    "return_order": [
        # return_rules.check_status_for_return,
        # return_rules.check_return_time_window,
    ]
}

def check_policies(order: Order, action: str) -> PolicyDecision:
    if action not in RULE_REGISTRY:
        return PolicyDecision(False, f"No policies defined for action: {action}", "config_error")

    rules_to_apply: List[Callable[[Order, dict], Tuple[bool, str]]] = RULE_REGISTRY[action]
    
    action_config_key_map = {
        "cancel_order": "cancellation",
        "return_order": "returns"
        # Add other mappings more actions are defined and policy config blocks are added
    }
    config_key_for_action = action_config_key_map.get(action)
    
    if not config_key_for_action:
            return PolicyDecision(False, f"Policy configuration key for action '{action}' not found in action_config_key_map.", "internal_config_error")

    # Get the specific domain's policy configuration (e.g., the "cancellation" dictionary)
    domain_specific_policy_config = POLICIES_CONFIG.get(config_key_for_action, {})
    if not domain_specific_policy_config and rules_to_apply: # If rules exist but no config for them
        print(f"Warning: No specific policy configuration found for domain '{config_key_for_action}', but rules are registered. Rules will use their defaults.")


    for rule_func in rules_to_apply:
        try:
            allowed, message = rule_func(order, domain_specific_policy_config)
            if not allowed:
                return PolicyDecision(False, message, violated_rule=rule_func.__name__)
        except Exception as e:
            print(f"Error executing policy rule {rule_func.__name__} for action {action}: {e}")
            # Decide if an error in a rule should deny the action or be handled differently
            return PolicyDecision(False, f"Error in policy rule: {rule_func.__name__}.", "rule_execution_error") 
            
    return PolicyDecision(True, f"Action '{action}' permitted by all relevant policies.")
