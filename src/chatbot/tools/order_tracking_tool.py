# src/chatbot/tools/order_tracking_tool.py

import requests
from typing import Type, Union, Dict, Any
from pydantic import BaseModel, Field
from langchain.tools import BaseTool

class OrderTrackingInput(BaseModel):
    """Input for the order tracking tool."""
    order_id: str = Field(description="The unique identifier of the order to track.")

class OrderTrackingTool(BaseTool):
    """
    Tool to get the current status and details of a customer's order.
    Returns the raw JSON response from the API upon success.
    """
    name: str = "order_tracker"
    description: str = (
        "Use this tool to get the current status and details of a customer's order. "
        "You must provide the order ID. The tool will return order details as a JSON object if successful."
    )
    args_schema: Type[BaseModel] = OrderTrackingInput
    
    mock_api_base_url: str 
    track_order_endpoint_template: str

    def _run(self, order_id: str) -> Union[Dict[str, Any], str]:
        """Use the tool. Returns JSON data (as dict) on success, or an error string."""
        if not order_id:
            return "Error: Order ID was not provided. Please provide an order ID."

        try:
            base_url = self.mock_api_base_url.rstrip('/')
            endpoint = self.track_order_endpoint_template.format(order_id=order_id)
            url = f"{base_url}{endpoint}"
            
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                try:
                    return response.json()
                except requests.exceptions.JSONDecodeError:
                    return "Error: API returned a non-JSON response even with a 200 status code. Response body: " + response.text
            elif response.status_code == 404:
                return f"Error: Order with ID '{order_id}' not found."
            else:
                return (
                    f"Error: Received status code {response.status_code} from API when trying to track order '{order_id}'. "
                    f"Response: {response.text}"
                )
        except requests.exceptions.Timeout:
            return f"Error: The request to track order '{order_id}' timed out. Please try again later."
        except requests.exceptions.RequestException as e:
            return f"Error: A network or request issue occurred while trying to track order '{order_id}': {e}"
        except Exception as e:
            # A general fallback for any other unexpected errors.
            return f"An unexpected error occurred while processing tracking for order '{order_id}': {e}"

    async def _arun(self, order_id: str) -> Union[Dict[str, Any], str]:
        """Use the tool asynchronously."""
        # This is a simplified example for now that doesnt really do async
        try:
            # TODO: Use httpx for actual async calls.
            return self._run(order_id=order_id)
        except Exception as e:
            return f"An unexpected error occurred during async tracking for order '{order_id}': {e}"
