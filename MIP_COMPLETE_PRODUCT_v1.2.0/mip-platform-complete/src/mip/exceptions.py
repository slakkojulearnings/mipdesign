class MIPError(Exception):
    """Base MIP exception."""


class SourceReadError(MIPError):
    """Raised when a source file cannot be decoded or read."""


class DatabaseError(MIPError):
    """Raised for persistence failures."""


class AssetNotFoundError(MIPError):
    """Raised when an asset cannot be found."""
