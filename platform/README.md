# Platform adapters

Hides device differences so core code stays identical.

- `base.py`: abstract interface (battery, notifications, packages)
- `linux_desktop.py`: laptop/desktop/ISO
- `android_termux.py`: phone/tablet via Termux

Detection happens at startup based on environment.
