# check_db.py
import chromadb

CHROMA_DB_PATH = "./chroma_db_local"
COLLECTION_NAME = "faq_local_collection"

print(f"--- Проверяю базу данных ChromaDB в '{CHROMA_DB_PATH}' ---")
print(f"Коллекция: '{COLLECTION_NAME}'")

try:
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    collection = client.get_collection(name=COLLECTION_NAME)

    count = collection.count()
    print(f"\n[РЕЗУЛЬТАТ] Количество записей в коллекции: {count}")

    if count > 0:
        print("\n--- Содержимое базы данных (первые 5 записей) ---")
        data = collection.get(limit=5, include=["metadatas", "documents"])
        print(data)

    print("\n--- ДИАГНОЗ ---")
    if count == 0:
        print("🔴 ПРОБЛЕМА: База данных пуста! Данные из faq.md не были загружены.")
    else:
        print("🟢 УСПЕХ: База данных содержит записи. Проблема не в наполнении.")

except Exception as e:
    print(f"\n🔴 КРИТИЧЕСКАЯ ОШИБКА: Не удалось получить доступ к базе или коллекции.")
    print(f"   Детали: {e}")
    print("   Это означает, что база данных не была создана правильно.")