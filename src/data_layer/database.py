import logging
from typing import List, Dict, Any, Optional
from sqlalchemy import create_engine, text, exc
from sqlalchemy.orm import sessionmaker, scoped_session
from contextlib import contextmanager
from src.core.config import DATABASE_CONFIG

# Настройка логирования
logger = logging.getLogger('Database')
logger.setLevel(logging.DEBUG)

# Создание соединения с базой данных
def get_engine():
    connection_string = f"{DATABASE_CONFIG['drivername']}://{DATABASE_CONFIG['username']}:{DATABASE_CONFIG['password']}@{DATABASE_CONFIG['host']}:{DATABASE_CONFIG['port']}/{DATABASE_CONFIG['database']}"
    return create_engine(connection_string, pool_size=20, max_overflow=0)

engine = get_engine()
SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

@contextmanager
def get_db():
    """Контекстный менеджер для работы с сессией БД"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Database error: {str(e)}")
        raise
    finally:
        db.close()

def init_database():
    """Инициализация базы данных (создание таблиц, если не существуют)"""
    try:
        with get_db() as db:
            # Проверяем существование основных таблиц
            tables = db.execute(text("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)).fetchall()
            
            existing_tables = [t[0] for t in tables]
            logger.info(f"Existing tables: {existing_tables}")
            
            # Если таблиц нет, создаем их через выполнение init_db.sql
            if not any(table in existing_tables for table in ['freights', 'transport_demand', 'macro_data']):
                logger.info("Essential tables not found, running initialization script...")
                # SQLAlchemy не может выполнять произвольные SQL-файлы напрямую,
                # поэтому мы выполним этот шаг через psql при запуске контейнера
                
    except exc.SQLAlchemyError as e:
        logger.error(f"Error initializing database: {str(e)}")
        raise

def insert_freights_batch(freights: List[Dict[str, Any]]):
    """Вставка грузов пачками с проверкой дубликатов"""
    if not freights:
        logger.warning("Attempted to insert empty freights list")
        return
    
    try:
        with get_db() as db:
            # Подготавливаем данные для вставки
            values = []
            for freight in freights:
                values.append({
                    'id': freight.get('id'),
                    'hash': freight.get('hash'),
                    'loading_city': freight.get('loading_city', ''),
                    'unloading_city': freight.get('unloading_city', ''),
                    'distance': freight.get('distance', 0),
                    'cargo': freight.get('cargo', ''),
                    'weight': freight.get('weight', 0),
                    'volume': freight.get('volume', 0),
                    'body_type': freight.get('body_type', ''),
                    'loading_date': freight.get('loading_date', ''),
                    'revenue_rub': freight.get('revenue_rub', 0),
                    'profit_per_km': freight.get('profit_per_km', 0),
                    'loading_lat': freight.get('loading_lat'),
                    'loading_lon': freight.get('loading_lon'),
                    'unloading_lat': freight.get('unloading_lat'),
                    'unloading_lon': freight.get('unloading_lon'),
                    'loading_region': freight.get('loading_region'),
                    'unloading_region': freight.get('unloading_region')
                })
            
            # Используем ON CONFLICT для обработки дубликатов
            stmt = text("""
                INSERT INTO freights (
                    id, hash, loading_city, unloading_city, distance, cargo, weight, 
                    volume, body_type, loading_date, revenue_rub, profit_per_km,
                    loading_lat, loading_lon, unloading_lat, unloading_lon,
                    loading_region, unloading_region
                ) VALUES (
                    :id, :hash, :loading_city, :unloading_city, :distance, :cargo, 
                    :weight, :volume, :body_type, :loading_date, :revenue_rub, 
                    :profit_per_km, :loading_lat, :loading_lon, :unloading_lat, 
                    :unloading_lon, :loading_region, :unloading_region
                )
                ON CONFLICT (id) 
                DO UPDATE SET
                    hash = EXCLUDED.hash,
                    loading_date = EXCLUDED.loading_date,
                    revenue_rub = EXCLUDED.revenue_rub,
                    profit_per_km = EXCLUDED.profit_per_km,
                    unloading_lat = EXCLUDED.unloading_lat,
                    unloading_lon = EXCLUDED.unloading_lon
            """)
            
            db.execute(stmt, values)
            logger.info(f"Inserted/updated {len(freights)} freights")
            
    except exc.SQLAlchemyError as e:
        logger.error(f"Error inserting freights: {str(e)}")
        raise

def get_database_stats():
    """Получение статистики базы данных"""
    try:
        with get_db() as db:
            # Общее количество грузов
            total_freights = db.execute(text("SELECT COUNT(*) FROM freights")).scalar()
            
            # Статистика по весу
            weight_stats = db.execute(text("""
                SELECT MIN(weight), MAX(weight), AVG(weight) 
                FROM freights WHERE weight > 0
            """)).fetchone()
            
            # Типы кузовов
            body_types = db.execute(text("""
                SELECT body_type, COUNT(*) 
                FROM freights 
                GROUP BY body_type 
                ORDER BY COUNT(*) DESC 
                LIMIT 10
            """)).fetchall()
            
            return {
                'total_freights': total_freights,
                'weight_stats': weight_stats,
                'body_types': body_types
            }
            
    except exc.SQLAlchemyError as e:
        logger.error(f"Error getting database stats: {str(e)}")
        return {}
