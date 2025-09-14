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


# --- ИНСТРУМЕНТ ПЕРЕВОДА НА МЕНЕДЖЕРА ---
async def local_transfer_to_manager(bot, manager_id, user_info, history, user_question) -> str:
    print(f"Локальный инструмент: перевод на менеджера...")
    user_info_str = f"<b>Имя:</b> {user_info.get('full_name')}\n<b>ID:</b> {user_info.get('id')}"
    if user_info.get('username'):
        user_info_str += f"\n<b>Username:</b> @{user_info.get('username')}"
    history_str = "\n".join([f"<b>{msg['role'].upper()}:</b>\n<pre>{msg['content']}</pre>" for msg in history])
    final_message = (
        f"⚠️ <b>[ЛОКАЛЬНЫЙ АГЕНТ] Новое обращение!</b> ⚠️\n\n"
        f"<b>Контакт клиента:</b>\n{user_info_str}\n\n"
        f"<b>История диалога:</b>\n--------------------\n{history_str}"
    )
    try:
        await bot.send_message(chat_id=manager_id, text=final_message, parse_mode='HTML')
        return "Уведомление менеджеру успешно отправлено. Сообщи пользователю, что менеджер скоро свяжется с ним."
    except Exception as e:
        return f"Ошибка при отправке уведомления менеджеру: {e}"