from langchain.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from omegaconf import DictConfig

def create_order_management_agent(llm, tools: list, agent_config: DictConfig, system_prompt_content: str) -> AgentExecutor:
    """
    Creates and returns an AgentExecutor for order management.

    Args:
        llm: The initialized LangChain LLM instance.
        tools: A list of LangChain tools (e.g., OrderTrackingTool, OrderCancellationTool).
        agent_config: OmegaConf DictConfig for agent-specific settings (e.g., verbose).
                      (Currently, we don't have many specific agent configs other than verbose,
                       but this allows for future expansion).
        prompt_config: OmegaConf DictConfig for prompt settings, specifically the system_prompt path.

    Returns:
        A configured LangChain AgentExecutor.
    """

    # Define the prompt template for the OpenAI Tools agent
    # It requires "input" for user query, "agent_scratchpad" for intermediate steps,
    # and "chat_history" for memory (which will be handled by AgentExecutor's memory).
    prompt_template = ChatPromptTemplate.from_messages([
        ("system", system_prompt_content),
        MessagesPlaceholder(variable_name="chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    # Create the LangChain agent (OpenAI Tools agent in this case)
    agent = create_openai_tools_agent(
        llm=llm,
        tools=tools,
        prompt=prompt_template
    )

    # Create the Agent Executor
    # Memory will be added to the AgentExecutor in the ChatbotService,
    # as memory often needs to be managed per session or at a higher level.
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=agent_config.get("verbose", True), # Get verbose from config, default True
        return_intermediate_steps=True,
        # handle_parsing_errors=True # Consider adding for robustness
    )

    return agent_executor
