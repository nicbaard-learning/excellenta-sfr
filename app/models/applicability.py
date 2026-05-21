"""Framework applicability rule model – context-based filtering."""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, Boolean, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class FrameworkApplicabilityRule(Base):
    """Rules that describe when a framework is applicable based on context attributes."""

    __tablename__ = "framework_applicability_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    framework_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("frameworks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attribute_name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="e.g. jurisdiction, business_model, size, privacy_context, domain"
    )
    attribute_value: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="e.g. EU, SaaS, small, healthcare"
    )
    is_recommended: Mapped[bool] = mapped_column(Boolean, default=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_sheet: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # relationships
    framework: Mapped["Framework"] = relationship("Framework", back_populates="applicability_rules")

    __table_args__ = (
        UniqueConstraint("framework_id", "attribute_name", "attribute_value", name="uq_applicability_rule"),
    )

    def __repr__(self) -> str:
        return f"<FrameworkApplicabilityRule fw={self.framework_id} {self.attribute_name}={self.attribute_value}>"
