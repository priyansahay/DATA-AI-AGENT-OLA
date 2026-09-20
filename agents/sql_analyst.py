import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__),'..')))
from utils.llmpick import pick_llm
from Models.schema import AgentSchema

# AI AGENT CODE

def curate_ques(state: AgentSchema) -> AgentSchema:
    user_question = state.user_ques
    llm = pick_llm("low")
    response = llm.invoke(f"Curate the following Question {user_question} to make it more clear and concise.")
    state.curated_ques = response
    return state



