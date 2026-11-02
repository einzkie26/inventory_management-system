"""Order receipts and product manifests exported independently of database writes."""

import os
from pathlib import Path
import tempfile

from .models import currency
from .roles import DELIVERY_STATUS_LABELS, ORDER_STATUS_LABELS


def render_receipt(order: dict) -> str:
    lines = [
        "INVENTORY | ORDER RECEIPT", "=" * 52,
        f"Order: #{order['order_id']}", f"Recipient: {order['recipient']}",
        f"Created by: {order['username']}", f"Status: {ORDER_STATUS_LABELS[order['status']]}",
        f"Date: {order['order_date']}", "", "Items", "-" * 52,
    ]
    for item in order["items"]:
        lines.append(f"{item['product_name']} (x{item['quantity']})")
        lines.append(f"  Unit price: {currency(item['unit_price'])}   Total: {currency(item['price'])}")
    lines += ["-" * 52, f"TOTAL: {currency(order['total_price'])}", ""]
    return "\n".join(lines)


def export_receipt(order: dict, directory: Path) -> Path:
    return _export_text(render_receipt(order), directory, f"receipt_{int(order['order_id'])}.txt")


def render_manifest(delivery: dict) -> str:
    lines = [
        "INVENTORY | DELIVERY MANIFEST", "=" * 52,
        f"Delivery: #{delivery['delivery_id']}", f"Order: #{delivery['order_id']}",
        f"Assistant: {delivery['assistant_name']}",
        f"Recipient: {delivery['recipient']}", f"Destination: {delivery['destination']}",
        f"Status: {DELIVERY_STATUS_LABELS[delivery['status']]}",
        f"Assigned: {delivery['assigned_at']}", f"Picked up: {delivery['picked_up_at'] or '—'}",
        f"Delivered: {delivery['delivered_at'] or '—'}", "", "Products", "-" * 52,
    ]
    for item in delivery["items"]:
        lines.append(f"- {item['product_name']} | {item['category']} | Quantity: {item['quantity']:,}")
    lines += ["", f"Notes: {delivery['notes'] or '—'}", "", "History", "-" * 52]
    for event in delivery["events"]:
        lines.append(f"{event['created_at']} | {event['actor_name']} | {event['notes']}")
    return "\n".join(lines) + "\n"


def export_manifest(delivery: dict, directory: Path) -> Path:
    return _export_text(render_manifest(delivery), directory, f"delivery_{int(delivery['delivery_id'])}.txt")


def _export_text(text: str, directory: Path, filename: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / filename
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=directory, prefix="receipt_", suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
            output.write(text)
        os.replace(temporary, target)
        return target
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
