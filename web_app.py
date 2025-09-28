# web_app.py (исправленная и финальная версия)

import asyncio
import os
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

# --- НОВЫЕ ИМПОРТЫ И НАСТРОЙКА ---
# Загружаем переменные окружения, чтобы прочитать USE_LOCAL_MODEL
load_dotenv()

# Условные импорты, как в bot.py
USE_LOCAL_MODEL = os.getenv("USE_LOCAL_MODEL", 'False').lower() in ('true', '1', 't')

if USE_LOCAL_MODEL:
    print("Режим: Локальная модель для веб-чата.")
    from local_agent_handler import get_local_model_response_stream
else:
    print("Режим: OpenAI (Agency Swarm) для веб-чата.")
    from agency.agency import agency
# --- КОНЕЦ НОВЫХ ИМПОРТОВ ---


app = FastAPI()
templates = Jinja2Templates(directory="templates")

chat_histories = {}
SESSION_ID = "local_web_session"


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Отдает главную HTML-страницу с чатом."""
    chat_histories[SESSION_ID] = []
    return templates.TemplateResponse("chat.html", {"request": request})


@app.post("/chat/stream")
async def chat_stream(request: Request):
    """
    Основной эндпоинт для стриминга ответа от модели.
    Теперь поддерживает переключение между локальной моделью и Agency Swarm.
    """
    body = await request.json()
    user_message = body.get("message", "")

    if not user_message:
        return {"error": "Empty message"}

    if SESSION_ID not in chat_histories:
        chat_histories[SESSION_ID] = []

    chat_histories[SESSION_ID].append({"role": "user", "content": user_message})

    # Контекст теперь универсален для обоих режимов
    context = {
        "bot_instance": None, "manager_id": None,  # В веб-режиме эти поля не нужны
        "user_info": {"id": "web_user", "full_name": "Local User", "username": "local_user"},
        "message_history": chat_histories[SESSION_ID]
    }

    async def stream_generator():
        """
        Генератор, который получает чанки ответа от модели и отдает их.
        Также сохраняет финальный ответ в историю.
        """
        final_answer = ""
        streamer = None

        try:
            # --- НОВАЯ ЛОГИКА ПЕРЕКЛЮЧЕНИЯ ---
            if USE_LOCAL_MODEL:
                streamer = get_local_model_response_stream(chat_histories[SESSION_ID], context)
                async for chunk in streamer:
                    final_answer += chunk
                    yield chunk
                    await asyncio.sleep(0.01)
            else:
                # Логика для Agency Swarm, адаптированная из bot.py
                agency_streamer = agency.get_response_stream(user_message, context_override=context)

                async for event in agency_streamer:
                    if hasattr(event, "data"):
                        data = event.data
                        if hasattr(data, "type") and data.type == "response.output_text.delta":
                            if hasattr(data, "delta"):
                                chunk = data.delta
                                if chunk:
                                    final_answer += chunk
                                    yield chunk
                                    await asyncio.sleep(0.01)
            # --- КОНЕЦ НОВОЙ ЛОГИКИ ---

            # Сохраняем полный ответ ассистента в историю
            if final_answer:
                chat_histories[SESSION_ID].append({"role": "assistant", "content": final_answer})

        except Exception as e:
            # Теперь мы будем видеть более детальную ошибку в консоли
            error_message = f"Произошла критическая ошибка в стрим-генераторе: {e}"
            print(error_message)
            import traceback
            traceback.print_exc()  # Печатаем полный traceback для отладки
            yield error_message

    return StreamingResponse(stream_generator(), media_type="text/plain")