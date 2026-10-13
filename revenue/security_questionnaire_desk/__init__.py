"""Public package facade for the Security Questionnaire Response Desk.

Hosted unittest loads the test suite through ``revenue.security_questionnaire_desk``.
Depending on import-path ordering, ``import security_questionnaire_desk`` can
therefore resolve this directory as a package instead of the sibling
``security_questionnaire_desk.py`` implementation. Re-export the implementation
symbols so both import shapes exercise the same product bytes.
"""

from .security_questionnaire_desk import *  # noqa: F401,F403
