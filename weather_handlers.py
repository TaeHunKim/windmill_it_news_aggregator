import wmill
import traceback
from datetime import time
import pytz

import telegram # pin: python-telegram-bot[job-queue]
import telegram.ext # repin: python-telegram-bot[job-queue]
from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram import InlineKeyboardButton, InlineKeyboardMarkup 
from telegram.ext import (
    Application, CommandHandler, ConversationHandler, 
    MessageHandler, filters, ContextTypes, CallbackQueryHandler
)

# [중요] 공통 모듈에서 cancel 함수 import
from f.telegram_life_bot.common_handlers import cancel

# [중요] 기존 날씨 스크립트 import
from f.telegram_life_bot.get_weather import (
    get_home_weather, get_office_weather, get_parent_home_weather, 
    get_weather_message_from_location_name, get_weather_message
)

# --- 날씨 관련 상수 ---
CB_MORNING_DYNAMIC_CURRENT = "morning_dynamic_current"
CB_MORNING_DYNAMIC_ALL = "morning_dynamic_all"
GET_LOCATION = 1
AWAIT_MORNING_LOCATION = 2
MY_CHAT_ID = wmill.get_variable("u/rapaellk/telegram_chat_id")

# --- 날씨 헬퍼 함수 ---
async def _process_and_reply_weather_info(update: Update, args, reply_markup=None):
    """날씨 정보를 처리하고 사용자에게 응답하는 헬퍼 함수"""
    msg = ""
    if not args:
        msg = "지역 이름이 필요합니다."
    else:
        try:
            location_name = " ".join(args)
            msg = get_weather_message_from_location_name(location_name)
        except Exception as e:
            print(traceback.format_exc())
            msg = f"Error on running command: {e}"
    
    await update.message.reply_text(
        msg, 
        parse_mode='MarkdownV2',
        reply_markup=reply_markup
    )

# --- 날씨 명령어 핸들러 ---
async def weather_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = get_home_weather()
    await update.message.reply_text(msg, parse_mode='MarkdownV2')

async def weather_office(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = get_office_weather()
    await update.message.reply_text(msg, parse_mode='MarkdownV2')

async def weather_parent_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = get_parent_home_weather()
    await update.message.reply_text(msg, parse_mode='MarkdownV2')


# --- 날씨 대화 핸들러 (1) - /weather_location ---
async def weather_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/weather_location 명령어의 진입점."""
    args = context.args
    if args:
        await _process_and_reply_weather_info(update, args, reply_markup=None)
        return ConversationHandler.END
    else:
        location_button = KeyboardButton(text="📍 현재 위치로 날씨 보기", request_location=True)
        custom_keyboard = ReplyKeyboardMarkup(
            [[location_button]], 
            one_time_keyboard=True, 
            resize_keyboard=True,
            input_field_placeholder="원하는 지역 이름을 입력하세요..."
        )
        await update.message.reply_text(
            "날씨를 조회할 지역 이름을 입력하시거나, '현재 위치로 날씨 보기' 버튼을 눌러주세요.\n"
            "취소하려면 /cancel 을 입력하세요.",
            reply_markup=custom_keyboard
        )
        return GET_LOCATION

async def receive_location_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """GET_LOCATION 상태에서 사용자의 '텍스트' 입력을 받아 처리합니다."""
    args = update.message.text.split()
    await _process_and_reply_weather_info(update, args, reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def receive_location_coordinates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """GET_LOCATION 상태에서 사용자의 '위치' 입력을 받아 처리합니다."""
    try:
        user_location = update.message.location
        latitude = user_location.latitude
        longitude = user_location.longitude
        msg = get_weather_message(latitude, longitude)
        await update.message.reply_text(
            msg,
            parse_mode='MarkdownV2',
            reply_markup=ReplyKeyboardRemove()
        )
    except Exception as e:
        print(traceback.format_exc())
        msg = f"Error on processing location: {e}"
        await update.message.reply_text(msg, reply_markup=ReplyKeyboardRemove())
    
    return ConversationHandler.END

# --- 날씨 대화 핸들러 (2) - 아침 날씨 ---
async def start_morning_weather_conv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    오전 5시 30분 메시지의 Inline 버튼 클릭을 처리합니다.
    사용자의 선택을 저장하고, 위치 전송을 요청합니다.
    """
    query = update.callback_query
    await query.answer()
    
    # 사용자가 어떤 버튼을 눌렀는지 user_data에 저장
    # (이 데이터는 이 대화 핸들러 세션 동안 유지됨)
    context.user_data['morning_weather_choice'] = query.data 
    
    # 1회용 위치 전송 버튼(ReplyKeyboardMarkup) 생성
    location_button = KeyboardButton(text="📍 현재 위치 전송하기", request_location=True)
    custom_keyboard = ReplyKeyboardMarkup(
        [[location_button]], 
        one_time_keyboard=True, 
        resize_keyboard=True
    )
    
    # 1. 기존 인라인 버튼 메시지를 수정하여 버튼을 제거
    await query.edit_message_text(
        text="✅ 선택을 확인했습니다.\n이제 '현재 위치 전송하기' 버튼을 눌러 위치를 보내주세요.",
        reply_markup=None # 인라인 버튼 제거
    )
    
    # 2. 별도의 새 메시지로 ReplyKeyboard(위치 전송 버튼)를 전송
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="아래 버튼을 눌러주세요 ⬇️",
        reply_markup=custom_keyboard
    )
    
    # 다음 상태(위치 수신 대기)로 전환
    return AWAIT_MORNING_LOCATION

# --- [신규] 아침 날씨 대화 (2/2): 위치 수신 시 처리 ---
async def receive_morning_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    AWAIT_MORNING_LOCATION 상태에서 위치 정보를 받아 처리합니다.
    """
    user_location = update.message.location
    lat = user_location.latitude
    lon = user_location.longitude
    
    # user_data에서 사용자의 원래 선택을 가져옴
    choice = context.user_data.get('morning_weather_choice')
    
    try:
        # 1. '현재 위치' 날씨는 항상 전송
        print(f"Calling get_weather_message({lat}, {lon})")
        msg_current = get_weather_message(lat, lon)
        # 키보드를 제거하며 첫 번째 메시지 전송
        await update.message.reply_text(msg_current, parse_mode='MarkdownV2', reply_markup=ReplyKeyboardRemove())

        # 2. '회사' 날씨 추가 전송
        if choice == CB_MORNING_DYNAMIC_ALL:
            print("Calling get_office_weather()")
            msg_office = get_office_weather()
            await update.message.reply_text(msg_office, parse_mode='MarkdownV2')
        
    except Exception as e:
         print(traceback.format_exc())
         await update.message.reply_text(f"날씨 조회 중 오류 발생: {e}", reply_markup=ReplyKeyboardRemove())
    finally:
        # 대화가 종료되므로 user_data 정리
        if 'morning_weather_choice' in context.user_data:
            del context.user_data['morning_weather_choice']
    
    # 대화 종료
    return ConversationHandler.END


# --- 날씨 스케줄 콜백 ---
async def send_daily_weather_options(context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """
    스케줄에 따라 아침 날씨 선택 버튼을 전송합니다.
    """
    print("Running scheduled job: send_daily_weather_options")
    try:
        # 1. Inline Keyboard 버튼 2개 생성
        keyboard = [
            [
                InlineKeyboardButton(
                    "📍 현재 위치 날씨 받기", 
                    callback_data=CB_MORNING_DYNAMIC_CURRENT
                ),
            ],
            [
                InlineKeyboardButton(
                    "📍 현재 위치 + 🏢 회사 날씨 받기", 
                    callback_data=CB_MORNING_DYNAMIC_ALL
                ),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # 2. MY_CHAT_ID로 메시지 전송
        await context.bot.send_message(
            chat_id=MY_CHAT_ID,
            text="좋은 아침입니다! ☀️\n조회할 날씨 종류를 선택하세요:",
            reply_markup=reply_markup
        )
    except Exception as e:
        print(f"Error in scheduled job (send_daily_weather_options): {e}")
        print(traceback.format_exc())
        await context.bot.send_message(
            chat_id=MY_CHAT_ID,
            text=f"스케줄된 아침 날씨 옵션 전송 중 오류 발생: {e}"
        )

# --- ⭐️ 외부 노출용 등록 함수 ⭐️ ---
def register(app: Application):
    """날씨 관련 핸들러와 스케줄을 Application에 등록합니다."""

    # 1. /weather_location 대화 핸들러
    weather_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("weather_location", weather_location)],
        states={
            GET_LOCATION: [
                MessageHandler(filters.LOCATION, receive_location_coordinates),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_location_name)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # 2. 아침 날씨 대화 핸들러
    morning_weather_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_morning_weather_conv, pattern=f"^{CB_MORNING_DYNAMIC_CURRENT}$|^{CB_MORNING_DYNAMIC_ALL}$")
        ],
        states={
            AWAIT_MORNING_LOCATION: [
                MessageHandler(filters.LOCATION, receive_morning_location)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        conversation_timeout=600 
    )

    app.add_handler(weather_conv_handler)
    app.add_handler(morning_weather_conv)

    # 3. 고정 명령어 핸들러
    app.add_handler(CommandHandler("weather_home", weather_home))
    app.add_handler(CommandHandler("weather_office", weather_office))
    app.add_handler(CommandHandler("weather_parent_home", weather_parent_home))

    # 4. 스케줄링 등록
    kst = pytz.timezone('Asia/Seoul')
    job_queue = app.job_queue
    
    job_daily_weather = job_queue.run_daily(
        send_daily_weather_options,
        time=time(hour=5, minute=30, second=0, tzinfo=kst),
        name="daily_morning_weather"
    )
    print("Scheduled weather job (Every day 5:30 KST) successfully.")