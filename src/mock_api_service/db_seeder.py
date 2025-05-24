import random
from datetime import date, datetime, timedelta
from typing import Optional, Dict, Any, List

from sqlmodel import Session, select

from .crud.models import Order, OrderStatus, OrderCreate, Customer, CustomerCreate, generate_short_id
from .db import load_db_config


config = load_db_config()
# Access seeder-specific config from the "seeder" key
SEEDER_CONFIG = config.get("seeder", {}) 
DEFAULT_NUM_ORDERS_TO_SEED = SEEDER_CONFIG.get("num_orders_to_seed", 60)
DEFAULT_NUM_CUSTOMERS_TO_SEED = SEEDER_CONFIG.get("num_customers_to_seed", 10)
INITIAL_SEED_VALUE = SEEDER_CONFIG.get("initial_seed_value", 42)
DEFAULT_MIN_DAYS_AGO = SEEDER_CONFIG.get("min_days_ago", 0)
DEFAULT_MAX_DAYS_AGO = SEEDER_CONFIG.get("max_days_ago", 45)

# Cancellation policy constants
STANDARD_CANCELLATION_WINDOW_DAYS = 10
PREMIUM_CANCELLATION_EXTENSION_DAYS = 5
PREMIUM_CANCELLATION_WINDOW_DAYS = STANDARD_CANCELLATION_WINDOW_DAYS + PREMIUM_CANCELLATION_EXTENSION_DAYS

# Define statuses for targeted generation
CANCELLABLE_IF_TIME_PERMITS_STATUSES: List[OrderStatus] = [
    OrderStatus.ORDERED,
]
NON_CANCELLABLE_BY_STATUS_POLICY_STATUSES: List[OrderStatus] = [
    OrderStatus.FULFILLED,
    OrderStatus.DELIVERING,
    OrderStatus.DELIVERED,
]


def _generate_mock_customer_data(seed_rng: random.Random) -> CustomerCreate:
    first_names = ["Alice", "Bob", "Charlie", "Diana", "Eve", "Frank", "Grace", "Henry"]
    last_names = ["Smith", "Jones", "Williams", "Brown", "Davis", "Miller", "Wilson"]
    name = f"{seed_rng.choice(first_names)} {seed_rng.choice(last_names)}"
    email_id = generate_short_id(5).lower()
    email = f"{name.split(' ')[0].lower()}.{email_id}@example.com"
    is_premium = seed_rng.choice([True, False, False]) 
    
    return CustomerCreate(
        name=name,
        email=email,
        is_premium=is_premium
    )

def _generate_single_mock_order(
    customer_id: str,
    is_premium_customer: bool,
    target_category: str, # "cancellable", "non_cancellable_status", "non_cancellable_time"
    seed_rng: random.Random,
    config_max_days_ago: int = DEFAULT_MAX_DAYS_AGO # Use the overall max configured
) -> OrderCreate:
    
    days_ago = 0
    status: OrderStatus

    effective_cancel_window = PREMIUM_CANCELLATION_WINDOW_DAYS if is_premium_customer else STANDARD_CANCELLATION_WINDOW_DAYS

    if target_category == "cancellable":
        # Time: Within window (0 to window_days - 1)
        # Status: Cancellable by policy
        days_ago = seed_rng.randint(0, effective_cancel_window - 1)
        status = seed_rng.choice(CANCELLABLE_IF_TIME_PERMITS_STATUSES)
    elif target_category == "non_cancellable_status":
        # Time: Within window (0 to window_days - 1)
        # Status: Non-cancellable by policy
        days_ago = seed_rng.randint(0, effective_cancel_window - 1)
        status = seed_rng.choice(NON_CANCELLABLE_BY_STATUS_POLICY_STATUSES)
    elif target_category == "non_cancellable_time":
        # Time: Older than window (window_days to config_max_days_ago)
        # Status: Would be cancellable if not for time
        min_old_days = effective_cancel_window
        if min_old_days > config_max_days_ago:
            # This can happen if config_max_days_ago is too small.
            # Make it as old as possible per config, or log warning.
            print(f"Warning: For 'non_cancellable_time' category, cancellation window ({min_old_days}d) "
                  f"exceeds config_max_days_ago ({config_max_days_ago}d). Setting days_ago to config_max_days_ago.")
            days_ago = config_max_days_ago
        else:
            days_ago = seed_rng.randint(min_old_days, config_max_days_ago)
        status = seed_rng.choice(CANCELLABLE_IF_TIME_PERMITS_STATUSES)
    else:
        raise ValueError(f"Unknown target_category for order generation: {target_category}")

    ordered_on_date = date.today() - timedelta(days=days_ago)
    
    return OrderCreate(
        customer_id=customer_id,
        ordered_on=ordered_on_date,
        status=status
    )

def seed_initial_data(
    session: Session,
    num_customers_to_create: Optional[int] = None,
    num_orders_to_create: Optional[int] = None, # This will be the total number of orders
    seed_to_use: Optional[int] = None,
    # min_order_days_ago is implicitly handled by category logic now
    # max_order_days_ago is used by _generate_single_mock_order
    max_order_days_ago_override: Optional[int] = None # Renamed for clarity
):
    actual_seed = seed_to_use if seed_to_use is not None else INITIAL_SEED_VALUE
    seed_rng = random.Random(actual_seed)
    
    actual_num_customers = num_customers_to_create if num_customers_to_create is not None else DEFAULT_NUM_CUSTOMERS_TO_SEED
    actual_total_num_orders = num_orders_to_create if num_orders_to_create is not None else DEFAULT_NUM_ORDERS_TO_SEED
    
    # Use override if provided, else seeder config default, else global default
    effective_max_days_ago = max_order_days_ago_override if max_order_days_ago_override is not None \
                             else SEEDER_CONFIG.get("max_days_ago", DEFAULT_MAX_DAYS_AGO)


    existing_customer_check = session.exec(select(Customer).limit(1)).first()
    customers_added_count = 0
    if not existing_customer_check:
        print(f"Seeding customers. Num: {actual_num_customers}, Seed: {actual_seed}")
        for _ in range(actual_num_customers):
            customer_data = _generate_mock_customer_data(seed_rng)
            db_customer = Customer.model_validate(customer_data)
            session.add(db_customer)
            customers_added_count += 1
        session.commit() 
        print(f"Successfully seeded {customers_added_count} customers.")
    else:
        print("Database already contains customers. Customer seeding skipped.")

    # Fetch all customers to get their IDs and premium status for order generation
    all_db_customers = session.exec(select(Customer)).all()
    if not all_db_customers:
        print("No customers found or created. Cannot seed orders.")
        return {"message": "No customers available to associate with orders.", "customers_added": customers_added_count, "orders_added": 0}
    
    # Create a map for easy lookup: customer_id -> customer_object
    customer_map: Dict[str, Customer] = {c.customer_id: c for c in all_db_customers}
    customer_ids: List[str] = list(customer_map.keys())


    existing_order_check = session.exec(select(Order).limit(1)).first()
    orders_added_count = 0
    if not existing_order_check:
        print(f"Seeding orders with targeted distribution. Total: {actual_total_num_orders}, Seed: {actual_seed}, MaxDaysAgo: {effective_max_days_ago}")

        order_categories = ["cancellable", "non_cancellable_status", "non_cancellable_time"]
        orders_per_category: Dict[str, int] = {cat: actual_total_num_orders // 3 for cat in order_categories}
        
        remainder = actual_total_num_orders % 3
        for i in range(remainder): # Distribute any remainder among categories
            orders_per_category[order_categories[i % len(order_categories)]] += 1

        generated_orders_data: List[OrderCreate] = []

        for category, count in orders_per_category.items():
            print(f"Generating {count} orders for category: '{category}'")
            for _ in range(count):
                if not customer_ids: 
                    print("Error: Ran out of customer IDs for order seeding unexpectedly.")
                    break 
                chosen_customer_id = seed_rng.choice(customer_ids)
                customer_obj = customer_map[chosen_customer_id]
                
                order_data = _generate_single_mock_order(
                    customer_id=chosen_customer_id,
                    is_premium_customer=customer_obj.is_premium,
                    target_category=category,
                    seed_rng=seed_rng,
                    config_max_days_ago=effective_max_days_ago
                )
                generated_orders_data.append(order_data)
            if not customer_ids: break # Break outer loop too
        
        seed_rng.shuffle(generated_orders_data) # Shuffle all generated orders before adding

        for order_data_item in generated_orders_data:
            db_order = Order.model_validate(order_data_item) 
            session.add(db_order)
            orders_added_count += 1
        session.commit()
        print(f"Successfully seeded {orders_added_count} orders with targeted distribution.")
    else:
        print("Database already contains orders. Order seeding skipped.")
    
    return {
        "message": f"Initial data seeding process complete. Customers added: {customers_added_count}. Orders added: {orders_added_count}.",
        "customers_added": customers_added_count,
        "orders_added": orders_added_count
    }


def clear_all_customer_data(session: Session) -> int:
    statement = select(Customer)
    results = session.exec(statement)
    customers_to_delete = results.all()
    
    count_deleted = 0
    if customers_to_delete:
        for cust_obj in customers_to_delete:
            session.delete(cust_obj)
            count_deleted +=1
        session.commit()
    print(f"Cleared {count_deleted} existing customers.")
    return count_deleted

def clear_all_order_data(session: Session) -> int:
    statement = select(Order)
    results = session.exec(statement)
    orders_to_delete = results.all()
    
    count_deleted = 0
    if orders_to_delete:
        for order_obj in orders_to_delete:
            session.delete(order_obj)
            count_deleted +=1
        session.commit()
    print(f"Cleared {count_deleted} existing orders.")
    return count_deleted

def reseed_database_with_new_data(
    session: Session, 
    num_orders: Optional[int] = None, 
    num_customers: Optional[int] = None, 
    seed_value: Optional[int] = None,
    # min_order_days_ago is no longer directly passed, it's handled by category logic
    max_order_days_ago: Optional[int] = None # This will be passed as max_order_days_ago_override
) -> Dict[str, Any]:
    """
    Clears all existing order and customer data, then reseeds the database
    by calling seed_initial_data with targeted distribution.
    """
    print("Starting database reseed operation with targeted distribution...")
    orders_cleared = clear_all_order_data(session)
    customers_cleared = clear_all_customer_data(session)
    
    seeding_result = seed_initial_data(
        session,
        num_customers_to_create=num_customers,
        num_orders_to_create=num_orders,
        seed_to_use=seed_value,
        max_order_days_ago_override=max_order_days_ago # Pass this through
    )
    
    message = (
        f"Reseed complete. Cleared {orders_cleared} orders and {customers_cleared} customers. "
        f"Customers seeded: {seeding_result.get('customers_added', 0)}. Orders seeded: {seeding_result.get('orders_added', 0)} "
        f"with targeted distribution."
    )
    print(message)
    return {
        "message": message, 
        "orders_cleared": orders_cleared, 
        "customers_cleared": customers_cleared,
        "customers_added": seeding_result.get('customers_added', 0),
        "orders_added": seeding_result.get('orders_added', 0)
    }
