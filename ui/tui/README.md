# TUI (Terminal User Interface) - Phase 3

A full-featured terminal console for Nexus AIOS built with `rich`. Works seamlessly over SSH, serial consoles, and Android Termux/proot without requiring X11 or a desktop display.

## Features

- **Interactive Intent Console**: Natural language prompt with live planning, tool execution output, and security confirmation dialogs.
- **Security Guard Telemetry**: Real-time system resource watchdog (CPU/RAM/Disk bounds) and proactive tripwire/anomaly alerts.
- **Autonomous Task Scheduler**: Inspect, toggle, trigger, and create scheduled maintenance and recurring intent jobs.
- **Tools Catalog Explorer**: Searchable directory of registered system, file, and network tools with parameter schemas.
- **Persistent Memory Manager**: Key-value facts and preference manager with relevance search.
- **Cryptographic Audit Feed**: Real-time structured log stream.

## Launching the TUI

Make sure `nexusd` is running (`python -m nexusd.main` or via systemd), then run:

```bash
# Direct launch
python ui/tui/app.py

# Or via CLI flag
nexus --tui

# Custom host and port
python ui/tui/app.py --host 127.0.0.1 --port 8765
```

## Navigation Hotkeys

- `[1]`: Intent Console
- `[2]`: Security Guard & System Health
- `[3]`: Scheduler
- `[4]`: Tools Catalog
- `[5]`: Memory Store
- `[6]`: Audit Stream
- `[q]`: Quit
