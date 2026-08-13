# pdiiif Deployment Guide

## Quick Deployment to Production

### 1. Build and Push to Registry

The GitHub Actions workflow automatically builds and pushes images when you push to specific branches:

- **Staging**: Push to `staging` branch → `ghcr.io/leidenuniversitylibrary/pdiiif:staging`
- **Production**: Push to `production` branch → `ghcr.io/leidenuniversitylibrary/pdiiif:latest`

### 2. Update the Server

On your server (as the `podman` user):

```bash
# Stop the service
systemctl --user stop ubl-pdiiif.service

# Pull the latest image
podman pull ghcr.io/leidenuniversitylibrary/pdiiif:staging

# Remove the old container
podman rm -f ubl-pdiiif

# Start with the new image
systemctl --user start ubl-pdiiif.service

# Verify it's running
systemctl --user status ubl-pdiiif.service
curl -I http://localhost:8082
```

### 3. One-Line Update

```bash
systemctl --user stop ubl-pdiiif.service && \
podman pull ghcr.io/leidenuniversitylibrary/pdiiif:staging && \
podman rm -f ubl-pdiiif && \
systemctl --user start ubl-pdiiif.service
```

---

## Local Development

### Build Locally with Podman

```bash
# Build the image
podman build -t pdiiif:latest .

# Run with podman-compose
podman-compose up
```

### Run Development Server

```bash
# Install dependencies
pnpm install

# Start dev server
cd pdiiif-web
pnpm run dev
```

---

## Version Management

The application version is defined in `pdiiif-web/package.json` and displayed at the bottom of the web interface.

To update the version:

1. Edit `pdiiif-web/package.json`
2. Change the `"version"` field
3. Commit and push to trigger a new build

---

## Caddy Configuration

The application is accessible at `https://iiif-pdf-a.universiteitleiden.nl`

Caddyfile location: `/luci/data0/caddy/Caddyfile`

```caddy
iiif-pdf-a.universiteitleiden.nl {
    log
    tls /run/secrets/iiif-cert.pem /run/secrets/iiif-key.pem
    @pdiiif host iiif-pdf-a.universiteitleiden.nl
    reverse_proxy @pdiiif host.containers.internal:8082
}
```

After changing Caddyfile:
```bash
systemctl --user restart caddy.service
```

---

## Container Quadlet Location

**Server path**: `~/.config/containers/systemd/ubl-pdiiif.container`

After editing the quadlet:
```bash
systemctl --user daemon-reload
systemctl --user restart ubl-pdiiif.service
```

---

## Useful Commands

### Check logs
```bash
# Application logs
podman logs ubl-pdiiif -f

# Systemd service logs
journalctl --user -u ubl-pdiiif.service -f
```

### Check container status
```bash
podman ps | grep pdiiif
systemctl --user status ubl-pdiiif.service
```

### Check which image is running
```bash
podman inspect ubl-pdiiif | grep Image
```

### Force full rebuild on GitHub Actions
Push to your branch with an empty commit:
```bash
git commit --allow-empty -m "trigger rebuild"
git push
```

