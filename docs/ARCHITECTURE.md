# Architecture

```
User -> CLI/TUI/Web -> nexusd API -> LLM Router
                                  -> Permission Engine -> Tools
                                  -> Memory (SQLite)
                                  -> Audit Log
```
Flow: intent -> LLM plans -> permission check -> tool runs -> result stored -> reply.
