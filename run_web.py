# run_web.py

import uvicorn
import webbrowser
import threading
import time

HOST = "127.0.0.1"
PORT = 8000

def open_browser():
    """Открывает браузер на нужной странице после небольшой задержки."""
    time.sleep(2)
    webbrowser.open_new(f"http://{HOST}:{PORT}")
    print(f"Интерфейс чата должен был открыться в вашем браузере по адресу http://{HOST}:{PORT}")

if __name__ == "__main__":
    print("--- Запуск локального веб-интерфейса для чат-агента ---")

    # Запускаем открытие браузера в отдельном потоке, чтобы не блокировать сервер
    threading.Thread(target=open_browser, daemon=True).start()

    # Запускаем веб-сервер с приложением FastAPI
    # Uvicorn будет автоматически перезагружать сервер при изменении кода.
    uvicorn.run("web_app:app", host=HOST, port=PORT, reload=True)