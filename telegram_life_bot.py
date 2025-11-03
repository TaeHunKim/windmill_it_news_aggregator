import wmill
import telegram.ext # pin: python-telegram-bot[job-queue]
from telegram.ext import CommandHandler, Application, ConversationHandler, MessageHandler, filters, JobQueue # <<< JobQueue 추가
import requests
import telegramify_markdown
import traceback
from datetime import time # <<< [추가]
import pytz               # <<< [추가]

from u.admin.get_weather import get_home_weather, get_office_weather, get_parent_home_weather, get_weather_message_from_location_name

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
    api_addr = f'http://swopenAPI.seoul.go.kr/api/subway/{wmill.get_variable("u/admin/seoul_subway_api_key")}/json/realtimeStationArrival/0/99/{station}'
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
GET_LOCATION = 1  # <<< [수정] 날씨 위치 입력을 위한 상태 추가

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

# --- [추가] 스케줄된 작업을 위한 chat_id (본인의 ID로 변경하세요) ---
# 예: 123456789
MY_CHAT_ID = wmill.get_variable("u/admin/telegram_chat_id") # Windmill 변수로 관리하는 것을 추천

# --- [신규] 스케줄러가 호출할 별도 함수 ---
async def send_scheduled_guri_info(context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """
    스케줄에 따라 구리역 도착 정보를 MY_CHAT_ID로 전송합니다.
    """
    print("Running scheduled job: send_scheduled_guri_info")
    try:
        msg = f"**[자동] 구리역 서울행 실시간 도착정보**\n"
        msg += subway_arrival("구리", "8", "하행")
        msg += subway_arrival("구리", "경의중앙선", "상행")
        
        # context.bot을 사용하여 메시지 전송
        await context.bot.send_message(
            chat_id=MY_CHAT_ID,
            text=telegramify_markdown.markdownify(msg),
            parse_mode='MarkdownV2'
        )
    except Exception as e:
        print(f"Error in scheduled job: {e}")
        print(traceback.format_exc())
        # 오류 발생 시에도 알림을 받을 수 있습니다.
        await context.bot.send_message(
            chat_id=MY_CHAT_ID,
            text=f"스케줄된 구리역 정보 조회 중 오류 발생: {e}"
        )

async def weather_home(update, context):
    msg = get_home_weather(with_send_to_telegram=False)
    await update.message.reply_text(msg, parse_mode='MarkdownV2')

async def weather_office(update, context):
    msg = get_office_weather(with_send_to_telegram=False)
    await update.message.reply_text(msg, parse_mode='MarkdownV2')

async def weather_parent_home(update, context):
    msg = get_parent_home_weather(with_send_to_telegram=False)
    await update.message.reply_text(msg, parse_mode='MarkdownV2')

# --- [신규] 날씨 정보 처리 헬퍼 함수 ---
async def _process_and_reply_weather_info(update, args):
    """날씨 정보를 처리하고 사용자에게 응답하는 헬퍼 함수"""
    msg = ""
    if not args:
        msg = "지역 이름이 필요합니다."
    else:
        try:
            # "서울 중구"와 같이 공백이 포함된 지역명을 처리하기 위해 join 사용
            location_name = " ".join(args)
            msg = get_weather_message_from_location_name(location_name)
        except Exception as e:
            print(traceback.format_exc())
            msg = f"Error on running command: {e}"
    
    await update.message.reply_text(msg, parse_mode='MarkdownV2')

# --- [수정] weather_location을 ConversationHandler의 진입점으로 수정 ---
async def weather_location(update, context):
    """
    /weather_location 명령어의 진입점.
    인수가 있으면 바로 처리하고, 없으면 지역 이름을 묻습니다.
    """
    args = context.args
    if args:
        # 인수가 있으면 즉시 처리하고 대화 종료
        await _process_and_reply_weather_info(update, args)
        return ConversationHandler.END
    else:
        # 인수가 없으면 사용자에게 질문하고 GET_LOCATION 상태로 전환
        await update.message.reply_text(
            "조회할 지역 이름을 입력해 주세요. (예: 서울)\n"
            "취소하려면 /cancel 을 입력하세요."
        )
        return GET_LOCATION

# --- [신규] GET_LOCATION 상태에서 사용자 입력을 처리하는 함수 ---
async def receive_location_name(update, context):
    """GET_LOCATION 상태에서 사용자의 입력을 받아 처리합니다."""
    # 사용자가 입력한 텍스트를 공백 기준으로 나눠 인수로 사용
    args = update.message.text.split()
    await _process_and_reply_weather_info(update, args)
    
    # 처리 후 대화 종료
    return ConversationHandler.END

def main():
    telegram = wmill.get_resource("u/admin/telegram_token_resource_2")
    if not telegram:
        return
    job_queue = JobQueue()
    application = Application.builder().token(telegram['token']).job_queue(job_queue).build()
    # --- /subway 명령어를 위한 ConversationHandler 생성 ---
    subway_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("subway", subway_command)],
        states={
            GET_STATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_station_name)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    # --- [신규] /weather_location 명령어를 위한 ConversationHandler 생성 ---
    weather_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("weather_location", weather_location)],
        states={
            GET_LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_location_name)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]  # 동일한 cancel 핸들러 공유
    )

    application.add_handler(CommandHandler("start", start_command))
    
    # 기존 subway 핸들러 대신 ConversationHandler를 추가합니다.
    application.add_handler(subway_conv_handler) 
    
    application.add_handler(CommandHandler("guri2seoul", subway_arrival_command_guri))
    application.add_handler(CommandHandler("express2guri", subway_arrival_command_ebt))

    application.add_handler(CommandHandler("weather_home", weather_home))
    application.add_handler(CommandHandler("weather_office", weather_office))
    application.add_handler(CommandHandler("weather_parent_home", weather_parent_home))
    # --- [수정] 기존 weather_location 핸들러 대신 ConversationHandler를 추가 ---
    application.add_handler(weather_conv_handler)
    
    # 시간대 설정 (한국 시간 = KST)
    kst = pytz.timezone('Asia/Seoul')

    job_daily_guri = job_queue.run_daily(
        send_scheduled_guri_info,
        time=time(hour=8, minute=2, second=0, tzinfo=kst),
        days=(0, 1, 2, 3, 4), # 0=월요일, 1=화요일, ... 4=금요일
        name="daily_guri_check" # Job 이름 (선택 사항)
    )
    
    print("Scheduled daily job (Mon-Fri 8:02 KST) successfully.")
    
    application.run_polling()