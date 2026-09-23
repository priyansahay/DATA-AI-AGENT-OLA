import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__),'..')))
from utils.llmpick import pick_llm
from Models.schema import AgentSchema, JudgeSchema
from utils.database import DatabaseUtil
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv
load_dotenv()

llm = pick_llm("medium")
llm_judge = llm.with_structured_output(JudgeSchema)
prompt = """
You are an SQL Judge for data security. Your task is to determine wheather the SQL Query is safe or not.
The SQL query should only be used for data retrieval ans should not modify the satabase in any condition. Neither the SQL query prompt should contain any SQL commands thatcan modify the 
database, such as INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE, or any other commands that can change
the structure or the contents of the database. If the SQL Query is safe, respond with 'Yes' otherwise respond with 'No'. Additionally
provide comments explaining your decision.
Here is the SQL Query to be evaluated: {sql_query} """

print(llm_judge.invoke(prompt))
