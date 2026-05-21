"""Assessment Objective model – assessment objectives mapped to controls."""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AssessmentObjective(Base):
    """An assessment objective linked to a specific control."""

    __tablename__ = "assessment_objectives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    control_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("controls.id", ondelete="CASCADE"), nullable=False, index=True
    )
    objective_code: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="Objective reference code e.g. AC-01-O-1"
    )
    objective_text: Mapped[str | None] = mapped_column(Text, nullable=False, comment="The assessment objective")
    source_sheet: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="Workbook sheet name"
    )
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # relationships
    control: Mapped["Control"] = relationship("Control", back_populates="assessment_objectives")

    def __repr__(self) -> str:
        return f"<AssessmentObjective id={self.id} code={self.objective_code!r}>"
