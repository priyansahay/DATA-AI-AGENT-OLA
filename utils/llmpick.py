from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from dotenv import load_dotenv
load_dotenv()

def pick_llm(level:str):
    """
    pick the appropiate LLM based on the level of question.
    Args: level(str): The level of question can be "easy", "medium" or "hard".
    Return: STRING the name of LLM used.
    """
    level = level.lower()
    if level == "low":
        llm = ChatOpenAI(model_name = "gpt-5.6-luna", temperature = 0)
    elif level == "medium":
        llm = ChatOpenAI(model_name = "gpt-5.6-terra", temperature = 0)
    elif level == "high":
        llm = ChatAnthropic(model_name = "claude-haiku-5", temperature = 0) 
    else:
        raise ValueError(f"Unsupported level: {level}")
    return llm



