# local_agent_handler.py
import json
from openai import AsyncOpenAI
from local_tools import local_faq_search, local_transfer_to_manager

# --- УЛУЧШЕННОЕ ОПИСАНИЕ ИНСТРУМЕНТОВ ---
tools_definition = [
    {
        "type": "function", "function": {
        "name": "FAQSearch",
        "description": "Используется для ответа на ОБЩИЕ вопросы: доставка, возврат, гарантии.",
        "parameters": {"type": "object",
                       "properties": {"query": {"type": "string", "description": "Вопрос пользователя."}},
                       "required": ["query"]},
    }
    },
    {
        "type": "function", "function": {
        "name": "GetOrderInfo",
        "description": "Используется для получения статуса КОНКРЕТНОГО заказа по его номеру (ID).",
        "parameters": {"type": "object",
                       "properties": {"order_id": {"type": "integer", "description": "Номер заказа."}},
                       "required": ["order_id"]},
    }
    },
    {
        "type": "function", "function": {
        "name": "TransferToManager",
        "description": "Используется, когда пользователь прямо просит позвать человека или другие инструменты не помогли.",
        "parameters": {"type": "object",
                       "properties": {"user_question": {"type": "string", "description": "Вопрос пользователя."}},
                       "required": ["user_question"]},
    }
    }
]


async def get_local_model_response_stream(history: list, context: dict):
    """
    Финальная стриминг-версия, которая поддерживает инструменты и обрабатывает ошибки.
    """
    client = AsyncOpenAI(base_url='http://localhost:11434/v1', api_key='ollama')

    # --- ВОЗВРАЩАЕМ УМНЫЙ И СТРОГИЙ ПРОМПТ ---
    system_prompt = """Ты — 'ТехноМир', профессиональный ИИ-ассистент поддержки.

**Твои главные правила:**
1.  **Действуй, а не советуй.** Твоя задача — самостоятельно использовать инструменты, а не говорить пользователю, как их использовать.
2.  **Основывай ответ ТОЛЬКО на данных от инструмента.** Не придумывай детали, номера заказов или имена.
3.  **Если инструмент вернул ошибку или не нашел информацию (например, "Заказ не найден" или "В базе знаний не найдено ответа"), вежливо сообщи об этом пользователю и предложи альтернативу** (например, "проверить номер заказа" или "переспросить по-другому"). НЕ молчи.
4.  **Всегда используй Markdown для форматирования:**
    - Ключевые моменты выделяй **жирным**.
    - Используй списки с маркером `-`, если пунктов несколько.
    - Обращайся к клиенту на "Вы".
5.  **Отвечай кратко и по делу.**

Твоя цель — быть быстрым и точным помощником.
"""

    messages = [{"role": "system", "content": system_prompt}] + history

    # Шаг 1: Первый запрос для вызова инструмента
    response = await client.chat.completions.create(
        model="gpt-oss:20b",
        messages=messages,
        tools=tools_definition,
        tool_choice="auto"
    )
    response_message = response.choices[0].message

    # Если инструментов нет, просто стримим прямой ответ модели
    if not response_message.tool_calls:
        if response_message.content:
            # Создаем "фейковый" стрим для совместимости
            async def text_streamer(text):
                yield text

            async for chunk in text_streamer(response_message.content):
                yield chunk
        return

    # Шаг 1.5: Выполняем инструменты
    messages.append(response_message)
    for tool_call in response_message.tool_calls:
        function_name = tool_call.function.name
        args = json.loads(tool_call.function.arguments)
        result = ""
        try:
            if function_name == "FAQSearch":
                result = local_faq_search(query=args.get("query"))
            elif function_name == "GetOrderInfo":
                from agency.SupportAgent.tools.OrderTools import GetOrderInfo
                tool = GetOrderInfo(order_id=args.get("order_id"))
                result = tool.run()
            elif function_name == "TransferToManager":
                result = await local_transfer_to_manager(
                    bot=context["bot_instance"], manager_id=context["manager_id"],
                    user_info=context["user_info"], history=context["message_history"],
                    user_question=args.get("user_question")
                )
            messages.append(
                {"tool_call_id": tool_call.id, "role": "tool", "name": function_name, "content": str(result)})
        except Exception as e:
            messages.append(
                {"tool_call_id": tool_call.id, "role": "tool", "name": function_name, "content": f"Ошибка: {e}"})

    # Шаг 2: Второй, уже стриминговый, запрос с результатами
    response_stream = await client.chat.completions.create(
        model="gpt-oss:20b",
        messages=messages,
        stream=True
    )

    # Отдаем финальный ответ по кусочкам
    has_content = False
    async for chunk in response_stream:
        content = chunk.choices[0].delta.content
        if content:
            has_content = True
            yield content

    if not has_content:
        yield "Я обработал ваш запрос, но не смог сформировать ответ. Пожалуйста, попробуйте переформулировать."

