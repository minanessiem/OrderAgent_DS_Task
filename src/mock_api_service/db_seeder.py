import random
from datetime import date, datetime, timedelta
from typing import Optional, Dict, Any, List

from sqlmodel import Session, select

from .models import Order, OrderStatus, OrderCreate, Customer, CustomerCreate, generate_short_id
from .db import load_db_config


config = load_db_config()
# Access seeder-specific config from the "seeder" key
SEEDER_CONFIG = config.get("seeder", {}) 
DEFAULT_NUM_ORDERS_TO_SEED = SEEDER_CONFIG.get("num_orders_to_seed", 50)
DEFAULT_NUM_CUSTOMERS_TO_SEED = SEEDER_CONFIG.get("num_customers_to_seed", 10)
INITIAL_SEED_VALUE = SEEDER_CONFIG.get("initial_seed_value", 42)


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

def _generate_single_mock_order(customer_id: str, seed_rng: random.Random) -> OrderCreate:
    days_ago = seed_rng.randint(1, 30) 
    ordered_on_date = date.today() - timedelta(days=days_ago)
    
    # Exclude 'cancelled' from initial random status generation
    initial_statuses = [s for s in OrderStatus if s != OrderStatus.CANCELLED]
    status = seed_rng.choice(initial_statuses)
    
    return OrderCreate(
        customer_id=customer_id,
        ordered_on=ordered_on_date,
        status=status
    )

def seed_initial_data(
    session: Session,
    num_customers_to_create: Optional[int] = None,
    num_orders_to_create: Optional[int] = None,
    seed_to_use: Optional[int] = None
):
    """
    Seeds the database with initial mock customers and orders if the respective tables are empty.
    Uses provided counts and seed, or defaults from config.
    """
    
    actual_seed = seed_to_use if seed_to_use is not None else INITIAL_SEED_VALUE
    seed_rng = random.Random(actual_seed)
    
    actual_num_customers = num_customers_to_create if num_customers_to_create is not None else DEFAULT_NUM_CUSTOMERS_TO_SEED
    actual_num_orders = num_orders_to_create if num_orders_to_create is not None else DEFAULT_NUM_ORDERS_TO_SEED

    # 1. Seed Customers
    existing_customer_check = session.exec(select(Customer).limit(1)).first()
    customer_ids: List[str] = []
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

    all_db_customers = session.exec(select(Customer)).all()
    customer_ids = [c.customer_id for c in all_db_customers]

    if not customer_ids:
        print("No customers found or created. Cannot seed orders.")
        return {"message": "No customers available to associate with orders.", "customers_added": customers_added_count, "orders_added": 0}

    # 2. Seed Orders
    existing_order_check = session.exec(select(Order).limit(1)).first()
    orders_added_count = 0

    if not existing_order_check:
        print(f"Seeding orders. Num: {actual_num_orders}, Seed: {actual_seed}")
        for _ in range(actual_num_orders):
            if not customer_ids: 
                print("Error: No customer IDs available for order seeding.")
                break 
            chosen_customer_id = seed_rng.choice(customer_ids)
            order_data = _generate_single_mock_order(chosen_customer_id, seed_rng)
            db_order = Order.model_validate(order_data) 
            session.add(db_order)
            orders_added_count += 1
        session.commit()
        print(f"Successfully seeded {orders_added_count} orders.")
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
    seed_value: Optional[int] = None
) -> Dict[str, Any]:
    """
    Clears all existing order and customer data, then reseeds the database
    by calling seed_initial_data.
    """
    print("Starting database reseed operation...")
    orders_cleared = clear_all_order_data(session)
    customers_cleared = clear_all_customer_data(session)
    
    seeding_result = seed_initial_data(
        session,
        num_customers_to_create=num_customers,
        num_orders_to_create=num_orders,
        seed_to_use=seed_value
    )
    
    message = (
        f"Reseed complete. Cleared {orders_cleared} orders and {customers_cleared} customers. "
        f"Customers seeded: {seeding_result.get('customers_added', 0)}. Orders seeded: {seeding_result.get('orders_added', 0)}."
    )
    print(message)
    return {
        "message": message, 
        "orders_cleared": orders_cleared, 
        "customers_cleared": customers_cleared,
        "customers_added": seeding_result.get('customers_added', 0),
        "orders_added": seeding_result.get('orders_added', 0)
    }
