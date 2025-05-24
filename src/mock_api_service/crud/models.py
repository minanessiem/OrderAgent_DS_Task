from datetime import date, datetime, timedelta
from enum import Enum
from typing import Optional, List, Any, Dict
from sqlmodel import Field, SQLModel, Relationship, JSON, Column
import uuid
import random
import string
from pydantic import BaseModel, ConfigDict


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

class CustomerSummaryForOrder(BaseModel):
    customer_id: str
    is_premium: bool

    model_config = ConfigDict(from_attributes=True)


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


class ExperimentTelemetryEventBase(SQLModel):
    session_id: str = Field(index=True)
    event_type: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    order_id_identified: Optional[str] = None
    user_query: Optional[str] = None
    agent_model_name: Optional[str] = Field(default=None)
    system_prompt_name: Optional[str] = Field(default=None)
    agent_generated_payload: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    tool_name: Optional[str] = None
    tool_input: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON)) # Assuming tool inputs are JSON-like
    tool_raw_response: Optional[str] = None # Raw text response from tool
    tool_response_success: Optional[bool] = None
    final_agent_message_to_user: Optional[str] = None
    additional_notes: Optional[str] = None

class ExperimentTelemetryEvent(ExperimentTelemetryEventBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

class ExperimentTelemetryEventCreate(ExperimentTelemetryEventBase):
    pass

class ExperimentTelemetryEventRead(ExperimentTelemetryEventBase):
    id: int
    timestamp: datetime # Ensure timestamp is present in read model