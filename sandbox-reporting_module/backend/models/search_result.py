"""SearchResult model — one row per organic result returned by a search query."""

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class SearchResult(Base):
    __tablename__ = "search_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    query_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("search_queries.id"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer)
    url: Mapped[str] = mapped_column(String(2048))
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_search_results_query_id", "query_id"),)
