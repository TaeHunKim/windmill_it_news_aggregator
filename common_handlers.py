import telegram # pin: python-telegram-bot[job-queue]
import telegram.ext # repin: python-telegram-bot[job-queue]
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes, Application, CommandHandler, ConversationHandler

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start 명령어 핸들러"""
    await update.message.reply_text("Hello! I am your bot.")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """대화 취소 핸들러"""
    # user_data에 저장된 임시 선택지 정리
    if 'morning_weather_choice' in context.user_data:
        del context.user_data['morning_weather_choice']
        
    await update.message.reply_text(
        "조회를 취소했습니다.",
        reply_markup=ReplyKeyboardRemove()
    )
    # ConversationHandler.END를 반환하는 것은 
    # 이 함수를 호출한 ConversationHandler가 담당합니다.
    # (여기서는 상태만 정리하고 메시지만 보냅니다)
    # *수정: ConversationHandler의 fallback이 직접 이 함수를
    #        호출할 것이므로 END를 반환해야 합니다.
    return ConversationHandler.END


def register(app: Application):
    """공통 핸들러를 Application에 등록합니다."""
    app.add_handler(CommandHandler("start", start_command))
    # /cancel은 ConversationHandler의 fallbacks에서 주로 사용되지만,
    # 최상위 레벨에서도 등록해두면 좋습니다.
    app.add_handler(CommandHandler("cancel", cancel))