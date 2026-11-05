import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__),'..')))

from langchain_core.messages import SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph

from Models.schema import ETLAgentSchema
from tools.pdf_tools import extract_pdf_tool
from utils.llmpick import pick_llm


tools = [extract_pdf_tool]
tools_by_name = {agent_tool.name: agent_tool for agent_tool in tools}
llm = pick_llm("medium")
llm_bind = llm.bind_tools(tools)


def llm_node(state: ETLAgentSchema):
    prompt = """
        You are a PDF analyst. Help the user extract or analyze information from
        PDF documents. When a PDF path is available, call extract_pdf_tool and
        pass the user's complete request as custom_prompt so requested fields
        and output structure are preserved. If the PDF path is missing, ask the
        user for it rather than guessing. Report the JSON output path after a
        successful extraction.
    """
    assistant_message = llm_bind.invoke(
        [SystemMessage(content=prompt), *state.messages]
    )
    return {"messages": [assistant_message]}


def tool_node(state: ETLAgentSchema):
    tool_results = []
    for tool_call in state.messages[-1].tool_calls:
        agent_tool = tools_by_name[tool_call["name"]]
        observation = agent_tool.invoke(tool_call["args"])
        tool_results.append(
            ToolMessage(content=observation, tool_call_id=tool_call["id"])
        )
    return {"messages": tool_results}


def is_tool_call(state: ETLAgentSchema) -> str:
    if state.messages[-1].tool_calls:
        return "tool_node"
    return "end"


pdf_analyst_graph = StateGraph(ETLAgentSchema)
pdf_analyst_graph.add_node(llm_node, name="llm_node")
pdf_analyst_graph.add_node(tool_node, name="tool_node")
pdf_analyst_graph.add_edge(START, "llm_node")
pdf_analyst_graph.add_conditional_edges(
    "llm_node",
    is_tool_call,
    {"tool_node": "tool_node", "end": END},
)
pdf_analyst_graph.add_edge("tool_node", "llm_node")

pdf_analyst = pdf_analyst_graph.compile()
if __name__ == "__main__":
    from IPython.display import display, Image
    img = Image(pdf_analyst.get_graph().draw_mermaid_png())
    with open("pdf_analyst_graph.png", "wb") as f:
        f.write(img.data)