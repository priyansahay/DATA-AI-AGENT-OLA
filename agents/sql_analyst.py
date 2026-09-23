import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__),'..')))
from utils.llmpick import pick_llm
from Models.schema import AgentSchema, JudgeSchema
from utils.database import DatabaseUtil
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv
load_dotenv()
# AI AGENT CODE

def curate_ques(state: AgentSchema) -> AgentSchema:
    user_question = state.user_ques
    llm = pick_llm("low")
    response = llm.invoke(f"Curate the following Question: {user_question}.")
    state.curated_ques = response
    state.messages += [HumanMessage(content=f"{response}")] 
    return state

def prompt_query_context(state: AgentSchema) -> AgentSchema:
    curated_question = state.curated_ques
    conn_details = {
            "host": os.getenv("host"),
            "port": os.getenv("port"),
            "database": os.getenv("database"),
            "user": os.getenv("user"),
            "password": os.getenv("password")
    }
    obj = DatabaseUtil(conn_details)
    schema_info = obj.schema_details("public")
    prompt = f"""
        You are an SQL Analyst agent. Your task is to conver the user's natural languge query into PostgresSQL query that can be executed on the database
        You are provided with the user's original query and the schema details of the database, including table_names, column_names and sample data for each table
        so that you can understand the structure of the database and generate an accurate SQL query. Unless user explicitly asl for specific number of rows, always
        limit the output to 10 rows. Note - Just generate the SQL query without any explanation or additional text because this query will be executed directly
        on the database. SO the output should be SQL ready to be executed without any modification.

        User's Original Query: {curated_question}
        Database Schema Details: {schema_info}
        """
    state.prompt_quer_context = prompt
    llm = pick_llm("medium")
    generated_sql_query = llm.invoke(prompt)
    state.generated_sql_query = generated_sql_query
    return state


def generate_sql(state:AgentSchema) -> AgentSchema:
    prompt = state.prompt_query_contect
    llm = pick_llm("medium")
    generated_sql_query = llm.invoke(prompt)
    state.generated_sql_query = generated_sql_query
    return state

# LLM JUDGE IS SAFE CODE
def is_safe_sql(state: AgentSchema) -> AgentSchema:
    sql_query = state.generated_sql_query
    llm = pick_llm("medium")
    llm_judge = llm.with_structured_output(JudgeSchema)

    prompt = f"""
        You are an SQL Judge for data security. Your task is to determine wheather the SQL Query is safe or not.
        The SQL query should only be used for data retrieval ans should not modify the satabase in any condition. Neither the SQL query prompt should contain any SQL commands thatcan modify the 
        database, such as INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE, or any other commands that can change
        the structure or the contents of the database. If the SQL Query is safe, respond with 'Yes' otherwise respond with 'No'. Additionally
        provide comments explaining your decision.
        Here is the SQL Query to be evaluated: {sql_query} """

    response =llm_judge.invoke(prompt).model_dump()
    state.is_safe_sql_response = response["answer"]
    return state


