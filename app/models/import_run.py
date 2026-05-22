"""Import Run model – tracks workbook import executions and GitHub update checks."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ImportRun(Base):
    """Tracks each execution of the workbook import."""

    __tablename__ = "import_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(500), nullable=False, comment="Source workbook filename")
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="running", comment="running, completed, failed"
    )
    sheets_processed: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="JSON list of sheet names processed"
    )
    rows_loaded: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="Total rows loaded")
    rows_skipped: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="Rows skipped due to errors")
    error_log: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Errors encountered")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # GitHub update tracking (system-level, stored on the latest import run)
    last_checked_github_commit: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Last checked GitHub commit SHA"
    )
    latest_github_tag: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="Latest GitHub release tag (e.g. 2026.1.1)"
    )

    def __repr__(self) -> str:
        return f"<ImportRun id={self.id} file={self.filename!r} status={self.status!r}>"
