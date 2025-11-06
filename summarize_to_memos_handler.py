import wmill
import requests
import json
import trafilatura
import time
import re
from youtube_transcript_api import YouTubeTranscriptApi
import json_repair
import traceback
import telegram # pin: python-telegram-bot[job-queue]>=20.0
import telegram.ext # repin: python-telegram-bot[job-queue]>=20.0
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, ConversationHandler, 
    MessageHandler, filters, ContextTypes
)
import asyncio
from playwright.sync_api import sync_playwright

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted

# [중요] 공통 모듈에서 cancel 함수 import
try:
    from f.telegram_life_bot.common_handlers import cancel
except ImportError:
    # 로컬 테스트 등을 위한 fallback
    from common_handlers import cancel

genai.configure(api_key=wmill.get_variable("u/rapaellk/googleai_api_key_free"))

def process_text_with_gemini(text_input, max_retries=3, delay_seconds=60):
    # This system prompt contains all the logic you requested.
    # The model will follow these rules.
    SYSTEM_PROMPT = """
    You are a text processing expert. Your task is to process the given text and return a JSON object.

    Follow these steps precisely:
    1.  First, clean the input text by removing all XML, HTML, and Markdown syntax (e.g., tags like <p>, <div>, and markers like **, #, [text](link)). Get the raw, plain text content.
        1.1. Clean parts which are out of context (e.g., advertisement) as well
    2.  Summarize the text with details in structured markdown form and put it in 'summarization' field. The summarization should be written with same language with the input text.
        2.1. If necessary, you can use mermaid diagram syntax wrapped by ```mermaid\n...\n```. While doing so, use escape characters properly.
        2.2. Headings which can be used in the summary is `#### Heading 4` or lower (`##### Heading 5`, ...).
    3.  If the summarization is not written in Korean, translate it into Korean and put it into 'translated_in_korean'. If the summarization is already Korean, 'translated_in_korean' field can be omitted.
    4.  Write a proper title for the summarization in Korean and put it in 'title' field.
    5.  Based on the summary, decide 2~3 tags in Korean and put it in 'tags' field. Example: ["책", "유튜브", "개발"]
    5.  Return *only* the final JSON object, with the exact schema: {"title": "...", "summarization": "...", "translated_in_korean": "...", "tags":["tag1", "tag2", ...]}.
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
            result_json = json_repair.loads(response.text)
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

def get_content_from_link(url):
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36'
    }
    try:
        try:
            response = requests.get(
                url, 
                headers=HEADERS,  # 준비된 헤더 사용
                timeout=10        # 10초 이상 걸리면 중단
            )
            if response.status_code != 200:
                raise RuntimeError("Failed to get html")
            downloaded_html = response.text
            if downloaded_html is None:
                raise RuntimeError("Empty html")
        except Exception as e:
            print(f"Failed to get html: {e}. Try heavier way...")
            with sync_playwright() as p:
                try:
                    browser = p.chromium.launch()
                    page = browser.new_page()
                    page.goto(url)
                    downloaded_html = page.content()
                    browser.close()
                    if not downloaded_html:
                        raise RuntimeError("Failed to get html")
                except Exception:
                    print(f"Failed to get html: {e}. Give up")
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

def post_memo(content: str):
    memos_server_addr = "http://192.168.0.42:5230"
    headers = {
        'Authorization':'Bearer ' + wmill.get_variable("u/rapaellk/memos_token"),
        "Content-Type": "application/json"
    }

    json={
      "name": "",
      "state": "NORMAL",
      "content": content,
      "visibility": "PROTECTED",
      "pinned": False,
    }

    response = requests.post(
        f"{memos_server_addr}/api/v1/memos", headers=headers, json=json
    )
    return response.json()

def parseYoutubeURL(url:str)->str:
   data = re.findall(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
   if data:
       return data[0]
   return ""

def summarize_to_memos(url:str):
    content = ""
    if "youtube.com" in url.lower() or "youtu.be" in url.lower():
        video_id = parseYoutubeURL(url)
        if not video_id:
            return None
        ytt_api = YouTubeTranscriptApi()
        transcript_list = ytt_api.list(video_id)
        try:
            transcript = transcript_list.find_manually_created_transcript(['ko', 'en'])
        except Exception:
            try:
                transcript = transcript_list.find_generated_transcript(['ko', 'en'])
            except Exception:
                return None
        fetched_transcript = transcript.fetch()
        content = "\n".join([x.text for x in fetched_transcript.snippets])
        print(content)
    else:
        content = get_content_from_link(url)
    if not content:
        return None
    try:
        ai_processed_content = process_text_with_gemini(content)
        print(ai_processed_content)
    except Exception:
        return None

    # {"title": "...", "summarization": "...", "translated_in_korean": "...", "tags":["tag1", "tag2", ...]}.
    title = ai_processed_content.get('title', "")
    summarization = ai_processed_content.get('summarization', "")
    translated_in_korean = ai_processed_content.get('translated_in_korean', "")
    tags = " ".join([f"#{x.replace(' ', '_')}" for x in ai_processed_content.get('tags', [])])
    final_content = f"### {title} {tags}\n{summarization}\n" + (f"---\n{translated_in_korean}" if translated_in_korean else "") + f"[원본 링크]({url})"
    print(final_content)

    response = post_memo(final_content)
    print(response)
    if hasattr(response, "code"):
        return None
    return True # well done

# 대화 상태 정의
GET_URL = 0

async def _process_summary(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    """
    URL 요약 로직을 실제로 실행하고 사용자에게 응답하는 헬퍼 함수
    """
    await update.message.reply_text(f"요청을 처리 중입니다: {url}\n(내용에 따라 시간이 걸릴 수 있습니다...)")
    
    try:
        # --- [중요] ---
        # 만약 summarize_to_memos 함수가 오래 걸리는 작업(LLM API 호출 등)이라면
        # 봇 전체가 멈출 수 있습니다.
        # 이 경우, 아래와 같이 별도 스레드에서 실행해야 합니다.
        success = await asyncio.to_thread(summarize_to_memos, url)
        
        # (만약 summarize_to_memos가 이미 async def로 정의된 비동기 함수라면)
        # success = await summarize_to_memos(url) 

        if success is True:
            await update.message.reply_text("✅ 완료되었습니다.")
        else: # None 또는 False 반환 시
            await update.message.reply_text("❌ 실패하였습니다.")

    except Exception as e:
        print(traceback.format_exc()) # 오류 로그
        await update.message.reply_text(f"처리 중 오류가 발생했습니다: {e}")

async def summarize_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """/summarize_to_memos 명령어의 진입점"""
    args = context.args
    
    if args:
        # 1. 인자(/summarize_to_memos <url>)가 있는 경우
        url = args[0]
        await _process_summary(update, context, url)
        return ConversationHandler.END # 대화 즉시 종료
    else:
        # 2. 인자가 없는 경우, URL을 물어봄
        await update.message.reply_text(
            "요약할 웹 페이지 또는 유튜브 URL을 입력해주세요.\n"
            "취소하려면 /cancel 을 입력하세요."
        )
        return GET_URL # GET_URL 상태로 전환

async def receive_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """GET_URL 상태에서 사용자의 URL 텍스트 입력을 받아 처리"""
    url = update.message.text
    
    # (간단한 URL 유효성 검사 - 필요시 추가)
    if not url.startswith("http"):
        await update.message.reply_text(
            "잘못된 형식입니다. http:// 또는 https:// 로 시작하는 주소를 입력해주세요.\n"
            "취소하려면 /cancel 을 입력하세요."
        )
        return GET_URL # 상태 유지
    
    await _process_summary(update, context, url)
    return ConversationHandler.END # 대화 종료

# --- ⭐️ (3) 외부 노출용 등록 함수 ⭐️ ---
def register(app: Application):
    """요약 대화 핸들러를 Application에 등록합니다."""
    
    summary_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("summarize_to_memos", summarize_command)],
        states={
            GET_URL: [
                # 텍스트 메시지(명령어 제외)를 받아서 receive_url 함수로 넘김
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_url)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)] # 공통 cancel 함수 사용
    )
    
    app.add_handler(summary_conv_handler)
    print("Summarize handler registered successfully.")
