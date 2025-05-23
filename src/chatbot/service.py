import hydra
from omegaconf import DictConfig, OmegaConf
import asyncio # For async operations
import json # For parsing JSON strings if needed (though extractor handles it)
import re # For extracting payload
from datetime import datetime # For current date
import secrets
import os

from langchain.memory import ConversationBufferMemory

from src.chatbot.llm_providers import get_llm
from src.chatbot.tools.order_tracking_tool import OrderTrackingTool
from src.chatbot.tools.order_cancellation_tool import OrderCancellationTool
from src.chatbot.agent import create_order_management_agent
from src.chatbot.prompts.prompt_utils import load_prompt_from_file
# New imports for telemetry and payload extraction
from src.chatbot.utils.telemetry_client import TelemetryClient
from src.chatbot.utils.payload_extractor import extract_telemetry_payload

from dotenv import load_dotenv
load_dotenv() 

class ChatbotService:
    def __init__(self, cfg: DictConfig):
        self.cfg = cfg
        self.llm = get_llm(cfg.order_agent.llm)

        # Load base system prompt content once
        self.base_system_prompt_content = load_prompt_from_file(cfg.order_agent.prompts.system_prompt)
        
        # Initialize TelemetryClient
        telemetry_cfg = cfg.order_agent.telemetry_client
        self.telemetry_client = TelemetryClient(
            base_url=telemetry_cfg.base_url,
            log_event_endpoint=telemetry_cfg.endpoints.log_event
        )

        # Initialize Tools (existing logic)
        track_order_config = next(ep for ep in cfg.order_agent.mock_api_service.endpoints if ep.name == "get_order")
        self.order_tracking_tool = OrderTrackingTool(
            mock_api_base_url=cfg.order_agent.mock_api_service.base_url,
            track_order_endpoint_template=track_order_config.url
        )
        cancel_order_config = next(ep for ep in cfg.order_agent.mock_api_service.endpoints if ep.name == "cancel_order")
        self.order_cancellation_tool = OrderCancellationTool(
            mock_api_base_url=cfg.order_agent.mock_api_service.base_url,
            cancel_order_endpoint_template=cancel_order_config.url
        )
        self.tools = [self.order_tracking_tool, self.order_cancellation_tool]

        # Agent Executor will be created per call in process_message,
        # or if the date for policy is fixed for service lifetime, it can be here.
        # For now, let's assume it's created with a fixed date for the service instance lifetime for simplicity.
        # For true per-request date, agent creation needs to be inside process_message.
        current_date_for_prompt = self._get_current_date_for_policy()
        formatted_system_prompt = self.base_system_prompt_content.format(current_date_for_policy=current_date_for_prompt)

        self.agent_executor = create_order_management_agent(
            llm=self.llm,
            tools=self.tools,
            agent_config=cfg.order_agent.agent,
            system_prompt_content=formatted_system_prompt # Pass formatted prompt
        )
        
        self.memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
        self.agent_executor.memory = self.memory

    def _get_current_date_for_policy(self) -> str:
        """Returns the current date as YYYY-MM-DD string for policy checks."""
        return datetime.utcnow().strftime("%Y-%m-%d")

    async def process_message(self, user_query: str, session_id: str, agent_config_for_telemetry: DictConfig):
        """
        Processes a user query, logs telemetry, and returns the agent's response.
        """
        # Extract specific config values for telemetry
        agent_model_name = agent_config_for_telemetry.llm.model_name
        system_prompt_path = agent_config_for_telemetry.prompts.system_prompt
        system_prompt_name = os.path.basename(system_prompt_path)

        # 1. Log USER_QUERY_RECEIVED
        initial_telemetry_data = {
            "session_id": session_id,
            "event_type": "USER_QUERY_RECEIVED",
            "user_query": user_query,
            "agent_model_name": agent_model_name,
            "system_prompt_name": system_prompt_name,
        }
        await self.telemetry_client.log_event(initial_telemetry_data)

        try:
            agent_input = {"input": user_query}
            result = await self.agent_executor.ainvoke(agent_input)
        except Exception as e:
            print(f"Error during agent invocation: {e}")
            error_telemetry = {
                "session_id": session_id, "event_type": "AGENT_ERROR",
                "additional_notes": f"Agent invocation failed: {str(e)}",
                "user_query": user_query,
                "agent_model_name": agent_model_name,
                "system_prompt_name": system_prompt_name,
            }
            await self.telemetry_client.log_event(error_telemetry)
            return "Sorry, I encountered an error processing your request."

        final_response_to_user = result.get("output", "Sorry, I couldn't formulate a response.")
        agent_telemetry_payload_final = extract_telemetry_payload(final_response_to_user)
        
        order_id_from_final_payload = agent_telemetry_payload_final.get("order_id_analyzed") if agent_telemetry_payload_final else None

        if agent_telemetry_payload_final:
            final_response_to_user = re.sub(r"<agent_telemetry_payload>.*?</agent_telemetry_payload>", "", final_response_to_user, flags=re.DOTALL).strip()
        
        if "intermediate_steps" in result and result["intermediate_steps"]:
            for step_action, step_observation in result["intermediate_steps"]:
                tool_name = step_action.tool
                tool_input = step_action.tool_input
                agent_thought = step_action.log
                
                agent_telemetry_payload_step = extract_telemetry_payload(agent_thought)
                
                order_id_for_step = None
                if agent_telemetry_payload_step and agent_telemetry_payload_step.get("order_id_analyzed"):
                    order_id_for_step = agent_telemetry_payload_step.get("order_id_analyzed")
                elif isinstance(tool_input, dict) and tool_input.get("order_id"):
                    order_id_for_step = tool_input.get("order_id")
                # No fallback to initial_order_id or order_id_from_final_payload here for step-specific logs,
                # as those might not be relevant to *this specific step* if the agent changes focus.
                # The order_id should be directly associated with the step's context.

                intent_event = {
                    "session_id": session_id,
                    "event_type": "AGENT_DECISION_INTENT",
                    "order_id_identified": order_id_for_step,
                    "agent_generated_payload": agent_telemetry_payload_step,
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "additional_notes": "Payload extracted from agent thought before tool call." if agent_telemetry_payload_step else "No telemetry payload found in agent thought.",
                    "agent_model_name": agent_model_name,
                    "system_prompt_name": system_prompt_name,
                }
                await self.telemetry_client.log_event(intent_event)

                tool_executed_event = {
                    "session_id": session_id,
                    "event_type": "AGENT_TOOL_EXECUTED",
                    "order_id_identified": order_id_for_step,
                    "tool_name": tool_name,
                    "tool_input": tool_input,
                    "tool_raw_response": str(step_observation),
                    "agent_model_name": agent_model_name,
                    "system_prompt_name": system_prompt_name,
                }
                await self.telemetry_client.log_event(tool_executed_event)
        
        final_event_data = {
            "session_id": session_id,
            "event_type": "AGENT_FINAL_RESPONSE",
            "order_id_identified": order_id_from_final_payload,
            "final_agent_message_to_user": final_response_to_user,
            "agent_generated_payload": agent_telemetry_payload_final,
            "additional_notes": "Payload extracted from final output." if agent_telemetry_payload_final else "No telemetry payload in final output.",
            "agent_model_name": agent_model_name,
            "system_prompt_name": system_prompt_name,
        }
        await self.telemetry_client.log_event(final_event_data)
        
        return final_response_to_user

    async def close_telemetry(self):
        """Close the telemetry client."""
        if self.telemetry_client:
            await self.telemetry_client.close()


async def main_async_logic(cfg: DictConfig): # Renamed from main, still async
    print("Initializing Chatbot Service (async logic)...")
    agent_config_for_telemetry = cfg.order_agent 
    
    service = ChatbotService(cfg) # ChatbotService __init__ is sync
    print("Chatbot Service Initialized. Type 'exit' to quit.")
    
    session_counter = 1
    try:
        while True:
            # Using asyncio.to_thread for blocking input() in async context
            try:
                user_input = await asyncio.to_thread(input, "You: ")
            except RuntimeError as e:
                if "cannot be called from a running event loop" in str(e): # Fallback for environments where input() is already async-friendly or to_thread is tricky
                    print("Async input context issue, trying direct input()...")
                    user_input = input("You: ") 
                else:
                    raise

            if user_input.lower() == 'exit':
                print("Exiting chatbot.")
                break
            if not user_input.strip():
                continue
            
            # Generate session ID in the new format
            date_str = datetime.utcnow().strftime("%d%m%y")
            random_hash = secrets.token_hex(3) # 3 bytes = 6 hex characters
            current_session_id = f"session-{date_str}-{random_hash}"

            print(f"--- Session: {current_session_id} ---")
            
            bot_response = await service.process_message(
                user_query=user_input,
                session_id=current_session_id,
                agent_config_for_telemetry=agent_config_for_telemetry 
            )
            print(f"Bot: {bot_response}")
            session_counter += 1
    except KeyboardInterrupt:
        print("\nKeyboard interrupt received, exiting...")
    finally:
        print("Closing telemetry client...")
        await service.close_telemetry()
        print("Telemetry client closed.")

@hydra.main(config_path="../../configs", config_name="order_agent/default", version_base=None)
def main(cfg: DictConfig): # This is the new synchronous main that Hydra calls
    print("Hydra Entry Point. Effective config:", OmegaConf.to_yaml(cfg))
    try:
        asyncio.run(main_async_logic(cfg))
    except Exception as e:
        print(f"An error occurred in the async logic: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
