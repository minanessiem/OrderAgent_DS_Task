# src/chatbot/prompts/prompt_utils.py
from pathlib import Path
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from typing import Optional

def load_prompt_from_file(file_path: str) -> str:
    """Loads prompt content from a specified file."""
    try:
        return Path(file_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise FileNotFoundError(f"Prompt file not found: {file_path}")
    except Exception as e:
        raise Exception(f"Error reading prompt file {file_path}: {e}")

def create_chat_prompt_template(system_prompt_str: str, user_prompt_str: Optional[str] = None) -> ChatPromptTemplate:
    """
    Creates a ChatPromptTemplate from system and optional user prompt strings.
    Assumes user prompt will take 'input' and 'agent_scratchpad' variables if it's for an agent.
    Or just 'input' for simpler cases.
    """
    messages = [SystemMessagePromptTemplate.from_template(system_prompt_str)]
    if user_prompt_str:
        # Standard for many agents expecting history and last input
        # For ReAct or OpenAI Tools agents, the exact format might vary slightly
        # or be handled by helper functions like `create_openai_tools_agent`.
        # For now, let's keep it simple; we'll adjust when building the agent.
        messages.append(HumanMessagePromptTemplate.from_template(user_prompt_str)) 
    
    # If not using a specific user_prompt_str, Langchain agents often require specific input variables.
    # For OpenAI tools agent, it typically requires "input" and "chat_history".
    # Let's construct a generic one here if no user_prompt_str is provided,
    # and let the agent construction handle specifics.
    if not user_prompt_str:
        # This is a common structure for agents like OpenAI Tools or XML Agent
        messages.append(HumanMessagePromptTemplate.from_template("{input}"))
        # We might also need placeholders for chat_history if we directly use AgentExecutor
        # with memory. Langchain's `create_openai_tools_agent` handles this implicitly.

    return ChatPromptTemplate.from_messages(messages)
