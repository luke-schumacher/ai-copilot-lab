"""
claimcheck: the claim checker and the synthetic session generator.

Everything here runs on a laptop with no network, no database and no model
server. `ingest/` reads logger files, `check/` is the claim check, `web/` is
the local page, `synth.py` writes synthetic sessions with planted mistakes.
"""

__version__ = "0.1.0"
