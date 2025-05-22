from fastapi import FastAPI, HTTPException, Depends, Body, Query
from fastapi.responses import JSONResponse
from sqlmodel import Session
from typing import Optional, List

# Import from the new structured files
from .models import OrderRead, CancelOrderRequest, OrderStatus
from .db import get_session, create_db_and_tables, engine as db_engine # Renamed engine for clarity
from . import order_crud
from . import db_seeder

app = FastAPI(title="Mock Order Management API")

@app.on_event("startup")
def on_startup():
    """
    Actions to perform on application startup:
    1. Create database and tables if they don't exist.
    2. Seed the database with initial mock data if it's empty.
    """
    create_db_and_tables() # This is from db.py
    
    # For initial seeding, we need a session outside the request-response cycle
    with Session(db_engine) as session: # Use the global engine from db.py
        db_seeder.seed_initial_data(session)


@app.get("/", summary="API Root/Health Check")
async def root():
    return {"message": "Mock API Service is running. See /docs for API documentation."}

@app.get("/orders/{order_id}", response_model=OrderRead, summary="Track an Order")
async def track_order(order_id: str, session: Session = Depends(get_session)):
    """
    Retrieves the details and status of a specific order.
    """
    db_order = order_crud.get_order_by_id(session, order_id)
    if not db_order:
        raise HTTPException(status_code=404, detail="Order not found")
    return db_order

@app.post("/orders/{order_id}/cancel", summary="Cancel an Order")
async def cancel_order_endpoint(
    order_id: str, 
    request_body: Optional[CancelOrderRequest] = None,
    session: Session = Depends(get_session)
):
    cancellation_reason = request_body.cancellation_reason if request_body else None
    result = order_crud.attempt_cancel_order(session, order_id, reason=cancellation_reason)
    
    if not result["success"]:
        if result.get("message") == "Order not found.":
            raise HTTPException(status_code=404, detail="Order not found")
        else:
            # For policy violations, return a JSONResponse with status 400
            # The 'result' dictionary from order_crud now contains the 'order' field
            # and the 'message' for the detail.
            # We can structure the error response more explicitly if needed.
            error_content = {
                "message": result.get("message"),
                "violated_rule": result.get("details", {}).get("violated_rule"), # from policy_decision.details
                "order": result.get("order") # OrderForCancellationResponse data
            }
            return JSONResponse(status_code=400, content=error_content)
            
    # If successful, result already contains the correctly structured "order" data
    return result

@app.post("/admin/reseed", summary="Clear ALL Orders and Reseed Mock Data")
async def reseed_data_endpoint(
    num_orders: Optional[int] = Body(None, embed=True, description="Number of new orders to generate."), 
    seed: Optional[int] = Body(None, embed=True, description="Seed value for random generation."),
    session: Session = Depends(get_session)
):
    """
    Clears ALL existing mock order data from the database and generates a new set.
    Uses configured defaults if num_orders or seed are not provided.
    """
    return db_seeder.reseed_database_with_new_data(session, num_orders=num_orders, seed_value=seed)

@app.get("/admin/orders/recent", response_model=List[OrderRead], summary="List N Recent Orders")
async def list_recent_orders(
    limit: int = Query(10, ge=1, le=100, description="Number of recent orders to retrieve (1-100)."),
    session: Session = Depends(get_session)
):
    """
    Retrieves the N most recent orders based on their 'ordered_on' date.
    """
    recent_orders = order_crud.get_recent_orders(session, limit=limit)
    return recent_orders

@app.get("/admin/orders/filter-by-status", response_model=List[OrderRead], summary="Filter Orders by Status(es)")
async def filter_orders_by_status(
    statuses: List[OrderStatus] = Query(..., description="One or more order statuses to filter by (e.g., ?status=ordered&status=delivering)."),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of orders to return."),
    session: Session = Depends(get_session)
):
    """
    Retrieves orders that match any of the provided statuses.
    Example: `/admin/orders/filter-by-status?statuses=ordered&statuses=delivering`
    """
    if not statuses:
        raise HTTPException(status_code=400, detail="At least one status must be provided.")
    
    db_orders = order_crud.get_orders_by_status(session, statuses=statuses, limit=limit)
    return db_orders

# To run this app locally (outside Docker) for quick tests, if needed:
if __name__ == "__main__":
    import uvicorn
    import os
    # If running locally, ensure this matches your environment/docker-compose setup
    port = int(os.environ.get("MOCK_API_PORT", 8001))
    # Point uvicorn to this app instance. Adjust if file is moved/renamed.
    uvicorn.run("src.mock_api_service.app:app", host="0.0.0.0", port=port, reload=True)