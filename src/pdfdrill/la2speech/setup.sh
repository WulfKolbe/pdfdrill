#!/bin/sh
# One-time setup for latex2speech.
set -e
pip install -r requirements.txt

# npm resolves the install target by walking UP for a package.json. An empty
# sre/ has none, so a plain `npm install` here lands in the nearest ancestor
# that does -- typically $HOME, where a global tooling package.json lives.
# Seeding sre/package.json and passing --prefix . pins it to this directory.
mkdir -p sre
[ -f sre/package.json ] || echo '{"private":true}' > sre/package.json
npm install --prefix sre speech-rule-engine

echo "setup done -- now run: python3 test_latex2speech.py"
