"""SCF licence attribution (CC BY-ND 4.0), shared by the About page and exports.

Keep ATTRIBUTION in step with data/requirements/scf.json (a test checks this).
"""

from __future__ import annotations

LICENCE_NAME = (
    "Creative Commons Attribution-NoDerivatives 4.0 International Public License "
    "(CC BY-ND 4.0)"
)
LICENCE_URL = "https://creativecommons.org/licenses/by-nd/4.0/legalcode.en"
SCF_URL = "https://securecontrolsframework.com"
NO_CHANGES = "No changes have been made to the SCF content."

ATTRIBUTION = (
    "SFR (Shared Framework Repository) includes the Secure Controls Framework® (SCF) "
    "content, © Secure Controls Framework Council, LLC, used under the "
    f"{LICENCE_NAME} ({LICENCE_URL}). {NO_CHANGES} "
    f"Learn more at {SCF_URL}."
)


def oscal_licence_link() -> dict:
    """OSCAL metadata link pointing at the licence."""
    return {"href": LICENCE_URL, "rel": "license", "text": LICENCE_NAME}


def oscal_remarks() -> str:
    """Credit text for OSCAL metadata 'remarks'."""
    return ATTRIBUTION
