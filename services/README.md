# Services

systemd unit files for desktop/ISO installs.

- `nexusd.service`: starts the daemon at boot
- `nexus-guard.service`: security monitor

```bash
sudo cp services/*.service /etc/systemd/system/
sudo systemctl enable --now nexusd
```
Termux/proot has no systemd; use the CLI directly.
