import hydra
from omegaconf import DictConfig, OmegaConf

from langchain.memory import ConversationBufferMemory

from src.chatbot.llm_providers import get_llm
from src.chatbot.tools.order_tracking_tool import OrderTrackingTool
from src.chatbot.tools.order_cancellation_tool import OrderCancellationTool
from src.chatbot.agent import create_order_management_agent

from src.chatbot.prompts.prompt_utils import load_prompt_from_file
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from dotenv import load_dotenv
load_dotenv() 

class ChatbotService:
    def __init__(self, cfg: DictConfig):
        self.cfg = cfg
        self.llm = get_llm(cfg.order_agent.llm)

        # Initialize Tools
        track_order_config = next(
            ep for ep in cfg.order_agent.mock_api_service.endpoints 
            if ep.name == "get_order"
        )
        self.order_tracking_tool = OrderTrackingTool(
            mock_api_base_url=cfg.order_agent.mock_api_service.base_url,
            track_order_endpoint_template=track_order_config.url
        )

        cancel_order_config = next(
            ep for ep in cfg.order_agent.mock_api_service.endpoints
            if ep.name == "cancel_order"
        )
        self.order_cancellation_tool = OrderCancellationTool(
            mock_api_base_url=cfg.order_agent.mock_api_service.base_url,
            cancel_order_endpoint_template=cancel_order_config.url
        )
        
        self.tools = [self.order_tracking_tool, self.order_cancellation_tool]

        # Create Agent Executor using the new function
        # Pass the relevant parts of the configuration
        self.agent_executor = create_order_management_agent(
            llm=self.llm,
            tools=self.tools,
            agent_config=cfg.order_agent.agent, # Pass the agent sub-config
            prompt_config=cfg.order_agent.prompts # Pass the prompts sub-config
        )

        # Setup Memory - Now we need to add it to the executor here
        # The memory key must match the one in MessagesPlaceholder in the agent's prompt_template
        self.memory = ConversationBufferMemory(
            memory_key="chat_history", 
            return_messages=True
        )
        
        # Link memory to the agent_executor instance
        self.agent_executor.memory = self.memory


    def get_response(self, user_query: str, session_id: str = "default_session"):
        # session_id is not actively used with ConversationBufferMemory in this simple setup,
        # but good practice for more complex memory stores.
        
        response = self.agent_executor.invoke({"input": user_query})
        return response.get("output", "Sorry, I encountered an issue and couldn't respond.")

# Hydra main entry point (for testing from command line)
@hydra.main(config_path="../../configs", config_name="order_agent/default", version_base=None)
def main(cfg: DictConfig):
    print("Initializing Chatbot Service...")
    print("Effective configuration:\n", OmegaConf.to_yaml(cfg)) 
    
    service = ChatbotService(cfg)
    print("Chatbot Service Initialized. Type 'exit' to quit.")
    
    while True:
        user_input = input("You: ")
        if user_input.lower() == 'exit':
            print("Exiting chatbot.")
            break
        if not user_input.strip():
            continue
            
        bot_response = service.get_response(user_input)
        print(f"Bot: {bot_response}")

if __name__ == "__main__":
    main()
