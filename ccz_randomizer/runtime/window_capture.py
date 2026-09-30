from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class CaptureResult:
    image: object
    method: str
    previous_errors: tuple[str, ...]
    recovered: bool


class WindowCaptureError(RuntimeError):
    def __init__(self, errors: list[str]):
        super().__init__("all background window capture methods failed")
        self.errors = tuple(errors)


def _capture_error(method: str, exc: Exception) -> str:
    return f"{method}:{type(exc).__name__}:{exc}"


def capture_window_with_fallbacks(
    *,
    print_window: Callable[[int], object],
    bitblt: Callable[[], object],
    wake: Callable[[], None],
    is_usable: Callable[[object, bool], bool],
    sleep_after_wake: Callable[[], None],
) -> CaptureResult:
    """Capture a hidden window using ordered strategies and one wake retry."""
    errors: list[str] = []

    def attempt(
        method: str,
        capture: Callable[[], object],
        *,
        require_variance: bool = True,
        recovered: bool = False,
    ) -> CaptureResult | None:
        try:
            image = capture()
        except Exception as exc:
            errors.append(_capture_error(method, exc))
            return None
        if not is_usable(image, require_variance):
            state = "empty" if image is None or not getattr(image, "size", 0) else "blank"
            errors.append(f"{method}:{state}")
            return None
        return CaptureResult(
            image=image,
            method=method,
            previous_errors=tuple(errors),
            recovered=recovered,
        )

    for flags, method in ((2, "print_window_full"), (0, "print_window")):
        result = attempt(method, lambda flags=flags: print_window(flags))
        if result is not None:
            return result

    result = attempt(
        "bitblt",
        bitblt,
        require_variance=False,
    )
    if result is not None:
        return result

    try:
        wake()
        sleep_after_wake()
    except Exception as exc:
        errors.append(_capture_error("wake", exc))

    for flags, method in (
        (0, "print_window_after_wake"),
        (2, "print_window_full_after_wake"),
    ):
        result = attempt(
            method,
            lambda flags=flags: print_window(flags),
            recovered=True,
        )
        if result is not None:
            return result

    raise WindowCaptureError(errors)
