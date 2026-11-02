"""The four employee roles and the capabilities shared by the UI and services."""

ADMIN = "admin"
INVENTORY_WORKER = "inventory_worker"
STOCK_CHECKER = "stock_checker"
DELIVERY_ASSISTANT = "delivery_assistant"

ROLE_LABELS = {
    INVENTORY_WORKER: "Inventory worker",
    STOCK_CHECKER: "Stock checker",
    DELIVERY_ASSISTANT: "Truck delivery assistant",
    ADMIN: "Admin",
}
ALL_ROLES = frozenset(ROLE_LABELS)
INVENTORY_ROLES = frozenset({ADMIN, INVENTORY_WORKER})
STOCK_ROLES = frozenset({ADMIN, STOCK_CHECKER})
DELIVERY_STATUS_LABELS = {
    "assigned": "Assigned",
    "in_transit": "In transit",
    "delivered": "Delivered",
    "cancelled": "Cancelled",
}
ORDER_STATUS_LABELS = {
    "pending_delivery": "Pending delivery",
    "in_transit": "In transit",
    "completed": "Completed",
    "cancelled": "Cancelled",
}
