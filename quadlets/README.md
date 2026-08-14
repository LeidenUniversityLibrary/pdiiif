# pdiiif – Podman Quadlets

This directory contains [Podman quadlet](https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html)
unit files that run **pdiiif as a rootless systemd service** (no root or Docker daemon required).

## Files

| File | Purpose |
|---|---|
| `pdiiif-default.network` | Bridge network shared by the container |
| `pdiiif-pdiiif.container` | The pdiiif application container |
| `generate_quadlets.py` | Script to regenerate the above from `../docker-compose.yml` |

---

## Quick start

### 1. Build the image

```bash
# From the repository root
podman build -t pdiiif:latest .
```

### 2. Install the quadlets

Rootless user units live in `~/.config/containers/systemd/`:

```bash
mkdir -p ~/.config/containers/systemd
cp pdiiif-default.network pdiiif-pdiiif.container ~/.config/containers/systemd/
```

### 3. Reload systemd and start

```bash
systemctl --user daemon-reload
systemctl --user start pdiiif-pdiiif.service
```

### 4. Enable on login / boot

```bash
# Start automatically when the user logs in (rootless)
systemctl --user enable pdiiif-pdiiif.service

# Or start at boot even without a login session (requires linger)
loginctl enable-linger $USER
```

### Check status / logs

```bash
systemctl --user status pdiiif-pdiiif.service
journalctl --user -u pdiiif-pdiiif.service -f
```

---

## Regenerating quadlets after compose changes

```bash
cd quadlets
python3 generate_quadlets.py ../docker-compose.yml --output . --user
```

### Override the image (e.g. from a registry)

```bash
python3 generate_quadlets.py ../docker-compose.yml --output . --user \
    --image-map "pdiiif=ghcr.io/yourorg/pdiiif:1.2.3"
```

### All options

```
usage: generate_quadlets.py [-h] [--output OUTPUT] [--base-dir BASE_DIR]
                             [--network-name NETWORK_NAME] [--prefix PREFIX]
                             [--env-file ENV_FILE] [--image-map IMAGE_MAP]
                             [--image-map-file IMAGE_MAP_FILE] [--tag TAG]
                             [--secrets SECRETS] [--secrets-map-file SECRETS_MAP_FILE]
                             [--user]
                             [compose]
```

---

## Notes

- `CAP_SYS_ADMIN` and `SeccompProfile=unconfined` are required for Playwright's headless
  Chromium sandbox (used for cover-page PDF generation).
- The image tag `localhost/pdiiif:latest` refers to a locally built image.
  Use `--image-map` to point to a registry image instead.
- The app listens on port **8082** by default (set via `CFG_PORT`).
  Edit `pdiiif-pdiiif.container` to change it, then reload and restart the unit.

