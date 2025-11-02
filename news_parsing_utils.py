import wmill
from typing import TypedDict, Dict, Any
import requests
import telegramify_markdown
import google.generativeai as genai
import json
import time
from google.api_core.exceptions import ResourceExhausted
import trafilatura
from bs4 import BeautifulSoup

genai.configure(api_key=wmill.get_variable("u/admin/googleai_api_key_free"))

def process_weather_info_with_gemini(data: Dict[str, Any], max_retries=3, delay_seconds=60):
    # (1) 시스템 프롬프트: 모델의 역할, 규칙, 페르소나 정의
    SYSTEM_PROMPT = """
    당신은 날씨 데이터를 분석하여 사용자에게 조언을 주는 유용한 AI 비서입니다.
    당신의 유일한 임무는 입력된 JSON 날씨 데이터를 기반으로, 번역 및 외출 제안이 포함된 JSON 객체 하나를 반환하는 것입니다.
    다른 설명이나 텍스트를 절대 추가하지 마세요.

    다음은 'suggestion' 필드를 생성할 때 반드시 따라야 할 규칙입니다 (이 외에 다른 조언이 있다면 추가해도 좋습니다):
    - [강수] '오늘 강수 확률 (%)'가 30% 이상이면 우산을 챙기라는 조언을 포함합니다.
    - [대기질] '대기질 지수 (AQI)', '미세먼지 (PM2.5)', '초미세먼지 (PM10)', '오존 (O3)' 값에 '나쁨' 또는 '매우 나쁨'이 포함되면, 외출을 자제하거나 마스크 착용을 권장합니다.
    - [자외선] '오늘 자외선 지수 (UVI)'가 6 이상이면(높음), 8 이상이면(매우 높음) 자외선 차단제, 모자, 선글라스 등을 권장합니다.
    - [일교차] '최고 기온 (°C)'과 '최저 기온 (°C)'의 차이가 10도 이상이면 겉옷을 챙겨 체온 조절에 유의하라고 조언합니다.
    - [바람] '오늘 풍속 (m/s)'이 7 m/s 이상이면 바람이 강하게 분다는 사실을 언급합니다.
    - [긍정] 날씨와 공기 질이 모두 좋다면(예: 맑음, 강수확률 낮음, AQI 좋음/보통), 야외 활동하기 좋은 날씨라고 언급합니다.
    - [종합] 이 모든 조건을 종합하여 하나의 자연스러운 문단으로 'suggestion'을 만듭니다.
    """

    # (2) 사용자 프롬프트 템플릿: 실제 데이터와 작업 지시
    USER_PROMPT_TEMPLATE = """
    다음 JSON 날씨 데이터를 분석해 주세요.

    [입력 데이터]
    {input_data}

    [출력 스키마]
    {{
    "location_ko": "번역된 위치 ('위치' 필드 번역)",
    "summary_ko": "번역된 요약 ('요약' 필드 번역)",
    "alert_ko": "번역된 경보 ('경보' 필드 번역, 없으면 빈 문자열)",
    "suggestion": "시스템 프롬프트의 모든 규칙에 따라 생성된 종합 외출 제안 멘트"
    }}
    """

    # (3) 생성 설정: Temperature 및 JSON 모드 설정
    GENERATION_CONFIG = genai.GenerationConfig(
        temperature=0.2,  # 일관된 논리 + 약간 자연스러운 문장
        response_mime_type="application/json" # JSON 출력 모드 강제
    )

    print("Gemini API에 날씨 분석 요청 중...")
        # 1. 모델 초기화 (시스템 프롬프트, 생성 설정 적용)
    model = genai.GenerativeModel(
        model_name='gemini-2.5-flash',
        system_instruction=SYSTEM_PROMPT,
        generation_config=GENERATION_CONFIG
    )
    
    # 2. 사용자 프롬프트 완성
    # (json.dumps로 데이터를 문자열로 변환)
    user_prompt = USER_PROMPT_TEMPLATE.format(
        input_data=json.dumps(data, indent=2, ensure_ascii=False)
    )
        
    current_try = 0
    while current_try <= max_retries:
        try:
            # Send the text to the model.
            # The model already knows the rules from the SYSTEM_PROMPT.
            response = model.generate_content(user_prompt)
            
            # The model, in JSON mode, should return a clean JSON string.
            # We parse it into a Python dictionary.
            result_json = json.loads(response.text)
            return result_json

        except ResourceExhausted as e:
            # This exception is thrown on HTTP 429 (Rate Limit / Token Limit)
            current_try += 1
            if current_try > max_retries:
                print(f"[Error] Max retries reached for input: {user_prompt[:50]}...")
                print(f"Last error: {e}")
                raise
            
            print(f"[Warning] Rate limit exceeded. Waiting for {delay_seconds} seconds... (Attempt {current_try}/{max_retries})")
            time.sleep(delay_seconds)
        
        except json.JSONDecodeError as e:
            # The model returned invalid JSON
            print(f"[Error] Failed to decode JSON from model response.")
            print(f"       Input text was: {user_prompt[:100]}...")
            print(f"       Model response was: {response.text}")
            raise e
        
        except Exception as e:
            # Catch other potential errors (e.g., connection issues)
            print(f"[Error] An unexpected error occurred: {e}")
            raise e

    raise RuntimeError("Unknown error from AI process")


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

def send_to_telegram(message: str, chat_id: int = int(wmill.get_variable("u/admin/telegram_chat_id")), escaped: bool = False, token = wmill.get_resource("u/admin/telegram_token_resource")):
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

def send_long_message_to_telegram(message: str, chat_id: int = int(wmill.get_variable("u/admin/telegram_chat_id")), token = wmill.get_resource("u/admin/telegram_token_resource")):
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
