"""Compatibility facade for the hardened UNC AP/PeopleSoft compiler."""

try:
    from . import unc_ap_ai_v2 as _impl
except ImportError:
    import unc_ap_ai_v2 as _impl

globals().update({name: getattr(_impl, name) for name in _impl.__all__})
__all__ = list(_impl.__all__)
