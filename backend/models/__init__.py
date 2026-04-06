"""ORM models — import all so ``Base.metadata.create_all()`` picks them up."""

from backend.models.base import Base
from backend.models.data_source import DataSource
from backend.models.job import Job
from backend.models.search_query import SearchQuery
from backend.models.search_result import SearchResult

__all__ = ["Base", "DataSource", "Job", "SearchQuery", "SearchResult"]
