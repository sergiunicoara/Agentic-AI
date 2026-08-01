from dataclasses import dataclass


@router.get("/users")  # noqa: F821 - parser-only FastAPI decorator fixture
async def list_users():
    return []


@dataclass
class User:
    id: int
    def display(self):
        return self.id

    DEFAULT_ROLE = "user"


AFTER_DEFINITIONS = True
