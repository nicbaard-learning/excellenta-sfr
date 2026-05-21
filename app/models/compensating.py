"""Compensating Control Link model."""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CompensatingControlLink(Base):
    """A compensating control that partially or fully satisfies a canonical control requirement."""

    __tablename__ = "compensating_control_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    control_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("controls.id", ondelete="CASCADE"), nullable=False, index=True
    )
    compensating_control_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="Reference ID of the compensating control"
    )
    compensating_control_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    compensating_control_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    compensation_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="e.g. technical, procedural, contractual"
    )
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_sheet: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # relationships
    control: Mapped["Control"] = relationship("Control", back_populates="compensating_links")

    def __repr__(self) -> str:
        return f"<CompensatingControlLink id={self.id} ctrl={self.control_id}>"
