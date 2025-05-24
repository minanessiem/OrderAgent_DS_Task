import httpx # Using httpx for robust HTTP requests
from typing import Optional, List, Dict, Tuple, Any
from omegaconf import DictConfig
import logging # Add this import

# Assuming these utilities have been moved as discussed:
from src.utils.llm_providers import get_llm # Correctly import get_llm
from src.utils.prompt_utils import load_prompt_from_file, inject_placeholders

class CustomerAgent:
    def __init__(
        self,
        persona_prompt_template_path: str,
        llm_config: DictConfig, # Changed: Expect DictConfig directly
        mock_api_base_url: str = "http://localhost:8001",
        customer_name: str = "Valued Customer",
        order_id: Optional[str] = None
    ):
        self.logger = logging.getLogger(__name__) # Get a logger
        self.llm_config = llm_config
        self.llm = get_llm(self.llm_config) # Use get_llm to initialize the LLM
        
        self.logger.info(f"Loading persona prompt template from: {persona_prompt_template_path}")
        self.persona_prompt_template = load_prompt_from_file(persona_prompt_template_path)
        
        self.mock_api_base_url = mock_api_base_url
        self.customer_name = customer_name
        self.order_id: Optional[str] = order_id
        self.order_details: Optional[Dict[str, Any]] = None
        
        # This will store the resolved persona prompt after order details are fetched
        self.resolved_system_persona_prompt: Optional[str] = None 
        # conversation_history will now store:
        # {"role": "user", "content": "Order Agent's message"}
        # {"role": "assistant", "content": "Customer Agent's (LLM) response"}
        self.conversation_history: List[Dict[str, str]] = [] 
        self.logger.info(f"CustomerAgent '{self.customer_name}' initialized. LLM: {self.llm_config.get('model_name', 'N/A')}")

    async def _fetch_order_details(self) -> bool: # Made async for potential async httpx if needed later
        """
        Fetches order details. If self.order_id is set, fetches that specific order.
        Otherwise, fetches a random order.
        Populates self.order_details and self.order_id.
        Returns True on success, False on failure.
        """
        try:
            endpoint = ""
            if self.order_id:
                endpoint = f"/orders/{self.order_id}"
                self.logger.info(f"Fetching details for pre-set order ID: {self.order_id}")
                self.logger.debug(f"Fetching from URL: {self.mock_api_base_url}{endpoint}")
            else:
                endpoint = "/dev/orders/random" # Corrected endpoint
                self.logger.info("Fetching random order.")
                self.logger.debug(f"Fetching from URL: {self.mock_api_base_url}{endpoint}")

            # httpx can be used asynchronously as well, but for this single call, sync is fine.
            # If we wanted full async, we'd use `async with httpx.AsyncClient() as client:`
            with httpx.Client() as client:
                response = client.get(f"{self.mock_api_base_url}{endpoint}")
                response.raise_for_status()
                fetched_data = response.json()

            if fetched_data:
                self.order_details = fetched_data
                self.order_id = self.order_details.get("order_id")
                if self.order_id:
                    self.logger.info(f"Successfully fetched order: {self.order_id}")
                    self.logger.debug(f"Order Details: {self.order_details}")
                    return True
                else:
                    self.logger.error(f"Fetched data does not contain an order_id. Data: {self.order_details}")
                    self.order_details = None
                    return False
            else:
                self.logger.error(f"No data received from {endpoint}. ")
                self.order_details = None
                return False

        except httpx.HTTPStatusError as e:
            self.logger.error(f"HTTP error fetching order details from {endpoint}: {e.response.status_code}", exc_info=True)
            self.logger.debug(f"Response text: {e.response.text}")
            self.order_details = None
            return False
        except httpx.RequestError as e:
            self.logger.error(f"Request error fetching order details from {endpoint}: {e}", exc_info=True)
            self.order_details = None
            return False
        except Exception as e:
            self.logger.error("Unexpected error fetching order details", exc_info=True)
            self.order_details = None
            return False

    def _get_placeholders_for_prompt(self) -> Dict[str, Any]:
        """Prepares a dictionary of placeholders from order_details."""
        placeholders = {
            "customer_name": self.customer_name,
            "order_id": self.order_id or "UNKNOWN_ORDER",
        }
        if self.order_details:
            placeholders["order_status"] = self.order_details.get("status", "UNKNOWN_STATUS")
            placeholders["order_ordered_on"] = self.order_details.get("ordered_on", "UNKNOWN_DATE")
            
            customer_summary = self.order_details.get("customer")
            if isinstance(customer_summary, dict):
                 placeholders["customer_is_premium"] = str(customer_summary.get("is_premium", False)).lower()

            ordered_on_str = self.order_details.get("ordered_on")
            if ordered_on_str:
                try:
                    from datetime import date, datetime
                    order_date = datetime.fromisoformat(ordered_on_str.split("T")[0]).date()
                    days_diff = (date.today() - order_date).days
                    placeholders["days_since_order_placed"] = str(days_diff)
                except ValueError:
                    placeholders["days_since_order_placed"] = "UNKNOWN_DURATION"
            else:
                placeholders["days_since_order_placed"] = "UNKNOWN_DURATION"
        
        # Ensure all common placeholders have default values if order_details are missing
        for key in ["order_status", "order_ordered_on", "customer_is_premium", "days_since_order_placed"]:
            if key not in placeholders:
                placeholders[key] = f"UNKNOWN_{key.upper()}"
        return placeholders

    async def initialize_conversation_context(self) -> bool:
        """
        Initializes order details and resolves the system persona prompt.
        Returns True on success, False on failure.
        """
        self.logger.info("Initializing conversation context...")
        if not self.order_details: # Attempt to fetch only if not already populated (e.g. by specific order_id set at init)
            if not await self._fetch_order_details():
                self.logger.warning("Failed to fetch order details. Cannot initialize context.")
                return False
        
        placeholders = self._get_placeholders_for_prompt()
        # Resolve the persona prompt with order details and store it
        self.resolved_system_persona_prompt = inject_placeholders(self.persona_prompt_template, placeholders)
        
        if self.resolved_system_persona_prompt:
            self.logger.info("Context initialized successfully.")
            self.logger.debug(f"System prompt (persona + context):\n{self.resolved_system_persona_prompt[:500]}...")
            return True
        else:
            self.logger.error("Failed to resolve system persona prompt.")
            return False

    async def generate_response(self, order_agent_message: str) -> Optional[str]:
        """
        Generates the customer's (LLM's) response based on the order agent's last message.
        """
        if not self.resolved_system_persona_prompt:
            self.logger.error("Conversation context not initialized or system persona not resolved. Cannot generate response.")
            return None

        # Add the Order Agent's message (role: user) to history
        self.conversation_history.append({"role": "user", "content": order_agent_message})
        
        current_messages_for_llm = [
            {"role": "system", "content": self.resolved_system_persona_prompt}
        ] + self.conversation_history

        self.logger.info(f"Generating response for customer '{self.customer_name}'.")
        self.logger.debug(f"Full messages for LLM (last 3 turns): {current_messages_for_llm[-6:]}") # Show more context for LLM input

        try:
            response = await self.llm.ainvoke(current_messages_for_llm)
            customer_agent_response = response.content if hasattr(response, 'content') else str(response)
            
            if customer_agent_response:
                # Add the Customer Agent's (LLM's) response (role: assistant) to history
                customer_agent_response = customer_agent_response.strip()
                self.conversation_history.append({"role": "assistant", "content": customer_agent_response})
                self.logger.info("Response generated successfully.")
                self.logger.debug(f"Generated response: {customer_agent_response}")
                return customer_agent_response
            else:
                self.logger.warning("LLM failed to generate a response (empty content).")
                return None
        except Exception as e:
            self.logger.error("Error generating response from LLM.", exc_info=True)
            return None
