"""Reading and writing the .env settings file.

One definition, imported everywhere. There used to be three copies of
``_ENV_KEYS``/``load_env``/``save_env`` at module level in importing.py plus a
fourth inlined in MainWindow.__init__. Python kept only the last one, whose key
map covered the mail settings, so ``LoginDialog`` saved the EEG Faktura
credentials into a filter that dropped every one of them - the dialog appeared
to work and wrote nothing.
"""

import os
import sys
from pathlib import Path


def _user_config_dir():
    """Per-user config location, by platform convention."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "FakturaAddon"
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming")
        return Path(base) / "FakturaAddon"
    base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(base) / "FakturaAddon"


def _default_env_path():
    """Where .env lives.

    From a source checkout, next to the code - that is what developers expect
    and what existing installs already use. Frozen, it must not be: inside a
    .app or a PyInstaller folder the settings would be written into the
    application itself, lost on every upgrade, and unwritable altogether once
    macOS relocates a quarantined app to a read-only mount.
    """
    if getattr(sys, "frozen", False):
        directory = _user_config_dir()
        directory.mkdir(parents=True, exist_ok=True)
        return directory / ".env"
    return Path(__file__).parent / ".env"


ENV_PATH = _default_env_path()

# internal field name -> .env key
ENV_KEYS = {
    "user":                    "EEG_USER",
    "password":                "EEG_PASSWORD",
    "tenant":                  "EEG_TENANT",
    "community_id":            "EEG_COMMUNITY_ID",
    "my_mail":                 "MAIL_ADDRESS",
    "imap_server":             "MAIL_IMAP_SERVER",
    "smtp_server":             "MAIL_SMTP_SERVER",
    "smtp_port":               "MAIL_SMTP_PORT",
    "my_mail_pw":              "MAIL_PASSWORD",
    "home_directory":          "HOME_DIRECTORY",
    "EEG_name":                "EEG_NAME",
    "template_export_invoice": "TEMPLATE_EXPORT_INVOICE",
    "template_email":          "TEMPLATE_EMAIL",
    "language":                "LANGUAGE",
}


def bundled_dir(*parts):
    """Locate files shipped with the app, in a checkout and inside a bundle."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def resolve_resource(path, subdir="templates"):
    """Turn a configured template path into one that actually opens.

    Settings hold bare filenames by default, which resolve against the working
    directory - fine from a checkout, arbitrary for a double-clicked .app,
    whose cwd is wherever Finder happened to start it. Fall back to the copy
    shipped inside the bundle.
    """
    if not path:
        return ""
    if os.path.isabs(path) and os.path.exists(path):
        return path
    if os.path.exists(path):
        return os.path.abspath(path)
    bundled = bundled_dir(subdir, os.path.basename(path))
    if os.path.exists(bundled):
        return bundled
    return path        # keep the configured value so the error names it


def load_env() -> dict:
    """Read KEY=VALUE pairs from .env into a dict of internal field names."""
    values = {}
    if not ENV_PATH.exists():
        return values
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        for field, env_key in ENV_KEYS.items():
            if key.strip() == env_key:
                values[field] = val.strip()
    return values


def save_env(settings: dict) -> None:
    """Write the given settings back to .env, preserving unrelated lines."""
    to_write = {ENV_KEYS[k]: v for k, v in settings.items() if k in ENV_KEYS}

    existing_lines = []
    if ENV_PATH.exists():
        existing_lines = ENV_PATH.read_text(encoding="utf-8").splitlines()

    updated = set()
    new_lines = []
    for line in existing_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.partition("=")[0].strip()
            if key in to_write:
                new_lines.append(f"{key}={to_write[key]}")
                updated.add(key)
                continue
        new_lines.append(line)

    for env_key, val in to_write.items():
        if env_key not in updated:
            new_lines.append(f"{env_key}={val}")

    ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
