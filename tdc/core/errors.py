"""Application-wide exception types."""


class TDCError(Exception):
    """Base class for all application errors."""


class ConfigValidationError(TDCError):
    """A configuration value failed validation.

    ``errors`` maps field name -> human readable message.
    """

    def __init__(self, section: str, errors: dict[str, str]):
        self.section = section
        self.errors = dict(errors)
        detail = "; ".join(f"{k}: {v}" for k, v in self.errors.items())
        super().__init__(f"Invalid {section} settings: {detail}")


class DatabaseError(TDCError):
    """Database could not be opened, migrated or written."""


class ValidationError(TDCError):
    """Generic input validation failure for repository objects."""
