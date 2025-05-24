import os
from langchain_openai import ChatOpenAI
from omegaconf import DictConfig
# Potentially add other providers like from langchain_community.llms import Ollama etc.

def get_llm(llm_config: DictConfig):
    """
    Initializes and returns an LLM instance based on the provided configuration.

    Args:
        llm_config: An OmegaConf DictConfig object containing LLM settings
                    (e.g., provider, model_name, api_key, temperature).
    
    Returns:
        A LangChain LLM instance.
        
    Raises:
        ValueError: If the provider is not supported or API key is missing for OpenAI.
    """
    provider = llm_config.get("provider")
    model_name = llm_config.get("model_name")
    temperature = llm_config.get("temperature", 0)
    api_key_env = llm_config.get("api_key_env_var") # LLM Config API Key Environment Variable
    
    if provider == "openai":
        api_key = None
        if api_key_env:
            api_key = os.getenv(api_key_env)
        
        # Fallback to direct api_key from config if env var not set/found
        # (though env var is preferred for security)
        if not api_key and llm_config.get("api_key"):
            api_key = llm_config.get("api_key")

        if not api_key:
            raise ValueError(
                "OpenAI API key not found. "
                "Please set it via the environment variable specified in "
                "llm_config.api_key_env_var or directly in llm_config.api_key."
            )
            
        return ChatOpenAI(
            model_name=model_name,
            temperature=temperature,
            api_key=api_key
            # Add other OpenAI specific parameters from llm_config if needed
            # e.g., request_timeout=llm_config.get("request_timeout")
        )
    # TODO: add Anthropic
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")
