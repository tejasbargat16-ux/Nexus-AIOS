# Build

Creates bootable images.

- `Dockerfile`: reproducible build environment
- `build.sh`: main build script
- `packages.list`: packages baked into the image
- `live-build/`: Debian live-build config and hooks

Heavy builds run on GitHub Actions (`.github/workflows/build-multiarch.yml`), not on the phone. Output goes to `out/`.
