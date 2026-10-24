# Tools

The AI's safe "hands". Each tool is a small Python module exposing functions the LLM can call.

| Module | Purpose |
|---|---|
| `files.py` | read, search, move, zip files |
| `apps.py` | launch and close apps |
| `network.py` | connectivity, downloads, mail |
| `packages.py` | install and update packages |

## Rules
- One function = one clear action
- Return structured results (dict/JSON)
- Declare permission level in `permissions/policy.yaml`
- Never run shell input from the model without validation
