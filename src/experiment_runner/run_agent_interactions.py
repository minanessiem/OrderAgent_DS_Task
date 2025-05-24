import hydra
from omegaconf import DictConfig, OmegaConf
import asyncio
from dotenv import load_dotenv
import os
import sys
import logging

# Add project root to sys.path to allow direct imports of src components
# This is often needed when running scripts from subdirectories directly
# or when Hydra changes the working directory.
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.experiment_runner.interaction_service import AgentInteractionService
# Correctly import only the necessary function from db_seeder
from src.mock_api_service.db_seeder import reseed_database_with_new_data
# Import engine and Session for database operations
from src.mock_api_service.db import engine  # engine is configured by db.py
from sqlmodel import Session as SQLModelSession # Renaming for clarity if plain Session is used elsewhere

load_dotenv()

async def main_async_logic(cfg: DictConfig):
    # --- Initialize Logging ---
    log_level_str = cfg.experiment.get('logging_level', 'INFO').upper()
    numeric_level = getattr(logging, log_level_str, logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    # Get a logger for this script
    script_logger = logging.getLogger(__name__)

    script_logger.info("🚀 Starting Automated Agent Interaction Runner...")
    script_logger.debug("\n📋 Effective Experiment Configuration:\n%s", OmegaConf.to_yaml(cfg))

    # --- Database Seeding (Optional) ---
    if cfg.experiment.db_seeder_settings.get('reseed_before_run', False):
        script_logger.info("\n🌱 Reseeding database as per configuration...")
        try:
            # db.py has already loaded the config and set up the engine
            # We use that engine to create a session for the seeder.
            script_logger.info(f"Using database engine configured by mock_api_service.db: {engine.url}")

            # Synchronous db operations need to be run in a thread from an async context
            def _run_sync_seeding():
                with SQLModelSession(engine) as session: 
                    reseed_database_with_new_data( 
                        session=session, 
                        num_orders=cfg.experiment.db_seeder_settings.get('num_orders_to_seed', 100),
                        num_customers=cfg.experiment.db_seeder_settings.get('num_customers_to_seed', 20),
                        seed_value=cfg.experiment.db_seeder_settings.get('seed_value', None)
                        # min_order_days_ago and max_order_days_ago can be added here
                        # if you want the experiment config to override db_seeder defaults
                    )
                    session.commit()
            
            await asyncio.to_thread(_run_sync_seeding)
            script_logger.info("🌱 Database reseeding complete.")
        except Exception as e:
            script_logger.error(f"❌ Error during database reseeding: {e}", exc_info=True)
            # Decide if you want to continue or exit if seeding fails
            # For now, we'll print the error and attempt to continue.

    # --- Initialize Interaction Service ---
    # The configs for order_agent and customer_agent are already resolved by Hydra
    # and are available under cfg.order_agent and cfg.customer_agent respectively.
    script_logger.info("\n🤖 Initializing Agent Interaction Service...")
    interaction_service = AgentInteractionService(
        order_agent_full_config=cfg.experiment.order_agent, 
        customer_agent_full_config=cfg.experiment.customer_agent, 
        interaction_run_config=cfg.experiment # Pass the 'experiment' node
    )

    # --- Run Conversations ---
    # num_conversations is now num_conversations_per_permutation
    num_conversations = cfg.experiment.conversation_settings.get('num_conversations_per_permutation', 1)
    script_logger.info(f"\n🗣️ Starting {num_conversations} conversation(s)...")
    
    for i in range(num_conversations):
        # Here you would typically loop through different Order Agent prompts
        # and Customer Agent personas if your config supports permutations.
        # For this initial setup, we run with the single loaded config.
        # TODO: Extend for prompt/persona permutations if needed.
        script_logger.info(f"\n--- Preparing for Conversation Set #{i + 1} ---")
        # If CustomerAgent needs to pick a new random order for each conversation AND
        # was initialized WITHOUT a specific order_id, it will fetch one in initialize_conversation_context.
        # If you want to force a *new* random order even if it previously had one,
        # you might need a method like `customer_agent.reset_order()`
        # For now, CustomerAgent's init logic for order_id will define its behavior.

        await interaction_service.run_single_interaction(conversation_index=i + 1)
    
    # --- Cleanup ---
    script_logger.info("\n🏁 Closing down services...")
    await interaction_service.close_services()
    script_logger.info("\n✅ Automated Agent Interaction Runner finished successfully.")

@hydra.main(config_path="../../configs", config_name="experiment/default", version_base=None)
def hydra_entry_point(cfg: DictConfig):
    """
    Hydra entry point. Loads configuration and runs the async main logic.
    """
    # Note: Hydra typically changes the CWD to the output directory.
    # The sys.path manipulation at the top helps with imports.
    # OmegaConf.resolve_to_yaml(cfg, resolve=True) # Can be useful for debugging resolved paths
    try:
        asyncio.run(main_async_logic(cfg))
    except Exception as e:
        # Use the root logger or a specific logger here if needed
        logging.critical(f"❌ An unhandled error occurred in the async runner: {e}", exc_info=True)
        # Consider exiting with a non-zero code if critical error
        sys.exit(1)


if __name__ == "__main__":
    hydra_entry_point()
