import json
from openai import AsyncOpenAI
from local_tools import local_faq_search, local_transfer_to_manager

tools_definition = [
    {
        "type": "function", "function": {
        "name": "FAQSearch",
        "description": "Используется для ответа на ОБЩИЕ вопросы: доставка, возврат, гарантии, отмена заказа.",
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
    Финальная версия, которая генерирует подробные, экспертные ответы.
    """
    client = AsyncOpenAI(base_url='http://localhost:11434/v1', api_key='ollama')

    # --- ИЗМЕНЕННЫЙ СИСТЕМНЫЙ ПРОМПТ С "ЗАШИТЫМИ" КОНТАКТАМИ ---
    system_prompt = """Ты — 'ТехноМир', ведущий эксперт и ИИ-ассистент службы поддержки. Твоя задача — предоставлять клиентам исчерпывающие, вежливые и прекрасно отформатированные ответы.

**Твои главные правила:**
1.  **ЭКСПЕРТНАЯ ПОДАЧА:** Когда ты получаешь информацию от инструмента (например, из базы знаний), твоя задача — **не просто пересказать её**, а **сформулировать полный, подробный и заботливый ответ**. Используй вежливые обороты, объясняй детали и предвосхищай возможные вопросы клиента.
2.  **СТРОГО ПО ФАКТАМ:** Твой ответ должен быть **полностью основан** на предоставленных данных от инструмента. Не придумывай ссылки, сроки или условия.
3.  **СТРУКТУРА И ФОРМАТИРОВАНИЕ:** Всегда используй Markdown.
    - Ответ начинай с вежливого приветствия.
    - Ключевые понятия и важные детали выделяй **жирным шрифтом**.
    - Если в ответе несколько шагов или пунктов, используй списки с маркером `-`.
    - Всегда обращайся к клиенту на "Вы".
4.  **ПРОАКТИВНОСТЬ:** Завершай свой ответ предложением помочь чем-либо еще, чтобы показать свою вовлеченность.
5.  **В СЛУЧАЕ НЕУДАЧИ:** Если инструмент не нашел информацию, вежливо сообщи об этом и предложи связаться со службой поддержки, используя **только следующие контактные данные**.

**Контактная информация службы поддержки (ИСПОЛЬЗУЙ ТОЛЬКО ЭТИ ДАННЫЕ):**
- **Телефон:** +7 (800) 555-35-35 (демонстрационный номер)
- **Электронная почта:** support@techno-mir.example.com
- **Чат на сайте:** раздел 'Поддержка' -> 'Начать чат'

**ЗАПРЕЩЕНО:** Придумывать любые другие номера телефонов, почтовые адреса или ссылки.
"""

    messages = [{"role": "system", "content": system_prompt}] + history

    # --- Весь остальной код остается без изменений, как в предыдущей версии ---
    response_stream = await client.chat.completions.create(
        model="gpt-oss:20b",
        messages=messages,
        tools=tools_definition,
        tool_choice="auto",
        stream=True
    )

    tool_calls = []
    collected_content = ""

    async for chunk in response_stream:
        delta = chunk.choices[0].delta
        if delta.content:
            collected_content += delta.content
        if delta.tool_calls:
            for tool_call_chunk in delta.tool_calls:
                if len(tool_calls) <= tool_call_chunk.index:
                    tool_calls.append({
                        "id": "", "type": "function", "function": {"name": "", "arguments": ""}
                    })
                tc = tool_calls[tool_call_chunk.index]
                if tool_call_chunk.id:
                    tc["id"] = tool_call_chunk.id
                if tool_call_chunk.function.name:
                    tc["function"]["name"] += tool_call_chunk.function.name
                if tool_call_chunk.function.arguments:
                    tc["function"]["arguments"] += tool_call_chunk.function.arguments

    if tool_calls:
        messages.append({"role": "assistant", "tool_calls": tool_calls})

        for tool_call in tool_calls:
            function_name = tool_call["function"]["name"]
            try:
                args = json.loads(tool_call["function"]["arguments"])
                result = ""
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
                    {"tool_call_id": tool_call["id"], "role": "tool", "name": function_name, "content": str(result)})
            except Exception as e:
                error_message = f"Ошибка при выполнении инструмента {function_name}: {e}"
                messages.append(
                    {"tool_call_id": tool_call["id"], "role": "tool", "name": function_name, "content": error_message})

        final_response_stream = await client.chat.completions.create(
            model="gpt-oss:20b",
            messages=messages,
            stream=True
        )
        async for chunk in final_response_stream:
            content = chunk.choices[0].delta.content
            if content:
                yield content
        return

    elif collected_content.strip():
        yield collected_content
        return

    else:
        yield "Мне жаль, но я не смог обработать ваш запрос. Пожалуйста, попробуйте переформулировать его."
        return