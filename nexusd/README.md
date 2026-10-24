# nexusd

The core Nexus daemon. Receives user intent, asks the LLM to plan, runs approved tools, stores memory.

## Files
- `main.py`: daemon entry point
- `router.py`: picks local or cloud model
- `config.py`: loads `config/nexus.yaml`
- `api.py`: local HTTP API (Flask/FastAPI)
- `scheduler.py`: resource prioritisation (Phase 3)
- `security.py`: process/network guard (Phase 3)
- `audit.py`: action log

## Run
```bash
python3 -m nexusd.main
```

## API (planned)
- `POST /intent` : send a natural-language request
- `GET /status` : daemon health
- `GET /audit` : recent actions
