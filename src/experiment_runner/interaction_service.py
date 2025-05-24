# src/experiment_runner/interaction_service.py
import asyncio
import secrets
from datetime import datetime
from omegaconf import DictConfig, OmegaConf
import os
import logging

from src.chatbot.service import ChatbotService # For OrderAgent
from src.customer_agent.agent import CustomerAgent
from src.chatbot.utils.telemetry_client import TelemetryClient # For orchestrator's own logging

class AgentInteractionService:
    def __init__(self, 
                 order_agent_full_config: DictConfig, 
                 customer_agent_full_config: DictConfig,
                 interaction_run_config: DictConfig):
        """
        Initializes the service with configurations for both agents and the interaction run.
        
        Args:
            order_agent_full_config: The actual configuration block for OrderAgent (e.g., cfg.experiment.order_agent).
            customer_agent_full_config: The actual configuration block for CustomerAgent (e.g., cfg.experiment.customer_agent).
            interaction_run_config: The 'experiment' node from Hydra config.
        """
        self.logger = logging.getLogger(__name__) # Get a logger for this class
        self.logger.info("Initializing AgentInteractionService...")
        # order_agent_full_config IS the specific config for the order agent.
        # customer_agent_full_config IS the specific config for the customer agent.
        self.order_agent_direct_cfg = order_agent_full_config 
        self.customer_agent_direct_cfg = customer_agent_full_config
        
        self.run_cfg = interaction_run_config 
        self.conversation_settings_cfg = self.run_cfg.conversation_settings

        self.logger.info("Initializing Order Agent (ChatbotService)...")
        # ChatbotService expects the config node that contains 'order_agent.llm', 'order_agent.prompts' etc.
        # which is what order_agent_full_config should be.
        self.chatbot_service = ChatbotService(order_agent_full_config) 

        self.logger.info("Initializing Customer Agent...")
        
        # actual_customer_agent_params holds specific settings for the customer_agent instance
        actual_customer_agent_params = customer_agent_full_config.customer_agent

        # The persona_prompt_template_path should come from the shared 'prompts' block
        # within the customer_agent_full_config, similar to how 'llm' config is accessed.
        # customer_agent_full_config.prompts is an object with a 'prompt_path' key.
        persona_prompt_template_path = customer_agent_full_config.prompts.prompt_path
        
        self.customer_agent = CustomerAgent(
            llm_config=customer_agent_full_config.llm, # Correct: Uses the shared llm config
            persona_prompt_template_path=persona_prompt_template_path, # Corrected path
            mock_api_base_url=actual_customer_agent_params.get('mock_api_base_url', "http://localhost:8001"),
            customer_name=actual_customer_agent_params.get('customer_name', "Automated Customer"),
            # Initialize order_id to None here. If the config has a specific order_id, 
            # it would be used for the VERY FIRST interaction if not reset.
            # Forcing None here ensures even the first run of run_single_interaction fetches randomly
            # unless the config *explicitly* wants a fixed order for all runs (which is not typical for this service).
            order_id=None # Explicitly set to None to ensure random fetch on first call too if not overridden by a specific test case.
        )
        self.logger.info("All agents initialized.")

        # Telemetry for the orchestrator itself (optional, could log relay events)
        # For now, we'll rely on the OrderAgent's telemetry.
        # If needed:
        # telemetry_cfg = self.run_cfg.get('interaction_telemetry')
        # self.orchestrator_telemetry_client = TelemetryClient(base_url=telemetry_cfg.base_url, ...)

    def _generate_interaction_session_id(self, conversation_index: int) -> str:
        date_str = datetime.utcnow().strftime("%y%m%d")
        random_hash = secrets.token_hex(3)
        # Include model/prompt identifiers if easily accessible, for richer session IDs
        # For now, a simple index is fine.
        return f"auto-session-{date_str}-{random_hash}-conv{conversation_index}"

    async def run_single_interaction(self, conversation_index: int) -> None:
        """
        Runs a single full conversation between the OrderAgent and CustomerAgent.
        A new random order will be fetched for the CustomerAgent for each interaction.
        """
        session_id = self._generate_interaction_session_id(conversation_index)
        self.logger.info(f"--- Starting Interaction Run #{conversation_index} | Session ID: {session_id} ---")

        # Reset CustomerAgent's order focus to ensure a new random order is fetched
        # unless the customer_agent_config specifically provides an order_id (which it currently doesn't by default).
        # If an experiment *needs* a specific order for a specific CustomerAgent config, that config could set it.
        # For general runs, we want random.
        if not self.customer_agent_direct_cfg.customer_agent.get('order_id'): # Only reset if no specific order_id is in THIS run's config
            self.logger.info(f"[{session_id}][Orchestrator] Resetting customer agent's order to fetch a new random one.")
            self.customer_agent.order_id = None
            self.customer_agent.order_details = None
            self.customer_agent.conversation_history = [] # Also clear history from any previous interaction
        else:
            # If a specific order_id IS in the config for this customer agent, respect it.
            # This allows for specific test cases.
            configured_order_id = self.customer_agent_direct_cfg.customer_agent.get('order_id')
            self.logger.info(f"[{session_id}][Orchestrator] Using pre-configured Order ID for Customer Agent: {configured_order_id}")
            self.customer_agent.order_id = configured_order_id
            self.customer_agent.order_details = None # Force re-fetch of this specific order's details
            self.customer_agent.conversation_history = []


        # 1. Initialize Customer Agent Context (will now fetch a new random order if order_id is None)
        self.logger.info(f"[{session_id}][Orchestrator] Initializing Customer Agent context...")
        customer_context_ok = await self.customer_agent.initialize_conversation_context()
        if not customer_context_ok:
            self.logger.warning(f"[{session_id}][Orchestrator] Failed to initialize Customer Agent context. Skipping interaction.")
            return
        if self.customer_agent.order_id: # Log the order ID the customer agent will use
            self.logger.info(f"[{session_id}][Orchestrator] Customer Agent focusing on Order ID: {self.customer_agent.order_id}")
        self.logger.debug(f"[{session_id}][Orchestrator] Customer agent conversation history after init: {self.customer_agent.conversation_history}")


        # 2. Conversation Loop
        current_turn = 0
        # Correctly access nested config values
        max_turns = self.conversation_settings_cfg.get('max_turns_per_conversation', 8)
        min_turns = self.conversation_settings_cfg.get('min_turns_per_conversation', 2)
        
        # Order Agent starts the conversation
        # Get initial greeting from the top-level interaction_run_config if it's there,
        # or from conversation_settings_cfg. For now, assuming it might be at top or under conversation_settings
        # Your current config has it at the top level of experiment/default.yaml (order_agent_initial_greeting)
        # So, we'll access it from self.run_cfg which is interaction_run_config
        last_order_agent_message = self.run_cfg.get('order_agent_initial_greeting', "Hello, how can I help you?")
        
        self.logger.info(f"[{session_id}][Turn {current_turn}][OrderAgent]: Greetings sent.")
        self.logger.debug(f"[{session_id}][Turn {current_turn}][OrderAgent] Initial Greeting: {last_order_agent_message}")
        # Log this initial greeting with OrderAgent's telemetry if desired
        # This would require a way to "inject" a message into OrderAgent's telemetry logging as if it said it.
        # For now, this orchestrator log is the record.

        try:
            while current_turn < max_turns:
                current_turn += 1
                # Apply turn delay if configured
                turn_delay_seconds = self.conversation_settings_cfg.get('turn_delay_seconds', 0)
                if turn_delay_seconds > 0:
                    self.logger.info(f"[{session_id}][Orchestrator] Delaying for {turn_delay_seconds}s...")
                    await asyncio.sleep(turn_delay_seconds)

                self.logger.info(f"[{session_id}][Orchestrator] --- Turn {current_turn} ---")

                # 2a. Customer Agent Responds
                self.logger.info(f"[{session_id}][Orchestrator] Customer Agent to generate response.")
                self.logger.debug(f"[{session_id}][Orchestrator] Customer Agent responding to: \"{last_order_agent_message[:100]}...\"")
                customer_response = await self.customer_agent.generate_response(last_order_agent_message)
                if not customer_response:
                    self.logger.warning(f"[{session_id}][Orchestrator] Customer Agent failed to generate a response. Ending interaction.")
                    break
                self.logger.info(f"[{session_id}][Turn {current_turn}][CustomerAgent ({self.customer_agent.customer_name})]: Response generated.")
                self.logger.debug(f"[{session_id}][Turn {current_turn}][CustomerAgent ({self.customer_agent.customer_name})]: {customer_response}")
                self.logger.debug(f"[{session_id}][Orchestrator] Customer agent history: {self.customer_agent.conversation_history}")

                # Check for conversation end conditions (basic for now)
                if current_turn >= min_turns and ("goodbye" in customer_response.lower() or "thank you" in customer_response.lower()):
                     self.logger.info(f"[{session_id}][Orchestrator] Customer Agent indicated conversation end.")
                     break


                # 2b. Order Agent Responds
                self.logger.info(f"[{session_id}][Orchestrator] Order Agent to process customer message.")
                self.logger.debug(f"[{session_id}][Orchestrator] Order Agent processing: \"{customer_response[:100]}...\"")
                # The ChatbotService.process_message handles its own telemetry logging internally
                order_agent_response = await self.chatbot_service.process_message(
                    user_query=customer_response,
                    session_id=session_id, 
                    # This needs the config that ChatbotService expects for telemetry,
                    # which is the 'order_agent_full_config' we passed to its constructor.
                    # So, self.order_agent_direct_cfg is correct here.
                    agent_config_for_telemetry=self.order_agent_direct_cfg 
                )
                if not order_agent_response:
                    self.logger.warning(f"[{session_id}][Orchestrator] Order Agent failed to generate a response. Ending interaction.")
                    break
                self.logger.info(f"[{session_id}][Turn {current_turn}][OrderAgent]: Response generated.")
                self.logger.debug(f"[{session_id}][Turn {current_turn}][OrderAgent]: {order_agent_response}")
                last_order_agent_message = order_agent_response
                # Add orchestrator telemetry log for ORDER_AGENT_MESSAGE_RELAYED if implemented

                # Check for conversation end conditions
                if current_turn >= min_turns and ("goodbye" in order_agent_response.lower() or "thank you for your help" in order_agent_response.lower()):
                     self.logger.info(f"[{session_id}][Orchestrator] Order Agent indicated conversation end.")
                     break
            
            if current_turn == max_turns:
                self.logger.info(f"[{session_id}][Orchestrator] Reached max turns ({max_turns}). Ending interaction.")

        except Exception as e:
            self.logger.error(f"[{session_id}][Orchestrator] An error occurred during interaction: {e}", exc_info=True)
        finally:
            self.logger.info(f"--- Finished Interaction Run #{conversation_index} | Session ID: {session_id} ---")
            # Clearing customer_agent's conversation_history is now done at the start of run_single_interaction
            # OrderAgent's memory is tied to session_id; new session_id means new memory context for Langchain agent


    async def close_services(self):
        """Closes any services that need explicit closing, like telemetry clients."""
        self.logger.info("[AgentInteractionService] Closing services...")
        if self.chatbot_service:
            await self.chatbot_service.close_telemetry() # Important for OrderAgent's telemetry
        # if self.orchestrator_telemetry_client:
        #     await self.orchestrator_telemetry_client.close()
        self.logger.info("[AgentInteractionService] Services closed.")
