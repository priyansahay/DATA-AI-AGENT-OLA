import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, START, END

from Models.schema import DataAgentSchema, RouterSchema
from agents.etl_analyst import etl_analyst
from agents.sql_analyst import sql_analyst
from utils.llmpick import pick_llm

load_dotenv()

llm = pick_llm("medium")
llm_router = llm.with_structured_output(RouterSchema)


def router_node(state: DataAgentSchema):
    last_message = state.messages[-1]
    question = last_message.content if hasattr(last_message, "content") else str(last_message)
    route_response = llm_router.invoke(question).model_dump()
    state.route_response = RouterSchema(**route_response)
    return state


def etl_node(state: DataAgentSchema):
    last_message = state.messages[-1]
    question = last_message.content if hasattr(last_message, "content") else str(last_message)
    response = etl_analyst.invoke({"messages": [HumanMessage(content=question)]})
    state.messages = state.messages + response.get("messages", [])
    return state


def sql_node(state: DataAgentSchema):
    last_message = state.messages[-1]
    question = last_message.content if hasattr(last_message, "content") else str(last_message)
    input_schema = {
        "messages": [],
        "user_ques": question,
        "curated_ques": "",
        "prompt_query_context": "",
        "generated_sql_query": "",
        "is_safe": "No",
        "comments": "",
        "sql_query_execution_result": "",
        "final_response": ""
    }
    response = sql_analyst.invoke(input_schema)
    state.messages = state.messages + response.get("messages", [])
    return state


def route_decision(state: DataAgentSchema) -> str:
    if state.route_response is None:
        return "sql"
    return state.route_response.answer


# DATA AGENT GRAPH

data_agent_graph = StateGraph(DataAgentSchema)
data_agent_graph.add_node(router_node, name="router_node")
data_agent_graph.add_node(etl_node, name="etl_node")
data_agent_graph.add_node(sql_node, name="sql_node")

data_agent_graph.add_edge(START, "router_node")
data_agent_graph.add_conditional_edges(
    "router_node",
    route_decision,
    {
        "sql": "sql_node",
        "etl": "etl_node",
    },
)
data_agent_graph.add_edge("etl_node", END)
data_agent_graph.add_edge("sql_node", END)

data_agent = data_agent_graph.compile()

if __name__ == "__main__":
    from IPython.display import Image

    img = Image(data_agent.get_graph().draw_mermaid_png())
    with open("data_agent_graph.png", "wb") as f:
        f.write(img.data)

    user_input = {"messages": [HumanMessage(content="I want to extract data from an API and save it to CSV file")]}
    result = data_agent.invoke(user_input)
    print(result)
