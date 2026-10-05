import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__),'..')))

from utils.etl_tools import ETLTools
from Models.schema import ETLAgentSchema
from utils.database import DatabaseUtil
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from dotenv import load_dotenv
from langchain.tools import tool
from utils.llmpick import pick_llm
from langchain_openai import OpenAI

# ETL AGENT
@tool
def extract_load_tool(url:str, output_folder:str, format: str) -> str:
    etl_tools = ETLTools()
    return etl_tools.extract_load (url, output_folder, format)

@tool
def transform_load_tool(input_file_path:str, output_folder:str, output_format:str, user_question:str) -> str:
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
    return results