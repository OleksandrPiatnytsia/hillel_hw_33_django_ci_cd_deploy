"""The version of the site, shown in the footer of every page.

Two parts:
- __version__: written by hand, MAJOR.MINOR.PATCH (semantic versioning).
  Raised once per release (a pull request to main), not per commit:
    PATCH (1.0.0 -> 1.0.1): a fix, nothing new for the user;
    MINOR (1.0.0 -> 1.1.0): a new feature (book formats; 1.1.0 -> 1.4.0:
        the wishlist, the rating, the book page and the navbar; 1.5.0: the
        events for Analytics);
    MAJOR (1.0.0 -> 2.0.0): a change that breaks the old (API clients).
- the commit: comes by itself, nobody has to remember it. Railway gives
  every deploy from GitHub the variable RAILWAY_GIT_COMMIT_SHA; elsewhere
  it can be set as APP_COMMIT. No variable (local Docker, runserver) -> no
  commit, only the version.

The commit in the footer answers "is the new code deployed?": it changes
with every push to main, even when __version__ stays the same.
"""

import os

__version__ = "1.5.0"


def deployed_commit():
    """The full SHA of the deployed commit, or "" when it is unknown."""
    return os.getenv("RAILWAY_GIT_COMMIT_SHA") or os.getenv("APP_COMMIT", "")
