"""Base exception for everything mulebox raises on purpose.

Each concern defines its own subclass in its own module (ConfigError in config.py,
ProtocolError in protocol.py, ...), so callers can catch one concern or all of them.
"""


class MuleboxError(Exception):
    """Base class for expected, user-reportable mulebox errors."""
