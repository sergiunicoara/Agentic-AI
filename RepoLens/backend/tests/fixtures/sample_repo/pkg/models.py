"""Domain models for the sample package."""

DEFAULT_TIMEOUT = 30


class User:
    """Represents a user record."""

    def __init__(self, name: str, email: str) -> None:
        self.name = name
        self.email = email

    def display_name(self) -> str:
        """Return a human-friendly display name."""
        return f"{self.name} <{self.email}>"


def create_user(name: str, email: str) -> User:
    """Factory function for building a User."""
    return User(name=name, email=email)
