# agency/SupportAgent/tools/ManagerTools.py

from agency_swarm import function_tool, RunContextWrapper
from pydantic import Field


# Вместо класса мы создаем асинхронную функцию с декоратором
@function_tool
async def TransferToManager(
        ctx: RunContextWrapper,
        user_question: str = Field(
            ..., description="Полный и точный вопрос пользователя, который стал причиной перевода на менеджера."
        )
) -> str:
    """
    Этот инструмент нужно использовать, когда пользователь просит позвать человека,
    жалуется на серьезную проблему (сломанный товар, возврат денег),
    или когда вы не можете найти ответ на его вопрос.
    Он отправляет уведомление менеджеру с историей диалога.
    """
    print("Executing new function-based TransferToManager tool...")

    bot = ctx.context.user_context.get("bot_instance")
    user_info_dict = ctx.context.user_context.get("user_info")
    message_history = ctx.context.user_context.get("message_history")
    manager_id = ctx.context.user_context.get("manager_id")

    if not all([bot, user_info_dict, message_history, manager_id]):
        missing = [k for k, v in {"bot": bot, "user": user_info_dict, "history": message_history,
                                  "manager_id": manager_id}.items() if not v]
        error_message = f"Ошибка: Не удалось получить данные из контекста. Отсутствуют: {', '.join(missing)}"
        print(f"ERROR in TransferToManager: {error_message}")
        return error_message

    # Форматируем сообщение (код без изменений)
    user_info_str = (
        f"<b>Имя:</b> {user_info_dict.get('full_name')}\n"
        f"<b>ID:</b> {user_info_dict.get('id')}"
    )
    if user_info_dict.get('username'):
        user_info_str += f"\n<b>Username:</b> @{user_info_dict.get('username')}"

    # Добавляем последний вопрос в историю для полноты
    full_history = message_history + [{"role": "user", "content": user_question}]
    history_str = "\n".join(
        [f"<b>{msg['role'].upper()}:</b>\n<pre>{msg['content']}</pre>" for msg in full_history])

    final_message = (
        f"⚠️ <b>Новое обращение, требуется вмешательство!</b> ⚠️\n\n"
        f"<b>Контакт клиента:</b>\n{user_info_str}\n\n"
        f"<b>История диалога:</b>\n--------------------\n{history_str}"
    )

    try:
        await bot.send_message(
            chat_id=manager_id,
            text=final_message,
            parse_mode='HTML'
        )
        print("Notification sent to manager successfully.")
        return "Уведомление менеджеру успешно отправлено. Сообщи пользователю, что менеджер скоро свяжется с ним."
    except Exception as e:
        error_message = f"Ошибка при отправке уведомления менеджеру: {e}"
        print(f"ERROR in TransferToManager: {error_message}")
        return error_message

