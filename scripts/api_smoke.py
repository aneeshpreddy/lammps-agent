"""API smoke test (plan Day 23): one tiny call with the model of config.yaml; prints the reply and the usage.

  export ANTHROPIC_API_KEY=...   (never written to a file)
  python scripts/api_smoke.py

Costs a fraction of a cent. Run it once before the first scored run.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import anthropic  # noqa: E402

from agents.baseline import EFFORT, MODEL  # noqa: E402

try:
    resp = anthropic.Anthropic().messages.create(
        model=MODEL, max_tokens=1024, output_config={"effort": "low"},
        messages=[{"role": "user", "content": "Reply with the single word: ready"}])
except anthropic.AuthenticationError:
    sys.exit("Invalid credentials: check the ANTHROPIC_API_KEY set in this terminal.")
except TypeError as e:
    if "authentication method" not in str(e):
        raise
    sys.exit("No credentials: set ANTHROPIC_API_KEY in this terminal (see docs/BASELINE.md).")
except anthropic.APIStatusError as e:
    sys.exit(f"API error {e.status_code}: {e.message}")
except anthropic.APIConnectionError as e:
    sys.exit(f"Could not reach the API: {e}")
text = "".join(b.text for b in resp.content if b.type == "text")
print(f"model {resp.model} (config: {MODEL}, baseline effort {EFFORT}) · stop_reason {resp.stop_reason} · reply {text!r}")
print(f"usage: {resp.usage.input_tokens} input, {resp.usage.output_tokens} output tokens")
