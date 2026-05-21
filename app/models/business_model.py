"""Business Model / TPRM vendor-category model."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BusinessModel(Base):
    """A business model or TPRM vendor category (e.g. SaaS, IaaS, MSP, MSSP)."""

    __tablename__ = "business_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True, comment="Short code e.g. SAAS, IAAS, MSP"
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="Grouping e.g. cloud, professional-services, telecom"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<BusinessModel id={self.id} code={self.code!r}>"
