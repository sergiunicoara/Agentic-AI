"""
Target C1 — Clean control target.
No security issues. Sentinel should return 'pass' verdict.
"""


def process_data(data: list[str]) -> list[str]:
    """Process a list of strings safely."""
    return [item.strip().lower() for item in data if isinstance(item, str)]


def calculate_score(values: list[float]) -> float:
    """Calculate average score safely."""
    if not values:
        return 0.0
    return sum(values) / len(values)