from datetime import date, datetime, timedelta
from typing import Optional, Dict, Any, List

from sqlmodel import Session, select, col, func
import random # Ensure random is imported if not already

from .models import Order, OrderStatus, OrderUpdate, Customer, OrderRead, OrderForCancellationResponse, CustomerSummaryForOrder
from .. import policy_checker # Import the new policy_checker


def get_order_by_id(session: Session, order_id: str) -> Optional[Order]:
    """Fetches a single order by its ID."""
    statement = select(Order).where(Order.order_id == order_id)
    order = session.exec(statement).first()
    return order

def attempt_cancel_order(session: Session, order_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
    """
    Attempts to cancel an order based on business rules (cancellation window).
    """
    order = get_order_by_id(session, order_id)

    if not order:
        return {"success": False, "message": "Order not found."}

    # Prepare data for the custom response model
    # Ensure order.customer is loaded; SQLModel usually handles this on access
    is_premium = order.customer.is_premium if order.customer else False 
    
    current_order_data_for_response = OrderForCancellationResponse(
                ordered_on=order.ordered_on,
                status=order.status,
                cancellation_reason=order.cancellation_reason,
                order_id=order.order_id,
                last_updated=order.last_updated,
                customer_id=order.customer_id,
                is_premium_customer=is_premium
            )

    if order.status == OrderStatus.CANCELLED:
        return {
            "success": True, 
            "message": "Order is already cancelled.", 
            "order": current_order_data_for_response.model_dump(mode='json')
        }

    policy_decision = policy_checker.check_policies(order, "cancel_order")
    
    if not policy_decision:
        # dumped_order_data = current_order_data_for_response.model_dump(mode='json')
        # print(f"DEBUG: Policy Failure. Order Data for Response: {dumped_order_data}")
        # print(f"DEBUG: Original policy_decision.message: {policy_decision.message}")
        # print(f"DEBUG: Original policy_decision.violated_rule: {policy_decision.violated_rule}")

        return {
            "success": False, 
            "message": policy_decision.message, 
            "details": {"violated_rule": policy_decision.violated_rule},
            "order": current_order_data_for_response.model_dump(mode='json')
        }

    # Policy checks passed
    order.status = OrderStatus.CANCELLED
    order.last_updated = datetime.utcnow()
    if reason: 
        order.cancellation_reason = reason 
    
    session.add(order)
    session.commit()
    session.refresh(order) # Refresh to get the latest state from DB

    # Refresh is_premium status from the potentially updated customer if needed,
    # though for cancellation, customer status isn't changed by this action.
    is_premium_after_update = order.customer.is_premium if order.customer else False

    response_order_data = OrderForCancellationResponse(
        ordered_on=order.ordered_on,
        status=order.status,
        cancellation_reason=order.cancellation_reason,
        order_id=order.order_id,
        last_updated=order.last_updated,
        customer_id=order.customer_id,
        is_premium_customer=is_premium_after_update # Use the (potentially refreshed) customer data
    )
    return {"success": True, "message": "Order cancelled successfully.", "order": response_order_data.model_dump(mode='json')}

def get_recent_orders(session: Session, limit: int = 10) -> List[Order]:
    """Fetches the N most recent orders, ordered by 'ordered_on' date descending."""
    if limit <= 0:
        return []
    statement = select(Order).order_by(col(Order.ordered_on).desc()).limit(limit)
    orders = session.exec(statement).all()
    return list(orders)

def get_orders_by_status(session: Session, statuses: List[OrderStatus], limit: int = 50) -> List[Order]:
    """
    Fetches orders that match any of the provided statuses.
    Orders are returned by most recent 'ordered_on' date.
    """
    if not statuses:
        return []
    if limit <= 0:
        limit = 50 # Default to a sensible limit if an invalid one is passed

    statement = (
        select(Order)
        .where(Order.status.in_(statuses)) # Filter by list of statuses
        .order_by(col(Order.ordered_on).desc())
        .limit(limit)
    )
    orders = session.exec(statement).all()
    return list(orders)

# Add other CRUD operations for Orders here as needed, e.g.:
# def create_order(session: Session, order_create: OrderCreate) -> Order: ...
# def update_order_status(session: Session, order_id: str, new_status: OrderStatus) -> Optional[Order]: ...
# def delete_order(session: Session, order_id: str) -> bool: ...
# this is currently unused
def check_order_return_eligibility(session: Session, order_id: str) -> Dict[str, Any]:
    order = get_order_by_id(session, order_id)
    if not order:
         return {"success": False, "message": "Order not found."} # Basic check

    policy_decision = policy_checker.check_policies(order, "return_order")
    
    # Translate PolicyDecision to the existing expected response structure
    return_by_date = policy_decision.details.get("return_by_date") if policy_decision.details else None # Example
    
    return {
        "order_id": order.order_id,
        "eligible_for_return": policy_decision.allowed,
        "return_by_date": return_by_date, # You'd need return_rules to populate this in details
        "message": policy_decision.message,
        "details": {"violated_rule": policy_decision.violated_rule}
    }

def get_random_order(session: Session) -> Optional[OrderRead]:
    """
    Fetches a random order from the database.
    Returns the order details using OrderRead model, or None if no orders exist.
    """
    # Get total count of orders
    count_statement = select(func.count(Order.order_id))
    total_orders = session.exec(count_statement).one_or_none()

    if not total_orders or total_orders == 0:
        return None

    # Generate a random offset
    # Note: For very large tables, offset can be inefficient.
    # An alternative for SQLite specifically might be ORDER BY RANDOM() LIMIT 1,
    # but SQLModel might not directly support RANDOM() in a portable way without raw SQL.
    # For simplicity and given it's a mock service, offset is acceptable.
    # If there's only one order, offset should be 0.
    random_offset = random.randint(0, total_orders - 1) if total_orders > 0 else 0
    
    statement = select(Order).offset(random_offset).limit(1)
    order = session.exec(statement).first()
    
    if order:
        # Manually prepare the data for OrderRead, especially the customer part
        order_data_for_validation = {
            "order_id": order.order_id,
            "customer_id": order.customer_id,
            "ordered_on": order.ordered_on,
            "status": order.status,
            "cancellation_reason": order.cancellation_reason,
            "last_updated": order.last_updated,
            "customer": None # Default to None
        }
        
        if order.customer:
            # Manually create CustomerSummaryForOrder from the order.customer ORM object
            order_data_for_validation["customer"] = CustomerSummaryForOrder.model_validate(order.customer)
            # or CustomerSummaryForOrder(customer_id=order.customer.customer_id, is_premium=order.customer.is_premium)

        # Now validate the prepared dictionary
        return OrderRead.model_validate(order_data_for_validation)
    return None