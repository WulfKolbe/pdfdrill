"""Local MathPix credential fallback.

Used when MATHPIX_APP_ID / MATHPIX_APP_KEY are not set in the environment.

NOTE: these keys are committed deliberately so the toolchain works out-of-the-
box on a private clone (e.g. a Claude.ai sandbox) without any key setup. This
file is SAFE ONLY while the repository is PRIVATE. Before making the repo
public, delete this file (the env-var path still works) and ROTATE the keys.
"""

APP_ID = "REMOVED_MATHPIX_APP_ID"
APP_KEY = "REMOVED_MATHPIX_APP_KEY"
