import wmill
import telegram # pin: python-telegram-bot[job-queue]>=20.0
import telegram.ext # repin: python-telegram-bot[job-queue]>=20.0
from telegram.ext import Application, JobQueue

import requests                 # subway_handlers.py 가 사용
import telegramify_markdown     # subway_handlers.py 가 사용
import pytz                     # subway_handlers.py 와 weather_handlers.py 가 사용
import holidayskr               # used by get_weather
import geopy                    # used by get_weather
import google.generativeai as genai # used by get_weather
from google.api_core.exceptions import ResourceExhausted # used by get_weather
import trafilatura # used by summarize_to_memos_handler
import youtube_transcript_api # used by summarize_to_memos_handler
import json_repair # used by summarize_to_memos_handler
import asyncio # used by summarize_to_memos_handler
from playwright.sync_api import sync_playwright # used by summarize_to_memos_handler

from f.telegram_life_bot import common_handlers
from f.telegram_life_bot import subway_handlers
from f.telegram_life_bot import weather_handlers
from f.telegram_life_bot import summarize_to_memos_handler # [신규] 임포트 추가

def main():
    telegram_token = wmill.get_resource("u/rapaellk/telegram_token_resource_2")
    if not telegram_token:
        print("Telegram token not found.")
        return

    # 1. Application 빌드
    job_queue = JobQueue()
    application = (
        Application.builder()
        .token(telegram_token['token'])
        .job_queue(job_queue)
        .build()
    )

    # 2. 각 기능 모듈의 핸들러 등록
    common_handlers.register(application)
    subway_handlers.register(application)
    weather_handlers.register(application)
    summarize_to_memos_handler.register(application) # [신규] 등록 호출 추가
    
    # 3. 봇 시작
    print("Bot application running polling...")
    application.run_polling()