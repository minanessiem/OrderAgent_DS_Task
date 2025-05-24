# src/chatbot/prompts/prompt_utils.py
from pathlib import Path
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from typing import Optional, Dict, Any
import re # For finding placeholders
import warnings # For issuing warnings

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

def inject_placeholders(prompt_template: str, placeholders: Dict[str, Any]) -> str:
    """
    Injects placeholder values into a prompt template string.

    The prompt template should use placeholders like {key_name}.

    Args:
        prompt_template: The string template with placeholders.
        placeholders: A dictionary where keys are placeholder names (without curly braces)
                      and values are the strings to insert.

    Returns:
        The prompt string with placeholders filled.

    Raises:
        Warnings: If a placeholder in the prompt_template is not found in the placeholders dict.
    """
    # Find all unique placeholders in the template (e.g., {key_name})
    # Using a set to avoid duplicate warnings for the same missing key
    required_placeholders = set(re.findall(r"\{(.*?)\}", prompt_template))
    
    filled_prompt = prompt_template
    
    # Check for missing placeholders and issue warnings
    for req_key in required_placeholders:
        if req_key not in placeholders:
            warnings.warn(
                f"Placeholder '{{{req_key}}}' found in prompt template but not in provided placeholders dictionary. "
                f"It will remain unchanged in the output.",
                UserWarning
            )
        else:
            # Replace placeholder if key exists
            # We do a direct replacement here. For more complex scenarios with f-string like capabilities,
            # str.format_map might be an option, but it has stricter error handling for missing keys.
            # Direct replacement with a loop gives us more control over warnings.
            filled_prompt = filled_prompt.replace(f"{{{req_key}}}", str(placeholders[req_key]))

    # Optional: Check for unused placeholders in the provided dict (more for debugging the calling code)
    # for provided_key in placeholders.keys():
    #     if provided_key not in required_placeholders:
    #         warnings.warn(
    #             f"Placeholder key '{provided_key}' was provided in the dictionary but not found in the prompt template.",
    #             UserWarning
    #         )
            
    return filled_prompt
