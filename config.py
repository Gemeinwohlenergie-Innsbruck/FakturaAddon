"""Reading and writing the .env settings file.

One definition, imported everywhere. There used to be three copies of
``_ENV_KEYS``/``load_env``/``save_env`` at module level in importing.py plus a
fourth inlined in MainWindow.__init__. Python kept only the last one, whose key
map covered the mail settings, so ``LoginDialog`` saved the EEG Faktura
credentials into a filter that dropped every one of them - the dialog appeared
to work and wrote nothing.
"""

from pathlib import Path

ENV_PATH = Path(__file__).parent / ".env"

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
}


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
