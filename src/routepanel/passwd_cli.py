# src/routepanel/passwd_cli.py
"""routepanel-passwd -- set the panel password (writes cfg.password_file, 0600)."""
import getpass, os, sys
from routepanel.config import get_config
from routepanel.panel.auth import hash_password

def main() -> None:
    pw = sys.argv[1] if len(sys.argv) > 1 else getpass.getpass("New panel password: ")
    if not pw:
        sys.exit("empty password refused")
    path = get_config().password_file
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):                       # backup before change -- never clobber
        os.replace(path, path + ".bak")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(hash_password(pw) + "\n")
    print(f"password written to {path}")
