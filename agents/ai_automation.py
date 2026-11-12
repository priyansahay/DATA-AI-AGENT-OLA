import os
import sys
import time
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from google import genai
from google.genai import types, errors
from google.genai.types import Content, Part

# Add project root to sys.path and load the root .env file
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(ROOT_DIR)
load_dotenv(os.path.join(ROOT_DIR, '.env'))

# 1. Fixed viewport dimensions so normalized coordinates (0-1000) map cleanly
SCREEN_WIDTH = 1440
SCREEN_HEIGHT = 900

# Ordered list of Computer Use supported models for automatic fallback on 503/429
FALLBACK_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
]

# 2. Define the target URL
TARGET_URL = "https://github.com/priyansahay"


def denorm_x(x: int) -> int:
    return int((x / 1000.0) * SCREEN_WIDTH)


def denorm_y(y: int) -> int:
    return int((y / 1000.0) * SCREEN_HEIGHT)


def generate_with_fallback(client, contents, config, max_retries_per_model=2):
    """Calls generate_content with exponential backoff and model fallback on 503/429/500."""
    for model_id in FALLBACK_MODELS:
        for attempt in range(1, max_retries_per_model + 1):
            try:
                print(f"  [Model] Calling {model_id} (Attempt {attempt}/{max_retries_per_model})...")
                return client.models.generate_content(
                    model=model_id,
                    contents=contents,
                    config=config,
                )
            except errors.APIError as e:
                # 503 = Server overloaded, 429 = Rate limit/Quota, 500 = Internal error
                if e.code in (503, 429, 500):
                    wait_time = 2 ** attempt
                    print(
                        f"  [Warning] {model_id} returned {e.code} ({e.message}). "
                        f"Retrying in {wait_time}s..."
                    )
                    time.sleep(wait_time)
                else:
                    # Raise immediately on non-transient errors (e.g., 400 Bad Request, 403 Auth)
                    raise
        print(f"  [Fallback] Switching from {model_id} to next available Computer Use model...")

    raise RuntimeError("All Computer Use fallback models are currently unavailable.")


def execute_action(page, fn_call) -> dict:
    """Executes a single Gemini Computer Use function call in Playwright."""
    name = fn_call.name
    args = fn_call.args or {}
    print(f"  -> Action: {name} | Args: {args}")

    try:
        if name in ("click", "click_at"):
            page.mouse.click(denorm_x(args["x"]), denorm_y(args["y"]))
        elif name in ("double_click", "double_click_at"):
            page.mouse.dblclick(denorm_x(args["x"]), denorm_y(args["y"]))
        elif name in ("type", "type_text_at"):
            # Click the field first if coordinates are provided alongside text
            if "x" in args and "y" in args:
                page.mouse.click(denorm_x(args["x"]), denorm_y(args["y"]))
            if args.get("clear_before_typing", False):
                page.keyboard.press("Meta+A")
                page.keyboard.press("Backspace")
            page.keyboard.type(args.get("text", ""), delay=30)
            if args.get("press_enter", False):
                page.keyboard.press("Enter")
        elif name in ("key_combination", "hotkey", "press_key"):
            key = args.get("key") or "+".join(args.get("keys", []))
            if key:
                page.keyboard.press(key)
        elif name in ("scroll", "scroll_at", "scroll_page"):
            if "x" in args and "y" in args:
                page.mouse.move(denorm_x(args["x"]), denorm_y(args["y"]))
            dx = args.get("delta_x", 0)
            dy = args.get(
                "delta_y",
                500 if args.get("direction", "down") == "down" else -500,
            )
            page.mouse.wheel(dx, dy)
        elif name in ("wait", "wait_5_seconds"):
            time.sleep(args.get("seconds", 3))
        elif name in ("navigate", "open_url"):
            page.goto(args["url"], wait_until="domcontentloaded")
        elif name == "go_back":
            page.go_back()

        time.sleep(1.0)  # Brief pause for UI animations/navigation to settle
        return {"status": "success", "url": page.url}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def run_form_automation():
    # Load .env from root or current working directory
    load_dotenv(os.path.join(ROOT_DIR, '.env'))
    load_dotenv()

    # Check common variable names used across LangChain / Gemini projects
    api_key = (
        os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or os.getenv("GEMINI_KEY")
        or os.getenv("API_KEY")
    )

    if not api_key:
        found_vars = [
            k for k in os.environ.keys()
            if "KEY" in k or "GEMINI" in k or "GOOGLE" in k
        ]
        raise ValueError(
            f"API key not found! Checked {os.path.join(ROOT_DIR, '.env')}. "
            f"Matching env vars currently loaded: {found_vars}"
        )

    client = genai.Client(api_key=api_key)

    # Enable the native Computer Use tool for the browser environment
    config = types.GenerateContentConfig(
        tools=[
            types.Tool(
                computer_use=types.ComputerUse(
                    environment=types.Environment.ENVIRONMENT_BROWSER,
                    enable_prompt_injection_detection=True,
                )
            )
        ]
    )

    with sync_playwright() as p:
        # Uses your Mac's installed Google Chrome (or change to channel="msedge" for Edge)
        browser = p.chromium.launch(channel="chrome", headless=False)
        context = browser.new_context(
            viewport={"width": SCREEN_WIDTH, "height": SCREEN_HEIGHT}
        )
        page = context.new_page()

        print(f"Navigating to {TARGET_URL}...")
        page.goto(TARGET_URL, wait_until="domcontentloaded")
        time.sleep(1.5)

        # Initial prompt + compressed JPEG screenshot
        prompt = (
            "You are on a GitHub profile page.\n"
            "1. Click on the 'Repositories' tab to view all repositories in the profile.\n"
            "2. Scroll through the repositories list if needed to inspect all of them.\n"
            "3. Identify all AI, Machine Learning, LLM, NLP, RAG, or Data Science related repositories.\n"
            "4. Once you have seen the repositories, respond with the complete list of AI-related "
            "projects and the total count of AI-related projects."
        )
        screenshot = page.screenshot(type="jpeg", quality=80)

        contents = [
            Content(
                role="user",
                parts=[
                    Part.from_text(text=prompt),
                    Part.from_bytes(data=screenshot, mime_type="image/jpeg"),
                ],
            )
        ]

        # Agent Loop (Max 15 steps to prevent infinite loops)
        for step in range(1, 16):
            print(f"\n--- Step {step} ---")
            response = generate_with_fallback(
                client=client,
                contents=contents,
                config=config,
            )

            candidate = response.candidates[0]
            contents.append(candidate.content)

            # Check if Gemini is done (no more function calls)
            if not response.function_calls:
                print(f"\nTask Complete! Gemini says:\n{response.text}")
                break

            # Execute all returned UI actions
            fn_response_parts = []
            for fn_call in response.function_calls:
                result = execute_action(page, fn_call)
                new_screenshot = page.screenshot(type="jpeg", quality=80)

                # Send the action result + updated screenshot back to Gemini
                fn_response_parts.append(
                    Part.from_function_response(
                        name=fn_call.name,
                        response=result,
                    )
                )
                fn_response_parts.append(
                    Part.from_bytes(data=new_screenshot, mime_type="image/jpeg")
                )

            contents.append(Content(role="user", parts=fn_response_parts))

        time.sleep(5)
        browser.close()


if __name__ == "__main__":
    run_form_automation()