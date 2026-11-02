"""Errors that can be shown to the user without exposing database credentials."""


class InventoryError(Exception):
    pass


class ValidationError(InventoryError):
    pass


class AuthenticationError(InventoryError):
    pass


class PermissionDenied(InventoryError):
    pass


class DatabaseError(InventoryError):
    pass
