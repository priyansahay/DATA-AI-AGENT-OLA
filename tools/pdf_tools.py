import json

from langchain.tools import tool

from utils.pdf_tools import extract_pdf_to_json


@tool
def extract_pdf_tool(pdf_path: str, custom_prompt: str) -> str:
    """Extract information from a PDF and save the structured result as JSON.

    Use the user's PDF path and preserve their requested fields, output shape,
    and analysis instructions in custom_prompt.
    """
    output_path = extract_pdf_to_json(pdf_path, custom_prompt)
    extracted_data = json.loads(output_path.read_text(encoding="utf-8"))
    return (
        f"PDF extraction completed. JSON saved to {output_path}.\n"
        f"Extracted data:\n{json.dumps(extracted_data, ensure_ascii=False, indent=2)}"
    )
