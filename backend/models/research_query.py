"""ResearchQuery model — tracks each web search the Research Agent performs."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class ResearchQuery(Base):
    __tablename__ = "research_queries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    research_job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("jobs.id"), index=True
    )
    query_text: Mapped[str] = mapped_column(Text)
    results_count: Mapped[int] = mapped_column(Integer, default=0)
    executed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
