
import os
import shutil

# Удаление файла базы данных SQLite
if os.path.exists('main.db'):
    os.remove('main.db')
    print("Файл 'main.db' удален.")

# Удаление директории с векторными базами ChromaDB
if os.path.isdir('chroma_db'):
    shutil.rmtree('chroma_db')
    print("Директория 'chroma_db' со всеми данными удалена.")

print("Очистка завершена.")
