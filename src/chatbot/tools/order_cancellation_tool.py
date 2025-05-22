# src/chatbot/tools/order_cancellation_tool.py

import requests
from typing import Type, Union, Dict, Any
from pydantic import BaseModel, Field
from langchain.tools import BaseTool

class OrderCancellationInput(BaseModel):
    """Input for the order cancellation tool."""
    order_id: str = Field(description="The unique identifier of the order to cancel.")

class OrderCancellationTool(BaseTool):
    """
    Tool to attempt to cancel a customer's order.
    Returns the raw JSON response from the API, which includes success/failure status
    and policy-related reasons.
    """
    name: str = "order_canceller"
    description: str = (
        "Use this tool to attempt to cancel a customer's order. "
        "You must provide the order ID. The tool will return a JSON object "
        "indicating the outcome of the cancellation attempt, including any "
        "policy reasons if the cancellation is not permitted."
    )
    args_schema: Type[BaseModel] = OrderCancellationInput
    
    mock_api_base_url: str
    cancel_order_endpoint_template: str # "/orders/{order_id}/cancel"

    def _run(self, order_id: str) -> Union[Dict[str, Any], str]:
        """Use the tool. Returns JSON data (as dict) on success/expected failure, or an error string."""
        if not order_id:
            return "Error: Order ID was not provided for cancellation. Please provide an order ID."

        try:
            endpoint = self.cancel_order_endpoint_template.format(order_id=order_id)
            url = f"{self.mock_api_base_url}{endpoint}"
            
            # For a POST request, no specific payload is needed for this API endpoint
            # as the order_id is in the URL.
            response = requests.post(url, timeout=10) 

            # The mock_api_service for cancellation is expected to return:
            # - 200 OK on successful cancellation.
            # - 400 Bad Request (or similar, like 403 Forbidden or 422 Unprocessable Entity) 
            #   if cancellation is denied due to policy, with details in the JSON body.
            # - 404 Not Found if the order_id doesn't exist.
            
            if response.status_code == 200: # Successful cancellation
                try:
                    return response.json() 
                except requests.exceptions.JSONDecodeError:
                    return "Error: API returned a non-JSON response on successful cancellation. Response body: " + response.text
            elif response.status_code == 400 or response.status_code == 403 or response.status_code == 422: # Policy violation or invalid request
                try:
                    return response.json() 
                except requests.exceptions.JSONDecodeError:
                    return (f"Error: API denied cancellation (status {response.status_code}) "
                            f"but returned a non-JSON response. Response body: {response.text}")
            elif response.status_code == 404:
                return f"Error: Order with ID '{order_id}' not found for cancellation."
            else:
                return (
                    f"Error: Received unexpected status code {response.status_code} from API when trying to cancel order '{order_id}'. "
                    f"Response: {response.text}"
                )
        except requests.exceptions.Timeout:
            return f"Error: The request to cancel order '{order_id}' timed out. Please try again later."
        except requests.exceptions.RequestException as e:
            return f"Error: A network or request issue occurred while trying to cancel order '{order_id}': {e}"
        except Exception as e:
            return f"An unexpected error occurred while processing cancellation for order '{order_id}': {e}"

    async def _arun(self, order_id: str) -> Union[Dict[str, Any], str]:
        """Use the tool asynchronously."""
        # This is a simplified example for now that doesnt really do async
        try:
            # TODO: Use httpx for actual async calls.
            return self._run(order_id=order_id)
        except Exception as e:
            return f"An unexpected error occurred during async cancellation for order '{order_id}': {e}"
