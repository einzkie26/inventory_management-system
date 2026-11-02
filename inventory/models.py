"""Domain values and in-memory delivery manifests. Prices always use Decimal."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from .errors import ValidationError

CENT = Decimal("0.01")
MAX_MONEY = Decimal("99999999999.99")
MAX_QUANTITY = 2_147_483_647


def money(value: Any, *, positive: bool = False) -> Decimal:
    try:
        amount = Decimal(str(value).strip())
        if not amount.is_finite() or amount < 0 or amount > MAX_MONEY:
            raise ValueError
        if amount != amount.quantize(CENT):
            raise ValidationError("Amounts may have at most two decimal places.")
        if positive and amount <= 0:
            raise ValidationError("The amount must be greater than zero.")
        return amount.quantize(CENT)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValidationError("Enter a valid, non-negative amount (up to 99,999,999,999.99).") from exc


def quantity(value: Any, *, allow_zero: bool = True) -> int:
    text = str(value).strip()
    if not text.isascii() or not text.isdigit() or len(text) > 10:
        raise ValidationError("Quantity must be a whole number.")
    result = int(text)
    if result < (0 if allow_zero else 1) or result > MAX_QUANTITY:
        raise ValidationError(f"Quantity must be between {0 if allow_zero else 1:,} and {MAX_QUANTITY:,}.")
    return result


def currency(value: Any) -> str:
    return f"${Decimal(str(value)):,.2f}"


@dataclass(frozen=True)
class User:
    user_id: int
    username: str
    email: str
    role: str
    balance: Decimal
    active: bool = True

    @classmethod
    def from_row(cls, row: dict) -> "User":
        return cls(*(row[key] for key in ("user_id", "username", "email", "role", "balance", "active")))


@dataclass(frozen=True)
class Product:
    product_id: int
    name: str
    description: str
    quantity: int
    price: Decimal
    category: str
    active: bool = True
    version: int = 1
    reserved: int = 0

    @property
    def available(self) -> int:
        return self.quantity - self.reserved

    @classmethod
    def from_row(cls, row: dict) -> "Product":
        return cls(*(row[key] for key in ("product_id", "name", "description", "quantity", "price", "category", "active", "version")), reserved=int(row.get("reserved", 0)))


@dataclass(frozen=True)
class ManifestItem:
    product: Product
    quantity: int

    @property
    def total(self) -> Decimal:
        return self.product.price * self.quantity


class Manifest:
    def __init__(self) -> None:
        self._items: dict[int, ManifestItem] = {}

    @property
    def items(self) -> tuple[ManifestItem, ...]:
        return tuple(self._items.values())

    @property
    def total(self) -> Decimal:
        return sum((item.total for item in self._items.values()), Decimal("0.00"))

    def add(self, product: Product, count: Any) -> None:
        requested = quantity(count, allow_zero=False)
        existing = self._items.get(product.product_id)
        combined = requested + (existing.quantity if existing else 0)
        if not product.active or combined > product.available:
            raise ValidationError(f"Only {product.available:,} units of {product.name} are available, including units already in this delivery.")
        if existing and existing.product.price != product.price:
            raise ValidationError(f"The price of {product.name} has changed. Remove it from this delivery and add it again.")
        money(self.total - (existing.total if existing else 0) + product.price * combined)
        self._items[product.product_id] = ManifestItem(product, combined)

    def remove(self, product_id: int) -> None:
        self._items.pop(product_id, None)

    def clear(self) -> None:
        self._items.clear()
