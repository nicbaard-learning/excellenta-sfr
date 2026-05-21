"""Jurisdiction models – geography / regulatory region support."""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Jurisdiction(Base):
    """A geographic or regulatory jurisdiction (country, region, union)."""

    __tablename__ = "jurisdictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(
        String(10), unique=True, nullable=False, index=True, comment="ISO 3166-1 alpha-2 or custom code"
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    region: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="e.g. EU, APAC, NA, LATAM"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<Jurisdiction id={self.id} code={self.code!r}>"


class FrameworkJurisdiction(Base):
    """Many-to-many link between frameworks and jurisdictions."""

    __tablename__ = "framework_jurisdictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    framework_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("frameworks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    jurisdiction_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("jurisdictions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_primary: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # relationships
    framework: Mapped["Framework"] = relationship("Framework", back_populates="jurisdictions")
    jurisdiction: Mapped["Jurisdiction"] = relationship("Jurisdiction")

    __table_args__ = (
        UniqueConstraint("framework_id", "jurisdiction_id", name="uq_framework_jurisdiction"),
    )

    def __repr__(self) -> str:
        return f"<FrameworkJurisdiction fw={self.framework_id} j={self.jurisdiction_id}>"
