import os
import re
import sys
from pathlib import Path
from typing import Any

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph

from Models.schema import DataAgentSchema, WorkflowPlanSchema, WorkflowStepSchema
from agents.etl_analyst import etl_analyst
from agents.pdf_analyst import pdf_analyst
from agents.sql_analyst import sql_analyst
from agents.ui_automate import run_ui_automation
from utils.llmpick import pick_llm


ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

SPECIALISTS = ("sql", "etl", "pdf", "ui_automate")

llm = pick_llm("medium")
llm_planner = llm.with_structured_output(WorkflowPlanSchema)


def _message_text(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    return str(content)


def _step_for(state: DataAgentSchema) -> WorkflowStepSchema:
    if state.current_step >= len(state.workflow_steps):
        raise RuntimeError("The workflow has no pending specialist step.")
    step = state.workflow_steps[state.current_step]
    if isinstance(step, WorkflowStepSchema):
        return step
    return WorkflowStepSchema.model_validate(step)


def _step_request(state: DataAgentSchema, step: WorkflowStepSchema) -> str:
    previous_outputs = [
        _message_text(message)
        for message in state.messages
        if not isinstance(message, HumanMessage)
        and _message_text(message).strip()
    ]
    artifact_lines = [
        f"- {artifact.get('path', '')} ({artifact.get('type', 'file')})"
        for artifact in state.artifacts
        if artifact.get("path")
    ]

    sections = [
        f"Original user request:\n{state.original_question}",
        f"Current {step.agent} task:\n{step.instruction}",
    ]
    if artifact_lines:
        sections.append("Available files from earlier steps:\n" + "\n".join(artifact_lines))
    if previous_outputs:
        sections.append(
            "Outputs from earlier workflow steps:\n"
            + "\n\n".join(previous_outputs[-12:])
        )
    return "\n\n".join(sections)


def _artifact_paths_from_messages(messages: list[Any]) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    saved_path_pattern = re.compile(
        r"(?i)(?:saved to|saved at|save to|output path(?: is)?)\s+"
        r"(.+?)(?:\s+in\s+(?:csv|json|parquet)\s+format)?[.!]?$"
    )
    for message in messages:
        for line in _message_text(message).splitlines():
            match = saved_path_pattern.search(line.strip())
            if not match:
                continue
            raw_path = match.group(1).strip().strip("'\"").rstrip(".,;")
            candidate = Path(raw_path).expanduser()
            if not candidate.is_absolute():
                candidate = ROOT_DIR / candidate
            if candidate.is_file():
                artifact_type = candidate.suffix.lstrip(".") or "file"
                item = {"path": str(candidate), "type": artifact_type}
                if item not in artifacts:
                    artifacts.append(item)
    return artifacts


def _invoke_specialist(state: DataAgentSchema, agent_name: str) -> dict[str, Any]:
    step = _step_for(state)
    if step.agent != agent_name:
        raise RuntimeError(
            f"Workflow expected {step.agent!r}, but graph entered {agent_name!r}."
        )
    question = _step_request(state, step)
    if agent_name == "pdf":
        response = pdf_analyst.invoke(
            {"messages": [HumanMessage(content=question)]}
        )
    elif agent_name == "etl":
        response = etl_analyst.invoke(
            {"messages": [HumanMessage(content=question)]}
        )
    elif agent_name == "sql":
        response = sql_analyst.invoke(
            {
                "messages": [],
                "user_ques": question,
                "curated_ques": "",
                "prompt_query_context": "",
                "generated_sql_query": "",
                "is_safe": "No",
                "comments": "",
                "sql_query_execution_result": "",
                "final_response": "",
            }
        )
    else:
        raise ValueError(f"Unknown specialist agent: {agent_name}")

    messages = response.get("messages", [])
    known_paths = {artifact.get("path") for artifact in state.artifacts}
    artifacts = [
        artifact
        for artifact in _artifact_paths_from_messages(messages)
        if artifact["path"] not in known_paths
    ]
    return {
        "messages": messages,
        "artifacts": artifacts,
        "current_step": state.current_step + 1,
    }


def router_node(state: DataAgentSchema) -> dict[str, Any]:
    original_question = state.original_question
    if not original_question:
        original_question = next(
            (
                _message_text(message)
                for message in state.messages
                if isinstance(message, HumanMessage)
            ),
            "",
        )
    if not original_question.strip():
        raise ValueError("The data agent requires a user request.")

    planning_prompt = f"""
You are the supervisor for a four-agent data workflow. Build an ordered plan using
only the specialists required to complete the user's request. Use each specialist
at most once and return no more than four steps. Respect any order explicitly
requested by the user, and order other steps by their data dependencies.

Specialists:
- sql: query/analyze data already present in the configured PostgreSQL database.
  It cannot directly query a local CSV/JSON file.
- etl: extract API/tabular data, transform local tabular files, and export files.
- pdf: read/extract/analyze PDF documents and save structured JSON.
- ui_automate: interact with a website using browser UI automation; include the
  target URL in target_url when one is present in the user's request.

For each step, provide a concrete instruction that preserves the user's goal.
Later nodes receive previous node outputs and the file paths they produced, so
refer to those artifacts in the instruction when relevant. If the task is just a
database query, use sql alone. If a local file must be queried or transformed,
use etl rather than asking sql to query that file. If no specialist is needed,
return an empty plan.

User request:
{original_question}
"""
    plan = llm_planner.invoke(planning_prompt)
    steps = plan.steps if isinstance(plan, WorkflowPlanSchema) else plan["steps"]
    unique_steps = []
    seen_agents = set()
    for step in steps:
        normalized_step = (
            step
            if isinstance(step, WorkflowStepSchema)
            else WorkflowStepSchema.model_validate(step)
        )
        if normalized_step.agent not in SPECIALISTS:
            raise ValueError(f"Planner selected an unsupported agent: {normalized_step.agent}")
        if normalized_step.agent not in seen_agents:
            unique_steps.append(normalized_step)
            seen_agents.add(normalized_step.agent)

    updates: dict[str, Any] = {
        "original_question": original_question,
        "workflow_steps": unique_steps,
        "current_step": 0,
    }
    if not unique_steps:
        updates["messages"] = [
            AIMessage(
                content=(
                    "No SQL, ETL, PDF, or browser automation step was needed for "
                    "this request."
                )
            )
        ]
    return updates


def pdf_node(state: DataAgentSchema) -> dict[str, Any]:
    return _invoke_specialist(state, "pdf")


def etl_node(state: DataAgentSchema) -> dict[str, Any]:
    return _invoke_specialist(state, "etl")


def sql_node(state: DataAgentSchema) -> dict[str, Any]:
    return _invoke_specialist(state, "sql")


def ui_automate_node(state: DataAgentSchema) -> dict[str, Any]:
    step = _step_for(state)
    if step.agent != "ui_automate":
        raise RuntimeError(
            f"Workflow expected {step.agent!r}, but graph entered 'ui_automate'."
        )
    question = _step_request(state, step)
    result = run_ui_automation(
        task_prompt=question,
        target_url=step.target_url,
    )
    artifacts = [
        {"path": result["json_path"], "type": "json"},
    ]
    if result.get("csv_path"):
        artifacts.append({"path": result["csv_path"], "type": "csv"})

    message = AIMessage(
        content=(
            f"UI automation completed for {result['target_url']}.\n"
            f"Result: {result['summary']}\n"
            f"Structured JSON: {result['json_path']}\n"
            + (
                f"CSV export: {result['csv_path']}"
                if result.get("csv_path")
                else "No tabular records were returned, so no CSV was created."
            )
        )
    )
    return {
        "messages": [message],
        "artifacts": artifacts,
        "current_step": state.current_step + 1,
    }


def route_decision(state: DataAgentSchema) -> str:
    if state.current_step >= len(state.workflow_steps):
        return "end"
    step = _step_for(state)
    if step.agent not in SPECIALISTS:
        raise ValueError(f"Unsupported workflow agent: {step.agent}")
    return step.agent


data_agent_graph = StateGraph(DataAgentSchema)
data_agent_graph.add_node(router_node, name="router_node")
data_agent_graph.add_node(etl_node, name="etl_node")
data_agent_graph.add_node(sql_node, name="sql_node")
data_agent_graph.add_node(pdf_node, name="pdf_node")
data_agent_graph.add_node(ui_automate_node, name="ui_automate_node")

data_agent_graph.add_edge(START, "router_node")
route_targets = {
    "sql": "sql_node",
    "etl": "etl_node",
    "pdf": "pdf_node",
    "ui_automate": "ui_automate_node",
    "end": END,
}
data_agent_graph.add_conditional_edges("router_node", route_decision, route_targets)
for node_name in ("sql_node", "etl_node", "pdf_node", "ui_automate_node"):
    data_agent_graph.add_conditional_edges(node_name, route_decision, route_targets)

data_agent = data_agent_graph.compile()


if __name__ == "__main__":
    from IPython.display import Image

    graph_image = Image(data_agent.get_graph().draw_mermaid_png())
    with open(ROOT_DIR / "data_agent_graph.png", "wb") as image_file:
        image_file.write(graph_image.data)

    response = data_agent.invoke(
        {
            "messages": [
                HumanMessage(
                    content=(
                   "You are on a GitHub profile page. Click the Repositories tab, inspect the "
                   "repositories, and identify all AI, Machine Learning, LLM, NLP, RAG, or "
                   "Data Science related projects. Return the complete list and the total count and save it in json file in folder data/extracted."
                    )
                )
            ]
        }
    )
    print(response)
