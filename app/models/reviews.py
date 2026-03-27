from app.database import Base
from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment_date: Mapped[datetime] = mapped_column(default=datetime.now)
    grade: Mapped[float]
    is_active: Mapped[bool] = mapped_column(default=True)

    # Foreign Keys
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="reviews",lazy="selectin")
    product: Mapped["Product"] = relationship("Product", back_populates="reviews",lazy="selectin")
