import logging
from contextlib import contextmanager
from typing import Generator, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from src.db.interfaces.base import BaseDatabase

logger = logging.getLogger(__name__)

class PostgreSQLSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="POSTGRES_", extra="ignore")

    database_url: str = Field(default="postgresql://rag_user:rag_password@localhost:5432/rag_db", description="PostgreSQL database URL")
    echo_sql: bool = Field(default=False, description="Whether to echo SQL statements")
    pool_size: int = Field(default=20, description="Size of the connection pool")
    max_overflow: int = Field(default=0, description="Maximum number of connections to create beyond the pool size")
        
Base = declarative_base()

class PostgreSQLDatabase(BaseDatabase):
    def __init__(self, config: PostgreSQLSettings):
        self.config = config
        self.engine: Optional[Engine] = None
        self.session_factory: Optional[sessionmaker] = None

    def startup(self) -> None:
        try:
            # Log connection attempt
            logger.info(
                f"Attempting to connect to PostgreSQL at: {self.config.database_url.split('@')[1] if '@' in self.config.database_url else 'localhost'}"
            )

            self.engine = create_engine(
                self.config.database_url,
                echo=self.config.echo_sql,
                pool_size=self.config.pool_size,
                max_overflow=self.config.max_overflow,
                pool_pre_ping=True,  # Verify connections before use
            )

            self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

            # Test the connection
            assert self.engine is not None
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                logger.info("Database connection test successful")

            # Check which tables exist before creating
            inspector = inspect(self.engine)
            existing_tables = inspector.get_table_names()

            # Create tables if they don't exist (idempotent operation)
            Base.metadata.create_all(bind=self.engine)

            # Check if any new tables were created
            updated_tables = inspector.get_table_names()
            if new_tables := set(updated_tables) - set(existing_tables):
                logger.info(f"Created new tables: {', '.join(new_tables)}")
            else:
                logger.info("All tables already exist - no new tables created")

            logger.info("PostgreSQL database initialized successfully")
            assert self.engine is not None
            logger.info(f"Database: {self.engine.url.database}")
            logger.info(f"Total tables: {', '.join(updated_tables) if updated_tables else 'None'}")
            logger.info("Database connection established")

        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL database: {e}")
            raise

    def teardown(self) -> None:
        if self.engine:
            logger.info("Closing PostgreSQL database connection...")
            self.engine.dispose()
            logger.info("PostgreSQL database connection closed.")

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        if not self.session_factory:
            raise RuntimeError("Database session factory is not initialized. Call startup() first.")
        
        session: Session = self.session_factory()
        try:
            yield session
        except Exception as e:
            session.rollback()
            logger.error(f"Session rollback due to exception: {e}")
            raise
        finally:
            session.close()     