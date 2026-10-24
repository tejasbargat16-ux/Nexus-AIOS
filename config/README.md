# Config

- `nexus.yaml`: main settings

## Keys
```yaml
model:
  local_path: ~/models/model.gguf
  cloud_provider: claude
router:
  prefer: local
api:
  host: 127.0.0.1
  port: 8765
```
API keys go in environment variables (`NEXUS_API_KEY`), not in this file.
