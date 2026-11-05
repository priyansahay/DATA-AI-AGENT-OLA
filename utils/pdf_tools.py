import base64
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _extract_response_text(response) -> str:
    """Get generated text from the Responses API convenience field or output blocks."""
    extracted_text = getattr(response, "output_text", None)
    if extracted_text and extracted_text.strip():
        return extracted_text

    text_blocks = []
    refusals = []
    for output_item in getattr(response, "output", None) or []:
        if getattr(output_item, "type", None) != "message":
            continue
        for content in getattr(output_item, "content", None) or []:
            content_type = getattr(content, "type", None)
            if content_type == "output_text":
                text = getattr(content, "text", None)
                if text and text.strip():
                    text_blocks.append(text)
            elif content_type == "refusal":
                refusal = getattr(content, "refusal", None)
                if refusal:
                    refusals.append(refusal)

    if text_blocks:
        return "\n".join(text_blocks)

    status = getattr(response, "status", "unknown")
    details = getattr(response, "incomplete_details", None)
    response_id = getattr(response, "id", None)
    failure_details = [f"status={status}"]
    if details:
        failure_details.append(f"incomplete_details={details}")
    if refusals:
        failure_details.append(f"refusal={'; '.join(refusals)}")
    if response_id:
        failure_details.append(f"response_id={response_id}")
    raise ValueError(
        "The PDF extraction model returned no JSON text "
        f"({', '.join(failure_details)})."
    )


def extract_pdf_to_json(
    pdf_path: str,
    custom_prompt: str,
    output_dir: str | Path = PROJECT_ROOT / "data" / "extracted",
) -> Path:
    """Extract structured information from a PDF and save it as JSON."""
    source_path = Path(pdf_path).expanduser()
    if not source_path.is_absolute():
        source_path = PROJECT_ROOT / source_path
    if source_path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file, received: {source_path}")
    if not source_path.is_file():
        raise FileNotFoundError(f"PDF file not found: {source_path}")

    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY is required for PDF extraction.")

    pdf_data = base64.b64encode(source_path.read_bytes()).decode("ascii")
    response = OpenAI().responses.create(
        model="gpt-4o",
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Analyze the attached PDF, including scanned or "
                            "image-based pages. Follow the user's extraction "
                            "instructions and return the result as a JSON object. "
                            "Use null for requested values that are not present "
                            "rather than guessing.\n\n"
                            f"User's extraction instructions:\n{custom_prompt}"
                        ),
                    },
                    {
                        "type": "input_file",
                        "filename": source_path.name,
                        "file_data": f"data:application/pdf;base64,{pdf_data}",
                    },
                ],
            }
        ],
        text={"format": {"type": "json_object"}},
    )

    extracted_text = _extract_response_text(response)
    extracted_data = json.loads(extracted_text)
    if not isinstance(extracted_data, dict):
        raise ValueError("The PDF extraction model must return a JSON object.")

    destination_dir = Path(output_dir).expanduser()
    if not destination_dir.is_absolute():
        destination_dir = PROJECT_ROOT / destination_dir
    destination_dir.mkdir(parents=True, exist_ok=True)
    output_path = destination_dir / f"{source_path.stem}_extracted.json"
    output_path.write_text(
        json.dumps(extracted_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path
