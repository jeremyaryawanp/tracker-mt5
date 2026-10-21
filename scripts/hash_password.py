"""Print a password hash for ADMIN_PASSWORD_HASH.  Usage: uv run python scripts/hash_password.py"""

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.security import hash_password  # noqa: E402

if __name__ == "__main__":
    pw = getpass.getpass("Password: ")
    if pw != getpass.getpass("Repeat: "):
        sys.exit("Passwords do not match")
    print(hash_password(pw))
