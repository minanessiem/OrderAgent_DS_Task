import hydra
from omegaconf import DictConfig, OmegaConf
import asyncio
import os
import logging

from src.customer_agent.agent import CustomerAgent

from dotenv import load_dotenv
load_dotenv()

# Helper to resolve paths (remains the same, specific to config loading for this service)
# Not moving to utils for now as its usage is localized.
def get_full_path(cfg_root_path: str, relative_path: str) -> str:
    if os.path.isabs(relative_path):
        return relative_path
    return relative_path


class CustomerAgentService:
    def __init__(self, cfg: DictConfig):
        self.cfg = cfg
        self.logger = logging.getLogger(__name__) # Logger for the service
        self.agent_cfg = self.cfg.customer_agent

        persona_prompt_path = self.agent_cfg.prompts.prompt_path

        self.logger.info(f"  LLM Config being used by CustomerAgent: {self.agent_cfg.llm.provider}/{self.agent_cfg.llm.model_name}")
        self.logger.debug(f"  Full LLM Config: {OmegaConf.to_yaml(self.agent_cfg.llm)}")
        self.logger.info(f"  Persona Prompt Path: {persona_prompt_path}")
        self.logger.info(f"  Mock API Base URL: {self.agent_cfg.get('mock_api_base_url', 'http://localhost:8001')}")
        self.logger.info(f"  Order ID (optional): {self.agent_cfg.get('order_id', None)}")

        try:
            self.agent = CustomerAgent(
                llm_config=self.agent_cfg.llm,
                persona_prompt_template_path=persona_prompt_path,
                mock_api_base_url=self.agent_cfg.get('mock_api_base_url', "http://localhost:8001"),
                customer_name=self.agent_cfg.get('customer_name', "Valued Customer"),
                order_id=self.agent_cfg.get('order_id', None)
            )
        except Exception as e:
            self.logger.error(f"Error initializing CustomerAgent: {e}", exc_info=True)
            raise # Re-raise to be caught by the caller if initialization fails

    async def run_cli(self):
        self.logger.info("\n--- Initializing Conversation Context ---")
        context_initialized = await self.agent.initialize_conversation_context()

        if not context_initialized:
            self.logger.error("Customer Agent failed to initialize context. Exiting.")
            return

        if self.agent.order_id:
            self.logger.info(f"Customer Agent is now focused on Order ID: {self.agent.order_id}")
        self.logger.info(f"Customer Agent Persona: {self.agent_cfg.prompts.prompt_path}") # Use path from service's config
        self.logger.info(f"--- Starting Chat with Customer Agent ({self.agent.customer_name}) ---")
        self.logger.info("You are the Order Agent. Please start the conversation.")

        turn_count = 1
        try:
            while True:
                try:
                    order_agent_message = await asyncio.to_thread(
                        input,
                        f"\nYour Message (Order Agent) (Turn {turn_count}) (type 'exit' to quit): "
                    )
                except RuntimeError:
                    order_agent_message = input(
                        f"\nYour Message (Order Agent) (Turn {turn_count}) (type 'exit' to quit): "
                    )

                if order_agent_message.lower() == 'exit':
                    self.logger.info("Exiting chat.")
                    break
                if not order_agent_message.strip():
                    continue

                self.logger.info(f"[OrderAgent][Turn {turn_count}] You said: {order_agent_message[:100]}...")

                customer_agent_response = await self.agent.generate_response(order_agent_message)
                if not customer_agent_response:
                    self.logger.warning("Customer Agent could not generate a response. Ending chat.")
                    break

                print(f"Customer Agent ({self.agent.customer_name}): {customer_agent_response}")
                self.logger.info(f"[CustomerAgent][Turn {turn_count}] Responded.")
                self.logger.debug(f"[CustomerAgent][Turn {turn_count}] Full response: {customer_agent_response}")
                turn_count += 1
        except KeyboardInterrupt:
            self.logger.info("\nExiting chat due to interrupt.")
        finally:
            self.logger.info("Customer Agent CLI session ended.")


async def customer_agent_cli_logic(cfg: DictConfig):
    logger = logging.getLogger(__name__) # Logger for this specific logic function
    logger.info("Initializing Customer Agent Service for CLI...")
    
    try:
        service = CustomerAgentService(cfg)
        await service.run_cli()
    except Exception as e:
        # If CustomerAgentService failed to initialize (e.g. CustomerAgent init error)
        logger.error(f"Failed to start Customer Agent CLI: {e}", exc_info=True)
        # No need to re-log if already logged by CustomerAgentService constructor,
        # but this catches errors during service.run_cli() or if init itself failed before run_cli.


@hydra.main(config_path="../../configs", config_name="customer_agent/default", version_base=None)
def main(cfg: DictConfig):
    log_level_str = cfg.get('logging_level', 'INFO').upper()
    numeric_level = getattr(logging, log_level_str, logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    script_logger = logging.getLogger(__name__) # Logger for this main function
    script_logger.info("Hydra Entry Point for Customer Agent. Effective config:")
    script_logger.debug(OmegaConf.to_yaml(cfg))

    try:
        asyncio.run(customer_agent_cli_logic(cfg))
    except Exception as e:
        script_logger.critical(f"An unhandled error occurred in customer_agent_cli_logic: {e}", exc_info=True)

if __name__ == "__main__":
    main()
