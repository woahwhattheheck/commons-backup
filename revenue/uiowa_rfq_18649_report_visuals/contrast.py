"""WCAG 2.1 contrast arithmetic, implemented from the specification.

Why this module exists: "accessible" is a claim until something measures it.
Every colour this package ships is run through `audit_palette()` and the test
suite fails if a pair drops below its threshold. A designer changing a hex value
finds out from a red test, not from a reader who cannot read the chart.

Reference: WCAG 2.1, "relative luminance" and "contrast ratio" definitions.
    https://www.w3.org/TR/WCAG21/#dfn-relative-luminance
    https://www.w3.org/TR/WCAG21/#dfn-contrast-ratio

Thresholds used here (we deliberately do NOT take the large-text exemption --
report figures get resized, printed and projected, so 3:1 body text is a bad
bet):
    TEXT_MIN        4.5:1  text of any size against its own background
    GRAPHICAL_MIN   3.0:1  borders, marks, hatch strokes, axis rules
    DISTINCT_MIN    3.0:1  two fills that a reader must tell apart *after*
                           colour has been removed

Python 3 standard library only.
"""

from __future__ import annotations

TEXT_MIN = 4.5
GRAPHICAL_MIN = 3.0
DISTINCT_MIN = 3.0

# Coefficients from the WCAG relative-luminance definition.
_LUM_R = 0.2126
_LUM_G = 0.7152
_LUM_B = 0.0722


class ColorError(ValueError):
    """Raised for a hex string this module refuses to guess at."""


def parse_hex(value: str) -> tuple[int, int, int]:
    """'#1A2B3C' or '#abc' -> (r, g, b) in 0..255. Strict on purpose."""
    if not isinstance(value, str):
        raise ColorError(f"colour must be a string, got {type(value).__name__}")
    s = value.strip()
    if not s.startswith("#"):
        raise ColorError(f"colour must start with '#': {value!r}")
    body = s[1:]
    if len(body) == 3:
        body = "".join(ch * 2 for ch in body)
    if len(body) != 6:
        raise ColorError(f"colour must be #rgb or #rrggbb: {value!r}")
    try:
        r = int(body[0:2], 16)
        g = int(body[2:4], 16)
        b = int(body[4:6], 16)
    except ValueError as exc:  # non-hex characters
        raise ColorError(f"not a hex colour: {value!r}") from exc
    return r, g, b


def to_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = (max(0, min(255, int(round(c)))) for c in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


def _channel_to_linear(c8: int) -> float:
    """sRGB 8-bit channel -> linear-light value, per WCAG."""
    c = c8 / 255.0
    if c <= 0.03928:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def _linear_to_channel(lin: float) -> float:
    """Inverse of `_channel_to_linear`, back to an 8-bit sRGB channel."""
    lin = max(0.0, min(1.0, lin))
    if lin <= 0.0031308:
        c = lin * 12.92
    else:
        c = 1.055 * (lin ** (1 / 2.4)) - 0.055
    return c * 255.0


def relative_luminance(color: str) -> float:
    """WCAG relative luminance, 0.0 (black) .. 1.0 (white)."""
    r, g, b = parse_hex(color)
    return (
        _LUM_R * _channel_to_linear(r)
        + _LUM_G * _channel_to_linear(g)
        + _LUM_B * _channel_to_linear(b)
    )


def contrast_ratio(a: str, b: str) -> float:
    """WCAG contrast ratio between two colours. 1.0 .. 21.0, order-independent."""
    la = relative_luminance(a)
    lb = relative_luminance(b)
    lighter, darker = (la, lb) if la >= lb else (lb, la)
    return (lighter + 0.05) / (darker + 0.05)


def to_grayscale(color: str) -> str:
    """Luminance-preserving grayscale.

    This is the "what a monochrome printer / a fully colour-blind reader gets"
    transform: keep the measured relative luminance, throw the hue away. It is
    the transform the unassessed-vs-low-rating test runs through, because that
    is exactly the situation the RFQ's completion condition is about.
    """
    lum = relative_luminance(color)
    channel = _linear_to_channel(lum)
    return to_hex((channel, channel, channel))


def grayscale_contrast(a: str, b: str) -> float:
    """Contrast ratio between two colours after colour has been removed."""
    return contrast_ratio(to_grayscale(a), to_grayscale(b))


def readable_ink(background: str, candidates: tuple[str, ...] = ("#000000", "#FFFFFF")) -> str:
    """Pick whichever candidate ink has the most contrast on `background`.

    Used to keep in-swatch text legible without a human eyeballing it.
    """
    return max(candidates, key=lambda ink: contrast_ratio(ink, background))


class CheckResult:
    """One measured pair. `ok` is computed, never asserted by hand."""

    __slots__ = ("name", "kind", "foreground", "background", "ratio", "minimum")

    def __init__(self, name: str, kind: str, foreground: str, background: str,
                 ratio: float, minimum: float) -> None:
        self.name = name
        self.kind = kind
        self.foreground = foreground
        self.background = background
        self.ratio = ratio
        self.minimum = minimum

    @property
    def ok(self) -> bool:
        # Compare the measured ratio, not its rounded display value.
        # W3C SC 1.4.3: 4.499 must not become a 4.5 threshold pass.
        return self.ratio >= self.minimum

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "foreground": self.foreground,
            "background": self.background,
            "ratio": round(self.ratio, 2),
            "minimum": self.minimum,
            "ok": self.ok,
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        flag = "PASS" if self.ok else "FAIL"
        return f"<{flag} {self.name} {self.ratio:.2f}:1 (min {self.minimum})>"


def check(name: str, kind: str, foreground: str, background: str, minimum: float) -> CheckResult:
    return CheckResult(name, kind, foreground, background,
                       contrast_ratio(foreground, background), minimum)


def check_grayscale(name: str, foreground: str, background: str,
                    minimum: float = DISTINCT_MIN) -> CheckResult:
    """Same as `check`, but measured after the colour is stripped out."""
    return CheckResult(name, "grayscale-distinct", foreground, background,
                       grayscale_contrast(foreground, background), minimum)


def format_report(results: list[CheckResult]) -> str:
    """Plain-text audit table. Printed by the CLI so the numbers are on record."""
    if not results:
        return "(no checks)"
    width = max(len(r.name) for r in results)
    lines = [
        f"{'check'.ljust(width)}  {'kind':<18} {'fg':<9} {'bg':<9} {'ratio':>7} {'min':>5}  result",
        "-" * (width + 62),
    ]
    for r in results:
        lines.append(
            f"{r.name.ljust(width)}  {r.kind:<18} {r.foreground:<9} {r.background:<9} "
            f"{r.ratio:>6.2f}:1 {r.minimum:>5.1f}  {'PASS' if r.ok else 'FAIL'}"
        )
    failed = [r for r in results if not r.ok]
    lines.append("-" * (width + 62))
    lines.append(f"{len(results)} checks, {len(results) - len(failed)} pass, {len(failed)} fail")
    return "\n".join(lines)
