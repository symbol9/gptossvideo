# local_agent_handler.py (исправленная версия с циклом)

import json
from openai import AsyncOpenAI
from local_tools import local_faq_search, local_transfer_to_manager

# ... (tools_definition остается без изменений)
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


# --- НОВАЯ ВЕРСИЯ ФУНКЦИИ ---
async def get_local_model_response_stream(history: list, context: dict):
    """
    Финальная версия, которая генерирует подробные, экспертные ответы
    и поддерживает многошаговые вызовы инструментов.
    """
    client = AsyncOpenAI(base_url='http://localhost:11434/v1', api_key='ollama')

    system_prompt = """
Ты — «ТехноМир», сотрудник поддержки. Твоя работа — это строгая последовательность действий с инструментами.

**Твоё ГЛАВНОЕ и САМОЕ СТРОГОЕ правило — никогда не придумывать информацию.** Передавай ТОЛЬКО факты из источника.

**ПРАВИЛА РАБОТЫ С ИНСТРУМЕНТАМИ (ОБЯЗАТЕЛЬНО К ВЫПОЛНЕНИЮ):**
1.  **Инструмент `FAQSearch` — только для внутреннего поиска.** Его результат ("найдено" или "не найдено") **НИКОГДА** не является финальным ответом для пользователя. После получения результата от `FAQSearch` ты **ОБЯЗАН** сделать одно из двух:
    - **Если что-то найдено:** отформатируй ответ для пользователя согласно правилам ниже.
    - **Если ничего не найдено:** немедленно и без раздумий **ВЫЗОВИ инструмент `TransferToManager`**.

2.  **Инструмент `GetOrderInfo` — для проверки заказов.**
    - **Если заказ найден:** отформатируй ответ по шаблону ниже.
    - **Если заказ не найден:** сообщи пользователю об этом по шаблону ниже.

**Логика поведения:**
- **Вежливые фразы («привет», «спасибо»):** Отвечай коротко и вежливо, не используя инструменты.
- **Нерелевантные вопросы («кто такой Пушкин?»):** Если вопрос явно не про компанию, вежливо откажись от ответа.

**ИНСТРУКЦИИ ПО ФОРМАТИРОВАНИЮ ФИНАЛЬНЫХ ОТВЕТОВ:**

- **GetOrderInfo:**
  - **Если заказ найден:** Используй шаблон:
    «Информация по вашему заказу №[номер]:
    - **Статус:** [статус]
    - **Состав заказа:** [состав]
    - **Получатель:** [имя клиента]
    - **Трек-номер:** [трек-номер или "пока не присвоен"]»
  - **Если заказ не найден:** Используй фразу: «К сожалению, заказ с таким номером не найден в нашей системе. Пожалуйста, проверьте правильность введенного номера».

- **FAQSearch (когда что-то найдено):**
  - Извлеки из найденного текста **только сам ответ**, игнорируя служебные заголовки («Вопрос:», «Ответ:»).
  - Представь его в чистом, разговорном виде. Не разбивай один абзац на несколько пунктов списка.
  - Сохраняй Markdown-ссылки.

- **TransferToManager (после вызова):**
  - Когда инструмент вернет "Уведомление отправлено", сообщи пользователю: «Это хороший вопрос. Чтобы дать точный ответ, я передам ваш диалог менеджеру».
"""

    messages = [{"role": "system", "content": system_prompt}] + history

    # --- НАЧАЛО ЦИКЛА ОБРАБОТКИ ИНСТРУМЕНТОВ ---
    while True:
        response_stream = await client.chat.completions.create(
            model="gpt-oss:20b", messages=messages,
            tools=tools_definition, tool_choice="auto",
            stream=True, temperature=0
        )

        tool_calls = []
        collected_content = ""

        # Собираем ответ от модели (текст или вызов инструмента)
        async for chunk in response_stream:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                collected_content += delta.content
            if delta and delta.tool_calls:
                for tc_chunk in delta.tool_calls:
                    if len(tool_calls) <= tc_chunk.index:
                        tool_calls.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                    tc = tool_calls[tc_chunk.index]
                    if tc_chunk.id: tc["id"] = tc_chunk.id
                    if tc_chunk.function:
                        if tc_chunk.function.name: tc["function"]["name"] += tc_chunk.function.name
                        if tc_chunk.function.arguments: tc["function"]["arguments"] += tc_chunk.function.arguments

        # Если модель решила вызвать инструмент
        if tool_calls:
            messages.append({"role": "assistant", "tool_calls": tool_calls})

            # Выполняем все инструменты, которые запросила модель
            for tool_call in tool_calls:
                function_name = tool_call["function"]["name"]
                try:
                    args = json.loads(tool_call["function"]["arguments"])
                    result = ""
                    if function_name == "FAQSearch":
                        result = local_faq_search(query=args.get("query"))
                    elif function_name == "GetOrderInfo":
                        from agency.SupportAgent.tools.OrderTools import GetOrderInfo
                        result = GetOrderInfo(order_id=args.get("order_id")).run()
                    elif function_name == "TransferToManager":
                        # ВАЖНО: передаем актуальный контекст
                        result = await local_transfer_to_manager(
                            bot=context.get("bot_instance"), manager_id=context.get("manager_id"),
                            user_info=context["user_info"], history=context["message_history"],
                            user_question=args.get("user_question")
                        )

                    messages.append({"tool_call_id": tool_call["id"], "role": "tool", "name": function_name,
                                     "content": str(result)})
                except Exception as e:
                    error_message = f"Ошибка при выполнении инструмента {function_name}: {e}"
                    messages.append({"tool_call_id": tool_call["id"], "role": "tool", "name": function_name,
                                     "content": error_message})

            # Продолжаем цикл, чтобы отправить результат инструмента обратно модели
            continue

            # Если модель вернула текстовый ответ - выходим из цикла
        else:
            final_response_stream = await client.chat.completions.create(
                model="gpt-oss:20b", messages=messages, stream=True
            )
            async for chunk in final_response_stream:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
            return  # Завершаем генерацию