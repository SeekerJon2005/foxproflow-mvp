import redis
import json
from typing import Optional, Any
import logging
import os


class RedisManager:
    """Менеджер для работы с Redis для дедупликации и кэширования."""

    def __init__(self):
        self.redis_client = None
        self.hash_key_prefix = "freight_hash:"
        try:
            # Настройки подключения с возможностью переопределения через переменные окружения
            redis_host = os.getenv('REDIS_HOST', 'localhost')
            redis_port = int(os.getenv('REDIS_PORT', 6379))
            redis_db = int(os.getenv('REDIS_DB', 0))
            redis_password = os.getenv('REDIS_PASSWORD', None)

            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                password=redis_password,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
                retry_on_timeout=True
            )
            self._check_connection()
        except Exception as e:
            logging.error(f"❌ Ошибка инициализации Redis: {e}")
            print(f"❌ Ошибка инициализации Redis: {e}")
            self.redis_client = None

    def _check_connection(self):
        """Проверка подключения к Redis"""
        try:
            if self.redis_client and self.redis_client.ping():
                logging.info("✅ Успешное подключение к Redis")
                print("✅ Успешное подключение к Redis")
            else:
                logging.warning("Не удалось проверить подключение к Redis")
                print("Не удалось проверить подключение к Redis")
        except redis.ConnectionError as e:
            logging.error(f"❌ Ошибка подключения к Redis: {e}")
            print(f"❌ Ошибка подключения к Redis: {e}")
            self.redis_client = None
        except Exception as e:
            logging.error(f"❌ Неизвестная ошибка при подключении к Redis: {e}")
            print(f"❌ Неизвестная ошибка при подключении к Redis: {e}")
            self.redis_client = None

    def is_duplicate(self, unique_hash: str, ttl_seconds: int = 7 * 24 * 3600) -> bool:
        """Проверяет, является ли хеш дубликатом"""
        if not self.redis_client:
            return False

        try:
            full_key = f"{self.hash_key_prefix}{unique_hash}"
            result = self.redis_client.set(full_key, "1", nx=True, ex=ttl_seconds)
            return result is None
        except redis.RedisError as e:
            logging.error(f"Ошибка проверки дубликата для хеша {unique_hash}: {e}")
            return False

    def cache_data(self, key: str, data: Any, ttl_seconds: int = 3600) -> None:
        """Универсальный метод для кэширования любых данных"""
        if not self.redis_client:
            return

        try:
            serialized_data = json.dumps(data)
            self.redis_client.setex(key, ttl_seconds, serialized_data)
            logging.debug(f"Данные успешно закэшированы для ключа {key}")
        except (TypeError, redis.RedisError) as e:
            logging.error(f"Ошибка кэширования данных для ключа {key}: {e}")

    def get_cached_data(self, key: str) -> Optional[Any]:
        """Получение данных из кэша"""
        if not self.redis_client:
            return None

        try:
            data = self.redis_client.get(key)
            if data:
                return json.loads(data)
            return None
        except (json.JSONDecodeError, redis.RedisError) as e:
            logging.error(f"Ошибка получения данных из кэша по ключу {key}: {e}")
            return None

    def is_redis_available(self) -> bool:
        """Проверка доступности Redis"""
        if not self.redis_client:
            return False

        try:
            return self.redis_client.ping()
        except redis.RedisError:
            return False


# Создаем глобальный экземпляр для импорта
redis_manager = RedisManager()

if __name__ == "__main__":
    # Подробное тестирование подключения к Redis
    print("🔍 Тестирование подключения к Redis...")

    try:
        # Проверяем базовое подключение
        result = redis_manager.redis_client.ping() if redis_manager.redis_client else False
        print(f"✅ Ping Redis: {result}")

        # Тестируем метод is_duplicate
        test_hash = "test_hash_123"
        test_result = redis_manager.is_duplicate(test_hash, 60)
        print(f"✅ Тест is_duplicate (первый вызов): {test_result} (ожидается False)")

        # Проверяем, что второй вызов возвращает True (дубликат)
        test_result2 = redis_manager.is_duplicate(test_hash, 60)
        print(f"✅ Тест is_duplicate (второй вызов): {test_result2} (ожидается True)")

        # Тестируем кэширование
        test_data = {"data": "test_value", "timestamp": "2024-01-01T12:00:00"}
        redis_manager.cache_data("test_key", test_data, 60)
        cached_data = redis_manager.get_cached_data("test_key")
        print(f"✅ Тест кэширования: {cached_data}")

        # Проверяем доступность Redis
        availability = redis_manager.is_redis_available()
        print(f"✅ Доступность Redis: {availability}")

        if redis_manager.redis_client:
            # Получаем информацию о сервере
            info = redis_manager.redis_client.info()
            print(f"✅ Версия Redis: {info.get('redis_version', 'N/A')}")
            print(f"✅ Использование памяти: {info.get('used_memory_human', 'N/A')}")

        print("🎉 Все тесты прошли успешно! Redis Manager работает корректно.")

    except Exception as e:
        print(f"❌ Ошибка при тестировании Redis Manager: {e}")
        import traceback

        traceback.print_exc()