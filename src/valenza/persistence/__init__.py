"""Persistencia local protegida; no abre bases persistentes sin SQLCipher."""

from .database import DatabaseSecurityError, LocalDatabase
from .repository import FinanceRepository

__all__ = ["DatabaseSecurityError", "FinanceRepository", "LocalDatabase"]
