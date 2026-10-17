"""List the models the configured endpoint offers, so GEMMA_MODEL can be set exactly."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from goa import llm  # noqa: E402

try:
    ids = llm.list_models()
except llm.LLMConfigError as e:
    print(e, file=sys.stderr)
    sys.exit(2)
for i in ids:
    print(i)
gemma = [i for i in ids if "gemma" in i.lower()]
print(f"\n{len(ids)} models, gemma: {gemma or 'none found'}", file=sys.stderr)
