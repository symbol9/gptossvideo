# agency/SupportAgent/SupportAgent.py

from agency_swarm import Agent
from .tools.OrderTools import GetOrderInfo
from .tools.ManagerTools import TransferToManager


class SupportAgent(Agent):
    def __init__(self):
        # Агент снова имеет простую, жестко заданную конфигурацию
        super().__init__(
            name="SupportAgent",
            description="Агент поддержки клиентов, который отвечает на вопросы и помогает решать проблемы.",
            instructions="""Ты — ассистент 'ТехноМир'.
- Для ответов на общие вопросы о доставке, возвратах, гарантиях ищи информацию в предоставленных тебе файлах.
- Для вопросов о статусе заказа используй `GetOrderInfo`.
- Если не можешь помочь или просят человека, используй `TransferToManager`.""",
            model="gpt-4o",
            files_folder="./files/faq_vs_vs_68c69ad177c48191be5a95b04930e786",
            tools=[GetOrderInfo, TransferToManager],
        )