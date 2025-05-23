import httpx # Using httpx for async requests
import json
from typing import Dict, Any, Optional

class TelemetryClient:
    def __init__(self, base_url: str, log_event_endpoint: str):
        self.base_url = base_url.rstrip('/')
        self.log_event_endpoint = log_event_endpoint.lstrip('/')
        self.client = httpx.AsyncClient()

    async def log_event(self, event_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Sends a telemetry event to the mock API service.

        Args:
            event_data: A dictionary representing the ExperimentTelemetryEventCreate model.

        Returns:
            The response from the API as a dictionary if successful, otherwise None.
        """
        url = f"{self.base_url}/{self.log_event_endpoint}"
        try:

            # Ensure complex fields like agent_configuration and agent_generated_payload
            # are properly JSON serializable if they are passed as dicts.
            # The Pydantic model on the server side will expect valid JSON for these.
            response = await self.client.post(url, json=event_data, timeout=10.0)
            response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
            return response.json()
        except httpx.HTTPStatusError as e:
            print(f"HTTP error occurred while logging telemetry event: {e.response.status_code} - {e.response.text}")
            try:
                error_details = e.response.json()
                return {"error": "HTTPStatusError", "status_code": e.response.status_code, "details": error_details}
            except json.JSONDecodeError:
                return {"error": "HTTPStatusError", "status_code": e.response.status_code, "raw_response": e.response.text}
        except httpx.RequestError as e:
            print(f"Request error occurred while logging telemetry event: {e}")
            return {"error": "RequestError", "message": str(e)}
        except Exception as e:
            print(f"An unexpected error occurred in TelemetryClient.log_event: {e}")
            return {"error": "UnexpectedError", "message": str(e)}

    async def close(self):
        """Closes the httpx client. Should be called on application shutdown."""
        await self.client.aclose()

if __name__ == '__main__':
    import asyncio

    async def main():
        # Example Usage (requires the mock_api_service to be running)
        # Ensure your mock_api_service is running on http://localhost:8001 or adjust URL
        # And that it has the /telemetry/log_event endpoint.
        
        # These would typically come from your Hydra config
        cfg_telemetry_client = {
            "base_url": "http://localhost:8001", # Adjust if your service runs elsewhere
            "endpoints": {
                "log_event": "/telemetry/log_event"
            }
        }
        
        client = TelemetryClient(
            base_url=cfg_telemetry_client["base_url"],
            log_event_endpoint=cfg_telemetry_client["endpoints"]["log_event"]
        )

        event1 = {
            "session_id": "client_test_01",
            "event_type": "TEST_EVENT_FROM_CLIENT",
            "user_query": "Testing telemetry client",
            "agent_configuration": {"llm": "test_client_model"},
            "agent_generated_payload": {"notes": "This is a test payload from client"}
        }
        
        print(f"Sending event: {event1}")
        response = await client.log_event(event1)
        print(f"Response from log_event: {response}")

        await client.close()

    asyncio.run(main())
