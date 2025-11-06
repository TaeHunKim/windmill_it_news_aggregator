import wmill
from typing import TypedDict
import requests
import telegramify_markdown
import google.generativeai as genai
import json
import time
from google.api_core.exceptions import ResourceExhausted
import trafilatura
from bs4 import BeautifulSoup

genai.configure(api_key=wmill.get_variable("u/rapaellk/googleai_api_key_free"))

def process_text_with_gemini(text_input, max_retries=3, delay_seconds=60):
    """
    Processes a single text string using the Gemini API.
    
    It follows the logic in SYSTEM_PROMPT and handles rate limiting.
    
    Args:
        text_input (str): The raw English text to process.
        max_retries (int): Max number of retries on rate limit errors.
        delay_seconds (int): Seconds to wait between retries.

    Returns:
        dict: A dictionary in the format {'english': '...', 'korean': '...'}
              or None if processing fails after retries.
    """

    # This system prompt contains all the logic you requested.
    # The model will follow these rules.
    SYSTEM_PROMPT = """
    You are a text processing expert. Your task is to process the given English text and return a JSON object.

    Follow these steps precisely:
    1.  First, clean the input text by removing all XML, HTML, and Markdown syntax (e.g., tags like <p>, <div>, and markers like **, #, [text](link)). Get the raw, plain text content.
    2.  Count the number of sentences in this *cleaned* plain text.
    3.  Apply logic based on the sentence count:
        -   **If 2 sentences or fewer:** The 'english' field in the JSON must be the original *cleaned* text, exactly as it is.
        -   **If 3 sentences or more:** The 'english' field in the JSON must be a concise, one-or-two-sentence summary of the *cleaned* text.
    4.  Translate the content of the 'english' field (whether it's the original text or the summary) into Korean. Put this translation in the 'korean' field.
    5.  Return *only* the final JSON object, with the exact schema: {"english": "...", "korean": "..."}.
        Do not include any other text, explanations, or markdown delimiters (like ```json).
    """

    # Configure the model to use the system prompt and JSON output mode
    model = genai.GenerativeModel(
        'gemini-2.5-flash',
        system_instruction=SYSTEM_PROMPT,
        generation_config={
            "response_mime_type": "application/json",
            "temperature": 0.0  # <-- Add this line for maximum predictability
        }
    )
    current_try = 0
    while current_try <= max_retries:
        try:
            # Send the text to the model.
            # The model already knows the rules from the SYSTEM_PROMPT.
            response = model.generate_content(text_input)
            
            # The model, in JSON mode, should return a clean JSON string.
            # We parse it into a Python dictionary.
            result_json = json.loads(response.text)
            return result_json

        except ResourceExhausted as e:
            # This exception is thrown on HTTP 429 (Rate Limit / Token Limit)
            current_try += 1
            if current_try > max_retries:
                print(f"[Error] Max retries reached for input: {text_input[:50]}...")
                print(f"Last error: {e}")
                raise
            
            print(f"[Warning] Rate limit exceeded. Waiting for {delay_seconds} seconds... (Attempt {current_try}/{max_retries})")
            time.sleep(delay_seconds)
        
        except json.JSONDecodeError as e:
            # The model returned invalid JSON
            print(f"[Error] Failed to decode JSON from model response.")
            print(f"       Input text was: {text_input[:100]}...")
            print(f"       Model response was: {response.text}")
            raise e
        
        except Exception as e:
            # Catch other potential errors (e.g., connection issues)
            print(f"[Error] An unexpected error occurred: {e}")
            raise e

    raise RuntimeError("Unknown error from AI process")

def split_string_by_lines(long_string: str, max_length: int = 4096) -> list[str]:
    """
    긴 문자열을 max_length 미만의 청크로 나눕니다.
    단, 라인의 중간이 잘리지 않도록 보장합니다.

    Args:
        long_string (str): 분할할 원본 문자열.
        max_length (int): 각 청크의 최대 길이 (이 길이 미만).

    Returns:
        list[str]: 분할된 문자열 청크 리스트.
        
    참고:
    만약 한 줄 자체가 max_length보다 긴 경우,
    "라인 중간을 자르지 않는다"는 규칙을 우선하여 해당 라인 하나가
    하나의 청크를 구성하게 됩니다. 이 경우 해당 청크는 max_length를 초과할 수 있습니다.
    """
    
    # 1. 문자열을 라인별로 나눕니다. (개행 문자를 보존합니다)
    lines = long_string.splitlines(keepends=True)
    
    chunks = []
    current_chunk = ""
    
    for line in lines:
        # 2. 만약 한 줄 자체가 max_length보다 긴 경우 (예외 케이스)
        #    "라인을 자르지 않는다"는 규칙을 우선합니다.
        if len(line) >= max_length:
            # 현재까지 누적된 청크가 있다면 먼저 추가합니다.
            if current_chunk:
                chunks.append(current_chunk)
            
            # 이 긴 라인을 그 자체로 하나의 청크로 추가합니다.
            chunks.append(line)
            
            # 현재 청크를 리셋하고 다음 라인으로 넘어갑니다.
            current_chunk = ""
            continue
            
        # 3. 현재 라인을 추가했을 때 max_length를 초과하는지 확인합니다.
        if len(current_chunk) + len(line) >= max_length:
            # 초과한다면, 현재까지의 청크를 리스트에 추가합니다.
            if current_chunk: # 빈 문자열이 아닐 경우에만 추가
                chunks.append(current_chunk)
            
            # 새 청크는 현재 라인으로 시작합니다.
            current_chunk = line
        else:
            # 4. max_length를 초과하지 않으면, 현재 청크에 라인을 누적합니다.
            current_chunk += line
            
    # 5. 마지막에 current_chunk에 남아있는 문자열이 있다면 추가합니다.
    if current_chunk:
        chunks.append(current_chunk)
        
    return chunks

class telegram(TypedDict):
    token: str

def send_to_telegram(message: str, chat_id: int = int(wmill.get_variable("u/rapaellk/telegram_chat_id")), escaped: bool = False, token = wmill.get_resource("u/rapaellk/telegram_token_resource")):
    telegram_url = f"https://api.telegram.org/bot{token['token']}/sendMessage"
    text = message
    if not escaped:
        text = telegramify_markdown.markdownify(message),
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode":'MarkdownV2'
    }
    response = requests.post(telegram_url, data=payload)
    return response.json()

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36'
}

def send_long_message_to_telegram(message: str, chat_id: int = int(wmill.get_variable("u/rapaellk/telegram_chat_id")), token = wmill.get_resource("u/rapaellk/telegram_token_resource")):
    splitted_msg = split_string_by_lines(message)
    for m in splitted_msg:
        send_to_telegram(m, chat_id, token=token)

def get_content_from_link(url):
    try:
        response = requests.get(
            url, 
            headers=HEADERS,  # 준비된 헤더 사용
            timeout=10        # 10초 이상 걸리면 중단
        )
        if response.status_code != 200:
            print("Failed to get html")
            return None
        downloaded_html = response.text
        if downloaded_html is None:
            print("Empty html")
            return None
        full_text = trafilatura.extract(
            downloaded_html,
            output_format='txt',      # 'txt' (기본값), 'json', 'xml' 등
            include_comments=False,   # 댓글 제외
            include_tables=False,     # 표(테이블) 제외
            no_fallback=False         # 기본 추출 실패 시 다른 방법 시도
        )
        if not full_text:
            print("too short html")
            return None
        return full_text
    except Exception as e:
        print(e)
        return None

def remove_html_tags_bs4(html_string):
    """
    Removes HTML tags from a string using BeautifulSoup and extracts pure text.
    """
    soup = BeautifulSoup(html_string, 'html.parser')
    return soup.get_text()


def main(x: str):
    return send_long_message_to_telegram(x)
