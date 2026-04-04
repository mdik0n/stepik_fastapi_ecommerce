from app.database import Base
from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    role: Mapped[str] = mapped_column(String, nullable=False, default="buyer")  # "buyer" or "seller"

    products: Mapped[list["Product"]] = relationship("Product", back_populates="seller", lazy="selectin")
    reviews: Mapped[list["Review"]] = relationship("Review", back_populates="user", lazy="selectin")

    cart_items: Mapped[list["CartItem"]] = relationship("CartItem", back_populates="user", cascade="all,delete-orphan")

    orders: Mapped[list["Order"]] = relationship("Order", back_populates="user", cascade="all,delete-orphan")
