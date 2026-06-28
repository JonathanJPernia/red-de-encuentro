from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SearchLog(Base):
    __tablename__ = "search_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    user_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    query_masked: Mapped[str] = mapped_column(String(255), nullable=False)
    results_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    response_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
