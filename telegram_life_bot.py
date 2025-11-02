#requirements:
#python-telegram-bot
#wmill
#requests
#telegramify_markdown

import wmill
# ConversationHandler, MessageHandler, filters 추가
from telegram.ext import (
    CommandHandler, 
    Application, 
    ConversationHandler, 
    MessageHandler, 
    filters
)
import requests
import telegramify_markdown
import traceback

subway_lines = {
    1001: "1호선",
    1002: "2호선",
    1003: "3호선",
    1004: "4호선",
    1005: "5호선",
    1006: "6호선",
    1007: "7호선",
    1008: "8호선",
    1009: "9호선",
    1061: "중앙선",
    1063: "경의중앙선",
    1065: "공항철도",
    1067: "경춘선",
    1075: "수인분당선",
    1077: "신분당선",
    1092: "우이신설선",
    1093: "서해선",
    1081: "경강선",
    1032: "GTX-A"
}

async def start_command(update, context):
    await update.message.reply_text("Hello! I am your bot.")

def is_integer(s):
    try:
        int(s)
        return True
    except ValueError:
        return False

train_emoji_map = {
    "급행": "⚡",  # Express - 빠른 속도
    "ITX": "🚆",   # Intercity Train eXpress - 도시 간 장거리 열차
    "일반": "🚈",   # Local - 모든 역에 정차하는 통근 열차
    "특급": "🚄"    # Limited/Special Express - 가장 빠른 고속 열차
}

def subway_arrival(station: str, line=None, updown=None):
    api_addr = f'http://swopenAPI.seoul.go.kr/api/subway/{wmill.get_variable("u/rapaellk/seoul_subway_api_key")}/json/realtimeStationArrival/0/99/{station}'
    response = requests.get(api_addr)
    if response.status_code != 200:
        raise RuntimeError("Cannot retrieve subway info")
    response_json=response.json()
    if response_json['errorMessage']['status'] != 200:
        raise RuntimeError("Cannot retrieve subway info")
    message = ""
    arrivals = response_json["realtimeArrivalList"]
    arrivals.sort(key=lambda x: int(x.get('subwayId')))
    if line:
        if is_integer(line):
            line = line+"호선"
        if line not in list(subway_lines.values()):
            raise RuntimeError("Wrong line name or number")
        arrivals = [x for x in arrivals if subway_lines[int(x['subwayId'])] == line]
    current_line = None
    for arrival in arrivals:
        l = subway_lines[int(arrival['subwayId'])]
        if l != current_line:
            current_line = l
            message+=f"\n*{current_line}*\n"
        ud = arrival['updnLine']
        if updown and updown != ud:
            continue
        train_status = arrival['btrainSttus']
        if train_status in train_emoji_map:
            train_status = f"**{train_emoji_map[train_status]} {train_status}**"
        message_tail = f"({arrival['arvlMsg3']})" if arrival['arvlMsg3'] not in arrival['arvlMsg2'] else ""
        message+=f"""* {ud} {arrival['trainLineNm']} {train_status}\n    * {arrival['arvlMsg2']} {message_tail}\n"""
    return message
# 대화 상태를 나타내는 상수 정의
GET_STATION = 0

async def _process_and_reply_subway_info(update, args):
    """지하철 정보를 처리하고 사용자에게 응답하는 헬퍼 함수"""
    msg = ""
    if not args:
        msg = "역 이름이 필요합니다."
    else:
        try:
            msg += f"**{args[0]}역 실시간 도착정보**\n"
            msg += subway_arrival(*args)
        except Exception as e:
            print(traceback.format_exc())
            msg = f"Error on running command: {e}"
    
    await update.message.reply_text(telegramify_markdown.markdownify(msg), parse_mode='MarkdownV2')

async def subway_command(update, context):
    """
    /subway 명령어의 진입점.
    인수가 있으면 바로 처리하고, 없으면 역 이름을 묻습니다.
    """
    args = context.args
    if args:
        # 인수가 있으면 즉시 처리하고 대화 종료
        await _process_and_reply_subway_info(update, args)
        return ConversationHandler.END
    else:
        # 인수가 없으면 사용자에게 질문하고 GET_STATION 상태로 전환
        await update.message.reply_text(
            "조회할 역 이름을 입력해 주세요. (예: 강남 2 상행)\n"
            "취소하려면 /cancel 을 입력하세요."
        )
        return GET_STATION

async def receive_station_name(update, context):
    """GET_STATION 상태에서 사용자의 입력을 받아 처리합니다."""
    # 사용자가 입력한 텍스트를 공백 기준으로 나눠 인수로 사용
    args = update.message.text.split()
    await _process_and_reply_subway_info(update, args)
    
    # 처리 후 대화 종료
    return ConversationHandler.END

async def cancel(update, context):
    """대화를 취소합니다."""
    await update.message.reply_text("조회를 취소했습니다.")
    return ConversationHandler.END

async def subway_arrival_command_guri(update, context):
    msg = f"**구리역 서울행 실시간 도착정보**\n"
    msg += subway_arrival("구리", "8", "하행")
    msg += subway_arrival("구리", "경의중앙선", "상행")
    await update.message.reply_text(telegramify_markdown.markdownify(msg), parse_mode='MarkdownV2')

async def subway_arrival_command_ebt(update, context):
    msg = f"**고속터미널역 구리행 실시간 도착정보**\n"
    msg += subway_arrival("고속터미널", "9", "상행")
    msg += subway_arrival("고속터미널", "7", "상행")
    msg += subway_arrival("고속터미널", "3", "상행")
    await update.message.reply_text(telegramify_markdown.markdownify(msg), parse_mode='MarkdownV2')

def main():
    telegram = wmill.get_resource("u/rapaellk/telegram_token_resource_2")
    if not telegram:
        return
    application = Application.builder().token(telegram['token']).build()
# --- /subway 명령어를 위한 ConversationHandler 생성 ---
    subway_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("subway", subway_command)],
        states={
            GET_STATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_station_name)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    application.add_handler(CommandHandler("start", start_command))
    
    # 기존 subway 핸들러 대신 ConversationHandler를 추가합니다.
    application.add_handler(subway_conv_handler) 
    
    application.add_handler(CommandHandler("guri2seoul", subway_arrival_command_guri))
    application.add_handler(CommandHandler("express2guri", subway_arrival_command_ebt))
    
    application.run_polling()
    # ... add handlers for other commands
    application.run_polling()
