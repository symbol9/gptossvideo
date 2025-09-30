# web_app.py (финальная версия с ID диалога)

import asyncio
import os
import uuid  # <<< НОВОЕ: Импортируем библиотеку для генерации ID
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from aiogram import Bot

load_dotenv()

USE_LOCAL_MODEL = os.getenv("USE_LOCAL_MODEL", 'False').lower() in ('true', '1', 't')
if USE_LOCAL_MODEL:
    print("Режим: Локальная модель для веб-чата.")
    from local_agent_handler import get_local_model_response_stream
else:
    print("Режим: OpenAI (Agency Swarm) для веб-чата.")
    from agency.agency import agency

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# <<< ИЗМЕНЕНО: Хранилища для сессий
chat_histories = {}
session_data = {}  # Будем хранить здесь ID диалога для каждой сессии
SESSION_ID = "local_web_session"  # Для простоты у нас по-прежнему одна сессия

telegram_context = {}


@app.on_event("startup")
async def startup_event():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    manager_id = os.getenv("MANAGER_ID")
    if token and manager_id:
        telegram_context["bot_instance"] = Bot(token=token)
        telegram_context["manager_id"] = manager_id
        print(f"✅ Telegram Bot инициализирован. Уведомления будут отправляться менеджеру с ID: {manager_id}")
    else:
        print("⚠️ ВНИМАНИЕ: TELEGRAM_BOT_TOKEN или MANAGER_ID не найдены в .env")
        telegram_context["bot_instance"] = None
        telegram_context["manager_id"] = None


@app.on_event("shutdown")
async def shutdown_event():
    bot = telegram_context.get("bot_instance")
    if bot:
        await bot.session.close()
        print("Сессия Telegram Bot корректно закрыта.")


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Отдает главную HTML-страницу и генерирует ID диалога."""
    dialog_id = f"WEB-{str(uuid.uuid4())[:8].upper()}"
    chat_histories[SESSION_ID] = []
    session_data[SESSION_ID] = {"dialog_id": dialog_id}
    print(f"Новый диалог начат. ID: {dialog_id}")
    # Передаем ID в шаблон для отображения
    return templates.TemplateResponse("chat.html", {"request": request, "dialog_id": dialog_id})


@app.post("/chat/stream")
async def chat_stream(request: Request):
    """Основной эндпоинт для стриминга ответа от модели."""
    body = await request.json()
    user_message = body.get("message", "")

    if SESSION_ID not in chat_histories:
        chat_histories[SESSION_ID] = []
    chat_histories[SESSION_ID].append({"role": "user", "content": user_message})

    dialog_id = session_data.get(SESSION_ID, {}).get("dialog_id", "Не определен")

    context = {
        "bot_instance": telegram_context.get("bot_instance"),
        "manager_id": telegram_context.get("manager_id"),
        "user_info": {"dialog_id": dialog_id},  # Новая структура user_info
        "message_history": chat_histories[SESSION_ID]
    }

    # ... (остальная часть функции stream_generator остается без изменений) ...
    async def stream_generator():
        final_answer = ""
        streamer = None
        try:
            if USE_LOCAL_MODEL:
                streamer = get_local_model_response_stream(chat_histories[SESSION_ID], context)
            else:
                async def agency_wrapper():
                    agency_streamer = agency.get_response_stream(user_message, context_override=context)
                    async for event in agency_streamer:
                        if hasattr(event, "data") and hasattr(event.data,
                                                              "type") and event.data.type == "response.output_text.delta" and hasattr(
                                event.data, "delta"):
                            yield event.data.delta

                streamer = agency_wrapper()

            async for chunk in streamer:
                if chunk:
                    final_answer += chunk
                    yield chunk
                    await asyncio.sleep(0.01)

            if final_answer:
                chat_histories[SESSION_ID].append({"role": "assistant", "content": final_answer})
        except Exception as e:
            error_message = f"Критическая ошибка в стрим-генераторе: {e}"
            print(error_message)
            import traceback
            traceback.print_exc()
            yield error_message

    return StreamingResponse(stream_generator(), media_type="text/plain")