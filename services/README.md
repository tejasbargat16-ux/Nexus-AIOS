# Services (Phase 3)

Systemd unit files and service management for desktop and ISO installs.

- `nexusd.service`: Autonomous daemon kernel started on boot with automatic restart and journal logging.
- `nexus-guard.service`: Real-time proactive security guard, tripwire watchdog, and anomaly detector.
- `install-services.sh`: Automated service installer and systemd configuration script.

## Quick Install (Desktop Linux / ISO)

```bash
sudo bash services/install-services.sh
```

Or manually:
```bash
sudo cp services/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now nexusd
sudo systemctl enable --now nexus-guard
```

## Service Control

```bash
# Check daemon status
sudo systemctl status nexusd

# Check security guard status
sudo systemctl status nexus-guard

# Tail daemon logs
journalctl -u nexusd -f
```

*Note: Android Termux/proot environments do not use systemd; use the CLI (`nexus`) or daemon runner (`python -m nexusd.main`) directly.*
