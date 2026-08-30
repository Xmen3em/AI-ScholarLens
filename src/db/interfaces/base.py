from abc import ABC, abstractmethod
from typing import ContextManager

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
