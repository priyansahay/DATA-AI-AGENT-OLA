import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__),'..')))

from utils.etl_tools import ETLTools
from Models.schema import ETLAgentSchema
from utils.database import DatabaseUtil
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from dotenv import load_dotenv
from langchain.tools import tool
from utils.llmpick import pick_llm
from langchain_openai import OpenAI

# ETL AGENT
@tool
def extract_load_tool(url:str, output_folder:str, format: str) -> str:
    """Extract data from a URL and save it to the output folder in the requested format."""
    etl_tools = ETLTools()
    return etl_tools.extract_load (url, output_folder, format)

@tool
def transform_load_tool(input_file_path:str, output_folder:str, output_format:str, user_question:str) -> str:
    """Transform a data file to answer the user's question and save it in the requested format."""
    etl_tools = ETLTools()
    top_3_rows = etl_tools.transform_load_context(input_file_path, output_folder, output_format)
    llm = pick_llm("medium")
    prompt = f"""
            You are a Python Data Analyst who uses Pandas to analyze data. 
            You need to provide only the Pandas Code that will help to perform the right ETL operations on the data stored in the file : {input_file_path}
            as per the user's question. Do not provide any explanation or comments, only
            the code should be provided. The code should be in a format that can be executed 
            in a Python environment with Pandas installed. 
            Don't write anything else than Pandas Code. \n
            
            Create the Pandas Dataframe from the data stored in the file : {input_file_path} and then 
            write the code to transform and save the data at {output_folder}.
            Here's the user's question: {user_question}\n
            Here's the context of the data you will be analyzing: {top_3_rows}\n
         """
    response = llm.invoke(prompt).content
    pandas_code = response.strip().strip('```').strip().lstrip('python').strip()
    results= etl_tools.execute_code(pandas_code)
    return f"The data is transformed and saved at {output_folder} in {output_format} format. \n\n Pandas Code Executed: \n {pandas_code} \n\n Execution Result: \n {results}"

tools=[extract_load_tool, transform_load_tool]
llm = pick_llm("medium")
llm_bind = llm.bind_tools(tools)

# AGENT GRAPH
def llm_node(state: ETLAgentSchema):
    messages = state.messages
    prompt = f"""
            You are a Python Data Analyst who has access to tools that can extract and load, 
            transform and load data. You will be provided with a user's question 
            and you would need to perform the right ETL operations as per the user's question. 
            If the operation is performed then inform the user and end the coversation.
            Here's the chat history: {messages}\n
    """
    final_answer = llm_bind.invoke(prompt).content
    state.messages = messages + [final_answer]
    return state

def tool_node(state: ETLAgentSchema):
    tools_result = []
    tools_by_name = {tool.name: tool for tool in tools}
    tool_calls = state.messages[-1].tool_calls
    for i in tool_calls:
        tool = tools_by_name[i['name']]
        observation = tool.invoke(i['args'])
        tools_result.append(ToolMessage(content =observation, tool_call_id = i['id']))
    state.messages = state.messages + tools_result
    return state

# AGENT NODE AND EDGES
etl_analyst_graph = StateGraph(ETLAgentSchema)
etl_analyst_graph.add_node(llm_node, name="llm_node")
etl_analyst_graph.add_node(tool_node, name="tool_node")

etl_analyst_graph.add_edge(START, "llm_node")

def is_tool_call(state:ETLAgentSchema):
    tool_calls = state.messages[-1].tool_calls
    if tool_calls:
        return "tool_node"
    else:
        return "end"

etl_analyst_graph.add_conditional_edges(
    "llm_node", is_tool_call,{
        "tool_node": "tool_node",
        "end": END
    }
)
etl_analyst_graph.add_edge("tool_node", "llm_node")




if __name__ == "__main__":
    etl_analyst = etl_analyst_graph.compile()
    from IPython.display import display, Image
    img = Image(etl_analyst.get_graph().draw_mermaid_png())
    with open("etl_analyst_graph.png", "wb") as f:
        f.write(img.data)

