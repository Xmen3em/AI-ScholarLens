from abc import ABC, abstractmethod
from typing import Any, ContextManager, Dict, List, Optional

from sqlalchemy.orm import Session


class BaseDatabase(ABC):
    @abstractmethod
    def get_session(self) -> ContextManager[Session]:
        """Get a database session."""

    @abstractmethod
    def startup(self) -> None:
        """Perform any necessary startup operations for the database."""

    @abstractmethod
    def teardown(self) -> None:
        """Perform any necessary teardown operations for the database."""


class BaseRepository(ABC):
    def __init__(self, session: Session):
        self.session = session

    @abstractmethod
    def create(self, data: Dict[str, Any]) -> Any:
        """Create a new record in the database."""

    @abstractmethod
    def get_by_id(self, record_id: Any) -> Optional[Any]:
        """Read a record from the database by its ID."""

    @abstractmethod
    def update(self, record_id: Any, data: Dict[str, Any]) -> Optional[Any]:
        """Update a record in the database by its ID."""

    @abstractmethod
    def delete(self, record_id: Any) -> bool:
        """Delete a record from the database by its ID."""

    @abstractmethod
    def list(self, limit: int = 100, offset: int = 0) -> List[Any]:
        """List records from the database with pagination."""
