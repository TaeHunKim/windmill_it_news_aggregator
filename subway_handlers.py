import wmill

import requests
from datetime import time
import telegramify_markdown
import traceback
from datetime import time
import pytz

import telegram # pin: python-telegram-bot[job-queue]
import telegram.ext # repin: python-telegram-bot[job-queue]
# [수정] InlineKeyboardButton, InlineKeyboardMarkup 추가
from telegram import Update, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ConversationHandler, 
    MessageHandler, filters, ContextTypes,
    CallbackQueryHandler # [수정] CallbackQueryHandler 추가
)
# [중요] 공통 모듈에서 cancel 함수 import
from f.telegram_life_bot.common_handlers import cancel

# --- 지하철 관련 상수 ---
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

train_emoji_map = {
    "급행": "⚡",  # Express - 빠른 속도
    "ITX": "🚆",   # Intercity Train eXpress - 도시 간 장거리 열차
    "일반": "🚈",   # Local - 모든 역에 정차하는 통근 열차
    "특급": "🚄"    # Limited/Special Express - 가장 빠른 고속 열차
}

GET_STATION = 0 # 지하철 대화 상태
MY_CHAT_ID = wmill.get_variable("u/rapaellk/telegram_chat_id")

# --- 지하철 헬퍼 함수 ---
def is_integer(s):
    try:
        int(s)
        return True
    except ValueError:
        return False

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

async def _process_and_reply_subway_info(update: Update, args, reply_markup=None):
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
    
    await update.message.reply_text(
        telegramify_markdown.markdownify(msg), 
        parse_mode='MarkdownV2',
        reply_markup=reply_markup
    )

# --- 지하철 명령어 핸들러 ---
async def subway_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/subway 명령어의 진입점."""
    args = context.args
    if args:
        await _process_and_reply_subway_info(update, args, reply_markup=None)
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "조회할 역 이름을 입력해 주세요. (예: 강남 2 상행)\n"
            "취소하려면 /cancel 을 입력하세요."
        )
        return GET_STATION

async def receive_station_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """GET_STATION 상태에서 사용자의 입력을 받아 처리합니다."""
    args = update.message.text.split()
    await _process_and_reply_subway_info(update, args, reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def subway_arrival_command_guri(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = f"**구리역 서울행 실시간 도착정보**\n"
    msg += subway_arrival("구리", "8", "하행")
    msg += subway_arrival("구리", "경의중앙선", "상행")
    await update.message.reply_text(telegramify_markdown.markdownify(msg), parse_mode='MarkdownV2')

async def subway_arrival_command_ebt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = f"**고속터미널역 구리행 실시간 도착정보**\n"
    msg += subway_arrival("고속터미널", "9", "상행")
    msg += subway_arrival("고속터미널", "7", "상행")
    msg += subway_arrival("고속터미널", "3", "상행")
    await update.message.reply_text(telegramify_markdown.markdownify(msg), parse_mode='MarkdownV2')

# --- [수정] 지하철 스케줄 콜백 ---
async def send_scheduled_guri_info(context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """[수정] 스케줄에 따라 구리역 도착 정보 수신 '여부'를 묻는 메시지를 전송합니다."""
    print("Running scheduled job: send_scheduled_guri_info (Asking)")
    
    # [추가] 인라인 키보드 버튼 정의
    keyboard = [
        [
            InlineKeyboardButton("✅ 네, 주세요", callback_data="guri_info_yes"),
            InlineKeyboardButton("❌ 아니요", callback_data="guri_info_no"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        # [수정] 정보를 보내는 대신, 버튼과 함께 질문을 보냅니다.
        await context.bot.send_message(
            chat_id=MY_CHAT_ID,
            text=telegramify_markdown.markdownify("**[자동]** 구리역 서울행 실시간 도착 정보를 받으시겠습니까?"),
            reply_markup=reply_markup,
            parse_mode='MarkdownV2'
        )
    except Exception as e:
        print(f"Error in scheduled job (sending question): {e}")
        print(traceback.format_exc())
        await context.bot.send_message(
            chat_id=MY_CHAT_ID,
            text=f"스케줄된 질문 전송 중 오류 발생: {e}"
        )

# --- [추가] 스케줄 버튼 클릭 핸들러 ---
async def handle_guri_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """'구리역 정보' 인라인 버튼 클릭을 처리합니다."""
    query = update.callback_query
    # 버튼 클릭에 즉시 응답하여 로딩 상태를 해제합니다.
    await query.answer()

    if query.data == "guri_info_yes":
        # "네"를 선택한 경우, 지하철 정보를 조회하고 메시지를 수정하여 정보를 표시합니다.
        print("User accepted scheduled guri info.")
        try:
            msg = f"**구리역 서울행 실시간 도착정보**\n"
            msg += subway_arrival("구리", "8", "하행")
            msg += subway_arrival("구리", "경의중앙선", "상행")
            
            await query.edit_message_text(
                text=telegramify_markdown.markdownify(msg),
                parse_mode='MarkdownV2'
            )
        except Exception as e:
            print(f"Error in scheduled job callback (getting info): {e}")
            print(traceback.format_exc())
            await query.edit_message_text(
                text=f"구리역 정보 조회 중 오류 발생: {e}"
            )
            
    elif query.data == "guri_info_no":
        # "아니요"를 선택한 경우, 메시지를 수정하여 취소했음을 알립니다.
        print("User declined scheduled guri info.")
        await query.edit_message_text(
            text=telegramify_markdown.markdownify("*구리역 정보* 요청을 취소했습니다."),
            parse_mode='MarkdownV2'
        )

# --- ⭐️ 외부 노출용 등록 함수 ⭐️ ---
def register(app: Application):
    """지하철 관련 핸들러와 스케줄을 Application에 등록합니다."""
    
    # 1. /subway 대화 핸들러 등록
    subway_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("subway", subway_command)],
        states={
            GET_STATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_station_name)]
        },
        fallbacks=[CommandHandler("cancel", cancel)] # 공통 cancel 함수 사용
    )
    app.add_handler(subway_conv_handler)
    
    # 2. 고정 명령어 핸들러 등록
    app.add_handler(CommandHandler("guri2seoul", subway_arrival_command_guri))
    app.add_handler(CommandHandler("express2guri", subway_arrival_command_ebt))

    # [추가] 3. 스케줄 관련 콜백 쿼리 핸들러 등록
    # "guri_info_"로 시작하는 모든 콜백 데이터를 이 핸들러가 처리합니다.
    app.add_handler(CallbackQueryHandler(handle_guri_info_callback, pattern="^guri_info_.*$"))

    # 4. 스케줄링 등록
    kst = pytz.timezone('Asia/Seoul')
    job_queue = app.job_queue
    
    job_daily_guri = job_queue.run_daily(
        send_scheduled_guri_info,
        time=time(hour=8, minute=0, second=0, tzinfo=kst),
        days=(0, 1, 2, 3, 4), 
        name="daily_guri_check"
    )
    print("Scheduled subway job (Mon-Fri 8:02 KST) successfully.")

#def main(station: str):
#    api_addr = f'http://swopenAPI.seoul.go.kr/api/subway/{wmill.get_variable("u/rapaellk/seoul_subway_api_key")}/json/realtimeStationArrival/0/99/{station}'
#    response = requests.get(api_addr)
#    print(response)