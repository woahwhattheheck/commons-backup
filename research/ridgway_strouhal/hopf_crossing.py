"""Abstract planar Hopf bookkeeping. Not Navier-Stokes. Not the cylinder."""

from __future__ import annotations


def linearization(re: float, re_c: float = 47.0, omega: float = 1.0) -> tuple[complex, complex]:
    """Eigenvalues of the normal-form linearization.
    mu = (re - re_c) / re_c.
    """
    mu = (re - re_c) / re_c
    lam = complex(mu, omega)
    return lam, complex(mu, -omega)


def crossing_speed(re_c: float = 47.0) -> float:
    return 1.0 / re_c


def is_simple_imaginary_crossing(re_c: float = 47.0, omega: float = 1.0) -> bool:
    left = linearization(re_c - 1e-6, re_c, omega)
    mid = linearization(re_c, re_c, omega)
    right = linearization(re_c + 1e-6, re_c, omega)
    if abs(mid[0].real) > 1e-12:
        return False
    if mid[0].imag <= 0:
        return False
    if left[0].real >= 0 or right[0].real <= 0:
        return False
    if crossing_speed(re_c) <= 0:
        return False
    return True


def exclude_steady_as_prize_object(velocity_is_time_independent: bool) -> bool:
    """Sponsor excludes constant-in-time solutions even though they are periodic."""
    return not velocity_is_time_independent


def truncated_channel_is_prize_domain() -> bool:
    return False
