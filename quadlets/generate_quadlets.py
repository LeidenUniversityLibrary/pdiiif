#!/usr/bin/env python3
"""
Generate Podman quadlets (.container / .network / .volume) from a docker-compose YAML.

pdiiif-aware features:
- Reads ALL networks from the compose file and generates .network quadlets.
- Maps the compose implicit `default` network to --network-name (default: pdiiif-default).
- Handles inline `environment:` → Environment= directives with ${VAR:-default} substitution.
- Handles `cap_add:` → AddCapability= directives.
- Handles `security_opt: seccomp=unconfined` → SeccompProfile=unconfined.
- Detects `restart: "no"` to emit Type=oneshot / RemainAfterExit=yes.
- Translates relative volume/env paths (./...) to absolute paths via --base-dir.
- Accepts --image-map / --image-map-file to override images for locally-built services.
- Services with only a `build:` stanza (no pre-built image) default to
  localhost/<service>:latest and print a reminder to build first.

Usage examples:
  # Minimal deployment (rootless user units):
  python3 generate_quadlets.py ../docker-compose.yml --output . --user

  # Override image for the pdiiif service (e.g. after pushing to a registry):
  python3 generate_quadlets.py ../docker-compose.yml --output . --user \\
      --image-map "pdiiif=ghcr.io/yourorg/pdiiif:latest"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_NETWORK_NAME = "pdiiif-default"
DEFAULT_BASE_DIR = "%h/pdiiif"
APP_PREFIX = "pdiiif"


# ---------------------------------------------------------------------------
# Image resolution helpers
# ---------------------------------------------------------------------------

def load_image_map(args) -> Dict[str, str]:
    img_map: Dict[str, str] = {}
    if args.image_map_file:
        p = Path(args.image_map_file)
        if not p.exists():
            raise SystemExit(f"image-map-file {p} not found")
        data = json.loads(p.read_text())
        if not isinstance(data, dict):
            raise SystemExit("image-map-file must be a JSON object {service: image:tag}")
        img_map.update({k: str(v) for k, v in data.items()})
    if args.image_map:
        for entry in args.image_map:
            if "=" not in entry:
                raise SystemExit(f"bad --image-map entry: {entry!r}  (expected service=image:tag)")
            svc, img = entry.split("=", 1)
            img_map[svc.strip()] = img.strip()
    return img_map


def resolve_image(name: str, svc: Dict[str, Any],
                  image_map: Dict[str, str], tag_override: Optional[str]) -> str:
    if name in image_map:
        img = image_map[name]
        print(f"  [override] {name} -> {img}", file=sys.stderr)
        return img
    if "build" in svc and svc["build"]:
        build_cfg = svc["build"]
        if isinstance(build_cfg, dict):
            tags = build_cfg.get("tags", [])
            if tags:
                base = tags[0]
                if tag_override and ":" in base:
                    base = f"{base.rsplit(':', 1)[0]}:{tag_override}"
                print(f"  [build-tag] {name} -> {base}", file=sys.stderr)
                return base
        placeholder = f"localhost/{name}:latest"
        print(
            f"  [warning] {name} has build: but no tags - using {placeholder}\n"
            f"            Run 'podman build -t {name}:latest .' before starting the unit.",
            file=sys.stderr,
        )
        return placeholder
    if "image" in svc and svc["image"]:
        return svc["image"]
    placeholder = f"localhost/{name}:latest"
    print(f"  [warning] no image for {name}, using {placeholder}", file=sys.stderr)
    return placeholder


# ---------------------------------------------------------------------------
# Environment variable loading & substitution
# ---------------------------------------------------------------------------

def load_env_vars(path_str: str) -> Dict[str, str]:
    env: Dict[str, str] = {}
    p = Path(path_str.replace("%h", str(Path.home())))
    if not p.exists():
        return env
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def expand_shell_defaults(text: str, env_vars: Dict[str, str]) -> str:
    def _sub_with_default(m: re.Match) -> str:
        return env_vars.get(m.group(1), m.group(2))

    def _sub_plain(m: re.Match) -> str:
        return env_vars.get(m.group(1), m.group(0))

    text = re.sub(r'\$\{([^}:]+):-([^}]*)\}', _sub_with_default, text)
    text = re.sub(r'\$\{([^}]+)\}', _sub_plain, text)
    return text


# ---------------------------------------------------------------------------
# Path translation helpers
# ---------------------------------------------------------------------------

def translate_path(path: str, base_dir: str) -> str:
    if path.startswith("./"):
        return f"{base_dir}/{path[2:]}"
    if path.startswith("~"):
        return f"%h{path[1:]}"
    return path


def translate_volume_mount(mount: str, base_dir: str) -> str:
    parts = mount.split(":")
    parts[0] = translate_path(parts[0], base_dir)
    return ":".join(parts)


# ---------------------------------------------------------------------------
# Inline environment -> Environment= directives
# ---------------------------------------------------------------------------

def format_inline_environment(env: Any, env_vars: Dict[str, str]) -> List[str]:
    lines: List[str] = []
    if isinstance(env, dict):
        for key, value in env.items():
            if value is None:
                continue
            expanded = expand_shell_defaults(str(value), env_vars)
            lines.append(f"Environment={key}={expanded}")
    elif isinstance(env, list):
        for item in env:
            if "=" in item:
                key, _, value = item.partition("=")
                expanded = expand_shell_defaults(value, env_vars)
                lines.append(f"Environment={key}={expanded}")
            else:
                lines.append(f"Environment={item}={env_vars.get(item, '')}")
    return lines


# ---------------------------------------------------------------------------
# Command / Exec formatting
# ---------------------------------------------------------------------------

def format_exec(command: Any, env_vars: Dict[str, str]) -> str:
    if isinstance(command, list):
        parts = [str(c) for c in command]
        command = " ".join(parts)
    command = str(command).replace("$$", "$")
    command = expand_shell_defaults(command, env_vars)
    return re.sub(r"\s+", " ", command).strip()


# ---------------------------------------------------------------------------
# Entrypoint formatting
# ---------------------------------------------------------------------------

def format_entrypoint(entrypoint: Any) -> str:
    if isinstance(entrypoint, list):
        if not entrypoint or entrypoint == [""]:
            return ""
        parts = [p.replace("$$", "$") for p in (str(c) for c in entrypoint)]
        return parts[0] if len(parts) == 1 else json.dumps(parts)
    return str(entrypoint).replace("$$", "$")


# ---------------------------------------------------------------------------
# Network helpers
# ---------------------------------------------------------------------------

def get_service_networks(svc: Dict[str, Any], primary_network: str) -> List[str]:
    raw = svc.get("networks", None)
    if raw is None:
        return [primary_network]
    names = list(raw.keys()) if isinstance(raw, dict) else list(raw)
    mapped = [primary_network if n == "default" else n for n in names]
    seen: set = set()
    return [n for n in mapped if not (n in seen or seen.add(n))]  # type: ignore[func-returns-value]


_PULL_MAP = {
    "always": "always",
    "missing": "missing",
    "if_not_present": "missing",
    "never": "never",
}


# ---------------------------------------------------------------------------
# cap_add -> AddCapability= directives
# ---------------------------------------------------------------------------

def format_cap_add(cap_add: Any) -> List[str]:
    if not cap_add:
        return []
    caps = [cap_add] if isinstance(cap_add, str) else list(cap_add)
    lines = []
    for cap in caps:
        cap = str(cap).strip().upper()
        if not cap.startswith("CAP_"):
            cap = f"CAP_{cap}"
        lines.append(f"AddCapability={cap}")
    return lines


# ---------------------------------------------------------------------------
# security_opt -> quadlet Security directives
# ---------------------------------------------------------------------------

def format_security_opt(security_opt: Any) -> List[str]:
    if not security_opt:
        return []
    opts = [security_opt] if isinstance(security_opt, str) else list(security_opt)
    lines = []
    for opt in opts:
        opt = str(opt).strip()
        if opt.lower().startswith("seccomp="):
            profile = opt.split("=", 1)[1]
            lines.append(f"SeccompProfile={profile}")
        elif opt.lower() == "no-new-privileges":
            lines.append("NoNewPrivileges=true")
        elif opt.lower().startswith("label="):
            label_val = opt.split("=", 1)[1]
            if label_val.lower() == "disable":
                lines.append("SecurityLabelDisable=true")
            else:
                lines.append(f"SecurityLabelLevel={label_val}")
        else:
            lines.append(f"# security_opt not mapped: {opt}")
    return lines


# ---------------------------------------------------------------------------
# Core quadlet generator
# ---------------------------------------------------------------------------

def service_to_quadlet(
    name: str,
    svc: Dict[str, Any],
    image_map: Dict[str, str],
    base_dir: str,
    primary_network: str,
    env_vars: Dict[str, str],
    tag_override: Optional[str] = None,
    secrets: Optional[List[str]] = None,
    wanted_by: str = "default.target",
    app_prefix: str = APP_PREFIX,
) -> str:
    lines: List[str] = []

    title = svc.get("container_name", name).replace("-", " ").replace("_", " ").title()
    lines += ["[Unit]", f"Description={title}", "StartLimitBurst=5", "StartLimitIntervalSec=120"]

    depends_on = svc.get("depends_on", {})
    dep_services: List[str] = []
    if isinstance(depends_on, dict):
        dep_services = [f"{app_prefix}-{k}.service" for k in depends_on]
    elif isinstance(depends_on, list):
        dep_services = [f"{app_prefix}-{k}.service" for k in depends_on]

    svc_networks = get_service_networks(svc, primary_network)
    after_line = "After=network-online.target"
    if dep_services:
        after_line += " " + " ".join(dep_services)
    lines += [after_line, "Wants=network-online.target", ""]

    lines.append("[Container]")
    lines.append(f"Image={resolve_image(name, svc, image_map, tag_override)}")

    pull_policy = str(svc.get("pull_policy", "")).strip().lower()
    if pull_policy in _PULL_MAP:
        lines.append(f"Pull={_PULL_MAP[pull_policy]}")

    lines.append(f"ContainerName={svc.get('container_name', name)}")

    if "entrypoint" in svc:
        lines.append(f"Entrypoint={format_entrypoint(svc['entrypoint'])}")

    for env_line in format_inline_environment(svc.get("environment", {}), env_vars):
        lines.append(env_line)

    for net in svc_networks:
        if net == primary_network:
            lines.append(f"Network={net}.network")
        else:
            lines.append(f"Network={app_prefix}-{net}.network")

    for port in svc.get("ports", []):
        lines.append(f"PublishPort={port}")

    for vol in svc.get("volumes", []):
        if ":" in str(vol):
            mount = translate_volume_mount(str(vol), base_dir)
            opts = mount.split(":")[2:]
            if not any(o in ("z", "Z", "ro,z", "ro,Z") for o in opts):
                mount += ":z"
            lines.append(f"Volume={mount}")
        else:
            lines.append(f"Volume={vol}")

    for cap_line in format_cap_add(svc.get("cap_add", [])):
        lines.append(cap_line)

    for sec_line in format_security_opt(svc.get("security_opt", [])):
        lines.append(sec_line)

    for secret in (secrets or []):
        lines.append(f"Secret={secret}")

    if "command" in svc:
        lines.append(f"Exec={format_exec(svc['command'], env_vars)}")

    lines.append("")
    lines.append("[Service]")

    restart_raw = str(svc.get("restart", "no")).strip().strip('"').lower()
    restart_map = {
        "no": None,
        "false": None,
        "always": "always",
        "on-failure": "on-failure",
        "unless-stopped": "always",
    }
    systemd_restart = restart_map.get(restart_raw)
    if systemd_restart:
        lines += [f"Restart={systemd_restart}", "RestartSec=5"]
    else:
        lines += ["Type=oneshot", "RemainAfterExit=yes"]

    lines += ["", "[Install]", f"WantedBy={wanted_by}"]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Network / Volume quadlet generators
# ---------------------------------------------------------------------------

def generate_network_quadlet(
    name: str,
    config: Dict[str, Any],
    wanted_by: str = "multi-user.target",
    app_prefix: str = APP_PREFIX,
) -> str:
    lines = [
        "[Unit]",
        f"Description={app_prefix.title()} {name} Network",
        "",
        "[Network]",
        f"NetworkName={name}",
        "Driver=bridge",
    ]
    if (config or {}).get("internal", False):
        lines.append("Internal=true")
    lines += ["", "[Install]", f"WantedBy={wanted_by}"]
    return "\n".join(lines)


def generate_volume_quadlet(name: str, wanted_by: str = "multi-user.target") -> str:
    return f"[Volume]\nVolumeName={name}\n\n[Install]\nWantedBy={wanted_by}\n"


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def generate(
    compose_path: Path,
    outdir: Path,
    image_map: Dict[str, str],
    base_dir: str,
    primary_network: str,
    tag_override: Optional[str] = None,
    secrets_map: Optional[Dict[str, List[str]]] = None,
    wanted_by: str = "default.target",
    env_file: Optional[str] = None,
    app_prefix: str = APP_PREFIX,
) -> None:
    data = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    services: Dict[str, Any] = data.get("services", {})
    volumes: Dict[str, Any] = data.get("volumes", {}) or {}
    networks: Dict[str, Any] = data.get("networks", {}) or {}

    env_vars: Dict[str, str] = {}
    if env_file:
        resolved_env = env_file.replace("%h", str(Path.home()))
        env_vars = load_env_vars(resolved_env)
    if not env_vars:
        env_vars = load_env_vars(str(compose_path.parent / ".env"))

    outdir.mkdir(parents=True, exist_ok=True)

    # Primary (default) network quadlet
    (outdir / f"{primary_network}.network").write_text(
        generate_network_quadlet(primary_network, {}, wanted_by, app_prefix)
    )
    print(f"Wrote  {primary_network}.network")

    # Extra named networks
    for net_name, net_cfg in networks.items():
        if net_name == "default":
            continue
        fname = f"{app_prefix}-{net_name}.network"
        (outdir / fname).write_text(
            generate_network_quadlet(net_name, net_cfg or {}, wanted_by, app_prefix)
        )
        print(f"Wrote  {fname}")

    # Named volumes
    for vol_name in volumes:
        fname = f"{app_prefix}-{vol_name}.volume"
        (outdir / fname).write_text(generate_volume_quadlet(vol_name, wanted_by))
        print(f"Wrote  {fname}")

    # Container quadlets
    for svc_name, svc in services.items():
        quadlet_text = service_to_quadlet(
            svc_name, svc, image_map, base_dir, primary_network,
            env_vars, tag_override, (secrets_map or {}).get(svc_name, []),
            wanted_by, app_prefix,
        )
        container_name = str(svc.get("container_name", svc_name))
        safe = re.sub(r"[^\w.\-]", "_", container_name)
        fname = f"{app_prefix}-{safe}.container"
        (outdir / fname).write_text(quadlet_text)
        print(f"Wrote  {fname}")


# ---------------------------------------------------------------------------
# Secrets helpers
# ---------------------------------------------------------------------------

def load_secrets_map(args) -> Dict[str, List[str]]:
    sm: Dict[str, List[str]] = {}
    if hasattr(args, "secrets_map_file") and args.secrets_map_file:
        p = Path(args.secrets_map_file)
        if not p.exists():
            raise SystemExit(f"secrets-map-file {p} not found")
        data = json.loads(p.read_text())
        for svc, val in data.items():
            sm[svc] = [val] if isinstance(val, str) else list(val)
    if hasattr(args, "secrets") and args.secrets:
        for entry in args.secrets:
            if "=" not in entry:
                raise SystemExit(f"bad --secrets entry: {entry!r}")
            svc, s = entry.split("=", 1)
            sm.setdefault(svc.strip(), []).extend(x.strip() for x in s.split(",") if x.strip())
    return sm


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(
        description="Generate Podman quadlets from the pdiiif docker-compose YAML",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("compose", nargs="?", default="../docker-compose.yml",
                   help="Path to docker-compose YAML (default: ../docker-compose.yml)")
    p.add_argument("--output", "-o", default=".",
                   help="Output directory (default: current directory)")
    p.add_argument("--base-dir", default=DEFAULT_BASE_DIR,
                   help=f"Base directory for relative host paths (default: {DEFAULT_BASE_DIR})")
    p.add_argument("--network-name", default=DEFAULT_NETWORK_NAME,
                   help=f"Primary Podman network name (default: {DEFAULT_NETWORK_NAME})")
    p.add_argument("--prefix", default=APP_PREFIX,
                   help=f"Filename/unit prefix (default: {APP_PREFIX})")
    p.add_argument("--env-file", default="",
                   help="Path to .env file for variable substitution")
    p.add_argument("--image-map", "-m", action="append",
                   help="service=image:tag override (repeatable)")
    p.add_argument("--image-map-file",
                   help="JSON file {service: image:tag} for image overrides")
    p.add_argument("--tag", help="Override tag for build images (e.g. 1.2.3)")
    p.add_argument("--secrets", "-s", action="append",
                   help="service=secret1,secret2 Podman secrets (repeatable)")
    p.add_argument("--secrets-map-file",
                   help="JSON file {service: [secrets]} for Podman secrets")
    p.add_argument("--user", action="store_true",
                   help="Emit WantedBy=default.target (rootless user units, recommended)")
    args = p.parse_args()

    compose_path = Path(args.compose)
    if not compose_path.exists():
        print(f"error: compose file not found: {compose_path}", file=sys.stderr)
        sys.exit(2)

    generate(
        compose_path=compose_path,
        outdir=Path(args.output),
        image_map=load_image_map(args),
        base_dir=args.base_dir,
        primary_network=args.network_name,
        tag_override=args.tag,
        secrets_map=load_secrets_map(args),
        wanted_by="default.target" if args.user else "multi-user.target",
        env_file=args.env_file or None,
        app_prefix=args.prefix,
    )


if __name__ == "__main__":
    main()
