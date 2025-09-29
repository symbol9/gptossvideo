# web_app.py (финальная версия с интеграцией Telegram)

import asyncio
import os
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

# <<< НОВОЕ: Импортируем Bot из aiogram
from aiogram import Bot

# Загружаем переменные окружения, чтобы прочитать USE_LOCAL_MODEL и TELEGRAM_BOT_TOKEN
load_dotenv()

# Условные импорты, как и раньше
USE_LOCAL_MODEL = os.getenv("USE_LOCAL_MODEL", 'False').lower() in ('true', '1', 't')

if USE_LOCAL_MODEL:
    print("Режим: Локальная модель для веб-чата.")
    from local_agent_handler import get_local_model_response_stream
else:
    print("Режим: OpenAI (Agency Swarm) для веб-чата.")
    from agency.agency import agency

app = FastAPI()
templates = Jinja2Templates(directory="templates")

chat_histories = {}
SESSION_ID = "local_web_session"

# <<< НОВОЕ: Глобальное хранилище для экземпляра бота и ID менеджера
telegram_context = {}


# <<< НОВОЕ: Функция, которая выполняется при старте приложения
@app.on_event("startup")
async def startup_event():
    """Инициализирует Telegram бота при запуске FastAPI."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    manager_id = os.getenv("MANAGER_ID")

    if token and manager_id:
        # Создаем один экземпляр бота на все время жизни приложения
        telegram_context["bot_instance"] = Bot(token=token)
        telegram_context["manager_id"] = manager_id
        print(f"✅ Telegram Bot инициализирован. Уведомления будут отправляться менеджеру с ID: {manager_id}")
    else:
        print("⚠️ ВНИМАНИЕ: TELEGRAM_BOT_TOKEN или MANAGER_ID не найдены в .env")
        print("Функция перевода на менеджера будет работать в консольном режиме.")
        telegram_context["bot_instance"] = None
        telegram_context["manager_id"] = None


# <<< НОВОЕ: Функция, которая выполняется при остановке приложения
@app.on_event("shutdown")
async def shutdown_event():
    """Корректно закрывает сессию бота при остановке FastAPI."""
    bot = telegram_context.get("bot_instance")
    if bot:
        await bot.session.close()
        print("Сессия Telegram Bot корректно закрыта.")


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Отдает главную HTML-страницу с чатом."""
    chat_histories[SESSION_ID] = []
    return templates.TemplateResponse("chat.html", {"request": request})


@app.post("/chat/stream")
async def chat_stream(request: Request):
    """
    Основной эндпоинт для стриминга ответа от модели.
    """
    body = await request.json()
    user_message = body.get("message", "")

    if not user_message:
        return {"error": "Empty message"}

    if SESSION_ID not in chat_histories:
        chat_histories[SESSION_ID] = []

    chat_histories[SESSION_ID].append({"role": "user", "content": user_message})

    # <<< ИЗМЕНЕНО: Контекст теперь берет реального бота и ID из хранилища
    context = {
        "bot_instance": telegram_context.get("bot_instance"),
        "manager_id": telegram_context.get("manager_id"),
        "user_info": {"id": "web_user", "full_name": "Local User", "username": "local_user"},
        "message_history": chat_histories[SESSION_ID]
    }

    async def stream_generator():
        """
        Генератор, который получает чанки ответа от модели и отдает их.
        """
        final_answer = ""
        streamer = None

        try:
            if USE_LOCAL_MODEL:
                streamer = get_local_model_response_stream(chat_histories[SESSION_ID], context)
            else:
                # В этом блоке мы создаем обертку для стрима от agency
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