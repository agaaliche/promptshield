"""Detection package."""


def __getattr__(name: str):
    """Lazy re-export so that ``from core.detection import detect_pii_on_page``
    still works without pulling heavy dependencies (spacy, etc.) at import time."""
    if name == "detect_pii_on_page":
        from core.detection.pipeline import detect_pii_on_page  # noqa: F811
        return detect_pii_on_page
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
