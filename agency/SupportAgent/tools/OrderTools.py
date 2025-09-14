# agency/SupportAgent/tools/OrderTools.py

import os
import psycopg2
from agency_swarm.tools import BaseTool
from pydantic import Field
from dotenv import load_dotenv

load_dotenv()

# Загружаем конфигурацию БД из .env
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "dbname": os.getenv("DB_NAME")
}


class GetOrderInfo(BaseTool):
    """
    Этот инструмент получает статус, трек-номер и детали заказа по его ID из базы данных PostgreSQL.
    Используйте его, когда пользователь прямо спрашивает о своем заказе, указывая его номер.
    """
    order_id: int = Field(
        ..., description="Номер (ID) заказа, который нужно найти в базе данных. Например, 1."
    )

    def run(self):
        """Выполняет запрос к базе данных PostgreSQL."""
        print(f"Инструмент GetOrderInfo: ищу заказ с ID {self.order_id}")
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cur = conn.cursor()

            # Выполняем JOIN, чтобы получить имя клиента
            query = """
                SELECT o.status, o.tracking_number, o.details, c.name
                FROM orders o
                JOIN customers c ON o.customer_id = c.customer_id
                WHERE o.order_id = %s
            """
            cur.execute(query, (self.order_id,))
            result = cur.fetchone()

            cur.close()
            conn.close()

            if result:
                status, tracking, details, customer_name = result
                response = (f"Заказ №{self.order_id} для клиента '{customer_name}' найден. "
                            f"Содержимое: '{details}'. "
                            f"Статус: '{status}'. "
                            f"Трек-номер для отслеживания: {tracking or 'еще не присвоен'}.")
                print(f"Результат: {response}")
                return response
            else:
                print("Результат: Заказ не найден.")
                return f"Ошибка: Заказ с номером {self.order_id} не найден в базе данных."
        except Exception as e:
            error_msg = f"Критическая ошибка при подключении к базе данных: {e}"
            print(f"ОШИБКА: {error_msg}")
            return error_msg