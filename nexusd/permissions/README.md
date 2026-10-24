# Permissions

Decides whether an AI action is allowed.

- `engine.py`: checks each action against policy
- `policy.yaml`: rules

## Levels
- `allow`: runs silently (read-only actions)
- `confirm`: asks the user first (delete, install, network)
- `deny`: never runs (format disk, edit bootloader)

## Example
```yaml
files.read: allow
files.delete: confirm
system.format: deny
```
