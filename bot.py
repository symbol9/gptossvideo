# bot.py (финальная, упрощенная версия без кнопок)

import os
import asyncio
import logging
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters.command import Command
from aiogram.enums import ChatAction
import time

# --- Условные импорты и конфигурация (без изменений) ---
logging.basicConfig(level=logging.INFO)
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MANAGER_ID = os.getenv("MANAGER_ID")
USE_LOCAL_MODEL = os.getenv("USE_LOCAL_MODEL", 'False').lower() in ('true', '1', 't')
if USE_LOCAL_MODEL:
    print("Режим: Локальная модель. Импортирую локальные компоненты...")
    from local_agent_handler import get_local_model_response_stream
    import local_tools
else:
    print("Режим: OpenAI. Импортирую Agency Swarm...")
    from agency.agency import agency
# ---------------------------------------------------------

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
user_histories = {}


async def stream_and_edit_message(streamer, message: types.Message):
    full_response = ""
    sent_message = await message.answer("⏳")
    last_edit_time = time.time()
    async for chunk in streamer:
        full_response += chunk
        if time.time() - last_edit_time > 1.0:
            try:
                await bot.edit_message_text(text=full_response + " ▌", chat_id=message.chat.id,
                                            message_id=sent_message.message_id, parse_mode='Markdown')
                last_edit_time = time.time()
            except Exception:
                pass
    try:
        await bot.edit_message_text(text=full_response, chat_id=message.chat.id, message_id=sent_message.message_id,
                                    parse_mode='Markdown')
    except Exception:
        # Если финальная версия с ошибкой, отправляем как простой текст
        await bot.edit_message_text(text=full_response, chat_id=message.chat.id, message_id=sent_message.message_id)
    return full_response


async def process_and_stream_response(message: types.Message):
    chat_id = message.chat.id
    context = {
        "bot_instance": bot, "manager_id": MANAGER_ID,
        "user_info": {"id": message.from_user.id, "full_name": message.from_user.full_name,
                      "username": message.from_user.username},
        "message_history": user_histories.get(chat_id, [])
    }
    final_answer = ""
    try:
        if USE_LOCAL_MODEL:
            streamer = get_local_model_response_stream(user_histories[chat_id], context)
            final_answer = await stream_and_edit_message(streamer, message)
        else:
            streamer = agency.get_response_stream(message.text, context_override=context)

            async def agency_chunk_extractor(s):
                async for event in s:
                    if hasattr(event, "data"):
                        data = event.data
                        if hasattr(data, "type") and data.type == "response.output_text.delta":
                            if hasattr(data, "delta"):
                                text_chunk = data.delta
                                if text_chunk:
                                    yield text_chunk

            final_answer = await stream_and_edit_message(agency_chunk_extractor(streamer), message)
        if final_answer:
            user_histories[chat_id].append({"role": "assistant", "content": final_answer})
    except Exception as e:
        logging.error(f"Критическая ошибка в фоновой задаче: {e}", exc_info=True)
        await message.answer("К сожалению, произошла внутренняя ошибка при генерации ответа.")


# --- УПРОЩЕННЫЙ ОБРАБОТЧИК /start ---
@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    user_histories[message.chat.id] = []
    await message.reply(
        "Здравствуйте! Я — ваш персональный ассистент 'ТехноМир'. Чем могу помочь?\n"
        "Вы можете спросить меня о статусе заказа (например, 'что с заказом 2?') или задать общие вопросы."
    )


# --- ГЛАВНЫЙ И ЕДИНСТВЕННЫЙ ОБРАБОТЧИК СООБЩЕНИЙ ---
@dp.message()
async def handle_message(message: types.Message):
    chat_id = message.chat.id
    if chat_id not in user_histories:
        user_histories[chat_id] = []
    user_histories[chat_id].append({"role": "user", "content": message.text})

    # Просто запускаем нашу фоновую AI-логику на любое сообщение
    asyncio.create_task(process_and_stream_response(message))


if __name__ == '__main__':
    asyncio.run(dp.start_polling(bot))