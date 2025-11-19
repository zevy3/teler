
from source.Database.DBHelper import DataBaseHelper

#  Временный файл как использовать бдшку

def main():
    # Создаем подключение к БД
    # Нужные таблицы создаст автоматически
    db = DataBaseHelper(db_url="postgresql://user:password@localhost/dbname")

    # Создать канал
    db.create_channel(channel_id=10001, name="Mash")
    db.create_channel(channel_id=10002, name="Moscowach")
    db.create_channel(channel_id=-10003, name="NegIdTest")

    # Создать пользователя
    db.create_user(user_id=12345, name="User")

    # Подписываем пользователя на два канала
    db.update_user_channels(user_id=12345, add=[10001, 10002])

    # Удаляем один канал из подписок
    db.update_user_channels(user_id=12345, remove=[10001])

    # Получить инфу о пользователе
    user = db.get_user(12345)
    print("User:", user)

    # Удаляем пользователя. У каналов уменьшется количество подписчиков
    db.delete_user(12345)

    # Пробуем удалить канал без подписчиков
    db.delete_channel(10001)  # Успешно

    # Ошибка, если есть подписчики на канал
    try:
        db.delete_channel(10002)
    except ValueError as e:
        print(e)

if __name__ == "__main__":
    main()
