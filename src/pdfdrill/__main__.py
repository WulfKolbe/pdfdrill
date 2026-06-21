"""Allow running as: python -m pdfdrill"""
import sys

from .cli import main

# Propagate the exit code — main() returns 1 on error. Without sys.exit() the
# process always exited 0, so callers (drillui's subprocess, CI) couldn't tell
# success from failure (a failed `model` looked like it built a document).
sys.exit(main())
