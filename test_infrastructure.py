#!/usr/bin/env python3
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from sqlalchemy import text  # Добавьте этот импорт
from data_layer.database import init_database, get_db
from data_layer.redis_manager import redis_manager
from core.config import DATABASE_CONFIG, REDIS_CONFIG


def test_database():
    print("Testing database connection...")
    try:
        init_database()
        with get_db() as db:
            # Оберните запросы в text()
            result = db.execute(text("SELECT version()")).fetchone()
            print(f"✓ PostgreSQL version: {result[0]}")

            # Проверка существования таблиц
            tables = db.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)).fetchall()

            print("✓ Tables in database:")
            for table in tables:
                print(f"  - {table[0]}")

        return True
    except Exception as e:
        print(f"✗ Database error: {str(e)}")
        return False

def test_redis():
    print("Testing Redis connection...")
    try:
        # Тестирование базовых операций
        redis_manager.set_key("test_key", "test_value", 60)
        value = redis_manager.get_key("test_key")
        
        if value == "test_value":
            print("✓ Redis connection successful")
            return True
        else:
            print("✗ Redis test failed")
            return False
    except Exception as e:
        print(f"✗ Redis error: {str(e)}")
        return False

def test_config():
    print("Testing configuration...")
    try:
        print(f"✓ Database config: {DATABASE_CONFIG['host']}:{DATABASE_CONFIG['port']}")
        print(f"✓ Redis config: {REDIS_CONFIG['host']}:{REDIS_CONFIG['port']}")
        return True
    except Exception as e:
        print(f"✗ Config error: {str(e)}")
        return False

if __name__ == "__main__":
    print("Running infrastructure tests...")
    print("=" * 50)
    
    tests = [
        test_config,
        test_database,
        test_redis
    ]
    
    results = []
    for test in tests:
        try:
            results.append(test())
        except Exception as e:
            print(f"✗ Test {test.__name__} failed with exception: {str(e)}")
            results.append(False)
        print()
    
    passed = sum(results)
    total = len(results)
    
    print("=" * 50)
    print(f"Test results: {passed}/{total} passed")
    
    if passed == total:
        print("✓ All infrastructure tests passed!")
        sys.exit(0)
    else:
        print("✗ Some tests failed!")
        sys.exit(1)
