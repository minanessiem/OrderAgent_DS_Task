from datetime import date, datetime, timedelta
from enum import Enum
from typing import Optional, List
from sqlmodel import Field, SQLModel, Relationship
import uuid
import random
import string
from pydantic import BaseModel


def generate_short_id(length: int = 6) -> str:
    """Generates a random alphanumeric string of a given length."""
    alphanumeric_chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(alphanumeric_chars) for _ in range(length))


class CustomerBase(SQLModel):
    name: str
    email: str = Field(unique=True, index=True)
    is_premium: bool = Field(default=False)

class Customer(CustomerBase, table=True):
    customer_id: str = Field(default_factory=lambda: f"CUST-{generate_short_id(4)}", primary_key=True, index=True)
    orders: List["Order"] = Relationship(back_populates="customer")

class CustomerCreate(CustomerBase):
    pass

class CustomerRead(CustomerBase):
    customer_id: str

class CustomerSummaryForOrder(BaseModel): # Using Pydantic's BaseModel for this simple DTO
    customer_id: str
    is_premium: bool

    class Config:
        orm_mode = True # Allow creating from ORM objects (like the Customer linked to Order)


class OrderStatus(str, Enum):
    ORDERED = "ordered"
    FULFILLED = "fulfilled"
    DELIVERING = "delivering"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

# Order Based Model (conceptual)
class OrderBase(SQLModel):
    customer_id: str = Field(index=True, foreign_key="customer.customer_id")
    ordered_on: date
    status: OrderStatus = Field(default=OrderStatus.ORDERED, index=True)
    cancellation_reason: Optional[str] = Field(default=None)
    # For simplicity, not including items list here.
    # items_json: Optional[str] = Field(default=None) # Example: store items as JSON string

# Order model (Base + Database Keys)
class Order(OrderBase, table=True):
    order_id: str = Field(default_factory=generate_short_id, primary_key=True, index=True)
    last_updated: datetime = Field(default_factory=datetime.utcnow, sa_column_kwargs={"onupdate": datetime.utcnow})
    customer: Optional[Customer] = Relationship(back_populates="orders")

class OrderCreate(OrderBase):
    # order_id will be generated automatically
    pass

class OrderRead(OrderBase):
    order_id: str
    last_updated: datetime
    customer: Optional[CustomerSummaryForOrder] = None 

class OrderUpdate(SQLModel):
    status: Optional[OrderStatus] = None
    cancellation_reason: Optional[str] = None

class CancelOrderRequest(SQLModel):
    cancellation_reason: Optional[str] = None

# Model for the specific data to return within the cancellation success response
class OrderForCancellationResponse(BaseModel):
    ordered_on: date
    status: OrderStatus
    cancellation_reason: Optional[str] = None
    order_id: str
    last_updated: datetime
    customer_id: str
    is_premium_customer: bool

    class Config:
        orm_mode = True
        use_enum_values = True
