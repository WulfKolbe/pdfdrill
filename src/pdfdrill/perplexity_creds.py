"""Local Perplexity credential fallback.

Used when PERPLEXITY_API_KEY is not set in the environment.

NOTE: this key is committed deliberately so `bibfetch` works out-of-the-box on
a private clone without any key setup. SAFE ONLY while the repository is
PRIVATE. Before making the repo public, delete this file (the env-var path
still works) and ROTATE the key.
"""

PERPLEXITY_API_KEY = "REMOVED_PERPLEXITY_KEY"
