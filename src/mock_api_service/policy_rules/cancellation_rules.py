from datetime import date, timedelta
from typing import Tuple
from ..crud.models import Order, OrderStatus

def check_within_time_window(order: Order, policy_config: dict) -> Tuple[bool, str]:
    """
    Checks if the order is within the allowed cancellation time window,
    considering standard and premium customer extensions.
    """
    standard_window = policy_config.get("standard_window_days", 10)
    premium_extension = policy_config.get("premium_customer_extension_days", 0)
    
    current_window_days = standard_window
    if order.customer and order.customer.is_premium:
        current_window_days += premium_extension
    
    eligible_until = order.ordered_on + timedelta(days=current_window_days)
    
    if date.today() <= eligible_until:
        return True, f"Order within {current_window_days}-day cancellation window (eligible until {eligible_until.isoformat()})."
    
    return False, f"Order outside {current_window_days}-day cancellation window (eligible until {eligible_until.isoformat()}, today is {date.today().isoformat()})."

def check_order_status_for_cancellation(order: Order, policy_config: dict) -> Tuple[bool, str]:
    """
    Checks if the order's current status allows for cancellation based on a denylist
    of statuses defined in the policy configuration.
    """
    denied_statuses = policy_config.get("status_denylist", [])
    
    if order.status.value in denied_statuses:
        return False, f"Orders with the status '{order.status.value}' can not be cancelled as they are already on their way to you (on denylist)."
    
    return True, "Order status permits cancellation (not on denylist)."

# Potential future rule:
# def check_item_properties_for_cancellation(order: Order, policy_config: dict) -> Tuple[bool, str]:
#     """Checks if any items in the order prevent cancellation (e.g., non-returnable custom items)."""
#     # This would require the 'items' field to be populated on the Order model.
#     # For now, this is a placeholder.
#     # if order.items:
#     #     for item in order.items:
#     #         if item.get("is_cancellable") is False: # Assuming an 'is_cancellable' flag per item
#     #             return False, f"Item '{item.get('name', 'Unknown Item')}' in the order is not cancellable."
#     return True, "All items in the order are cancellable (or item check not implemented)."