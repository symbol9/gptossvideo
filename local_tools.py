# local_tools.py
import chromadb
from sentence_transformers import SentenceTransformer

# --- НАСТРОЙКИ ---
FAQ_FILE_PATH = "./knowledge_base/faq.md"
CHROMA_DB_PATH = "./chroma_db_local"
COLLECTION_NAME = "faq_local_collection"

# --- ИНИЦИАЛИЗАЦИЯ ---
print("Инициализация локального RAG...")
model = SentenceTransformer('all-MiniLM-L6-v2')
client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

# --- ПРИНУДИТЕЛЬНАЯ ПЕРЕСБОРКА БАЗЫ ---
print("Принудительно пересобираю базу знаний для гарантии чистоты данных...")
try:
    client.delete_collection(name=COLLECTION_NAME)
    print(f"Старая коллекция '{COLLECTION_NAME}' успешно удалена.")
except Exception:
    print(f"Старая коллекция '{COLLECTION_NAME}' не найдена, создаю новую.")

collection = client.get_or_create_collection(name=COLLECTION_NAME)

try:
    with open(FAQ_FILE_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    # Теперь эта "нарезка" будет работать правильно с новым faq.md
    sections = [sec.strip() for sec in content.split('---') if sec.strip()]
    ids = [f'faq_{i}' for i in range(len(sections))]

    if sections:
        collection.add(documents=sections, ids=ids)
        print(f"✅ База знаний успешно наполнена {len(sections)} записями.")
    else:
        print("⚠️ ВНИМАНИЕ: В faq.md не найдено секций для добавления в базу.")
except Exception as e:
    print(f"🔴 ОШИБКА при наполнении базы знаний: {e}")


# --- ИНСТРУМЕНТ ПОИСКА ---
def local_faq_search(query: str) -> str:
    print(f"Локальный RAG: поиск по запросу '{query}'")
    if collection.count() == 0:
        return "База знаний пуста или не была загружена."
    results = collection.query(query_texts=[query], n_results=1)
    if not results or not results['documents'] or not results['documents'][0]:
        return "В базе знаний не найдено ответа."
    return results['documents'][0][0]


async def local_transfer_to_manager(bot, manager_id, user_info, history, user_question) -> str:
    print(f"Инструмент 'Перевод на менеджера': формирую и отправляю сообщение...")

    dialog_id_str = user_info.get('dialog_id', 'Не определен')
    user_info_str = f"<b>Номер диалога:</b> {dialog_id_str}"

    history_str_list = []
    for msg in history:
        content = msg.get('content', '').replace('<', '&lt;').replace('>', '&gt;')
        role = msg.get('role', 'unknown').upper()
        history_str_list.append(f"<b>{role}:</b>\n<pre>{content}</pre>")
    history_str = "\n".join(history_str_list)

    final_message_html = (
        f"⚠️ <b>[ЛОКАЛЬНЫЙ АГЕНТ] Новое обращение!</b> ⚠️\n\n"
        f"<b>{user_info_str}</b>\n\n"
        f"<b>История диалога:</b>\n--------------------\n{history_str}"
    )

    if not bot or not manager_id:
        return "Уведомление менеджеру было бы отправлено, но мы работаем в локальном режиме."

    try:
        await bot.send_message(chat_id=manager_id, text=final_message_html, parse_mode='HTML')
        print(f"✅ Сообщение по диалогу {dialog_id_str} успешно отправлено менеджеру (ID: {manager_id})")
        return "Уведомление менеджеру успешно отправлено. Сообщи пользователю, что менеджер скоро свяжется с ним."
    except Exception as e:
        print(f"🔴 ОШИБКА при отправке уведомления менеджеру по диалогу {dialog_id_str}: {e}")
        return f"Ошибка при отправке уведомления менеджеру: {e}"

