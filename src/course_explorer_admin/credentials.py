"""Sole owner of the administration credential file and of the administration state directory.

One administration account per site is stored as one closed JSON document under
``data/admin-web/password``: the username and an argon2id encoded hash. The password itself is
never written, echoed or acknowledged. This module holds no web framework dependency, because the
terminal provisioning command and the administration backend both read and write the same state.

It also owns the repository-relative administration state directory every administration security
and record file lives under, so one place names that root.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import argon2
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from course_explorer.administration import (
    administrative_json,
    atomic_write_private_text,
    load_private_model,
    repository_root,
)
from course_explorer.validation import require_text

# The repository-relative directory every administration security and record file lives under.
ADMIN_WEB_STATE_ROOT: Path = Path("data") / "admin-web"
# The one administration credential file beneath that directory.
PASSWORD_FILENAME = "password"

_hasher = argon2.PasswordHasher(type=argon2.Type.ID)


class AdminCredential(BaseModel):
    """One stored administration account: its username and its encoded argon2id hash.

    The hash is excluded from the rendered form, so a diagnostic print of this model carries no
    credential. Only the credential owner reads and writes it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    username: str
    password_hash: str = Field(repr=False)


class PasswordSetReport(BaseModel):
    """The acknowledgment of one stored administration account."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    configured: Literal[True] = True


def read_admin_credential(*, root: Path | None = None) -> AdminCredential:
    """Read the site's one administration account from its regular non-symlink state file.

    ``root`` defaults to the repository root that owns the ignored administration state. A missing,
    symlinked, non-regular or schema-mismatching file raises ``ValueError`` rather than reporting an
    absent account, so a backend never treats unreadable credential state as a login attempt.
    """
    resolved = repository_root() if root is None else root
    return load_private_model(resolved / ADMIN_WEB_STATE_ROOT / PASSWORD_FILENAME, AdminCredential)


def verify_admin_password(
    credential: AdminCredential, *, username: str, password: SecretStr
) -> bool:
    """Report whether one username and password pair matches the stored account.

    A username mismatch alone is a plain ``False``. A stored hash that is not an argon2id encoding,
    and any other verification failure, raises ``ValueError``, so malformed credential state is an
    operational failure rather than a failed login attempt. The one verification call runs before the
    username is compared, so a malformed stored hash raises whatever username the attempt presents.
    The hash is never rehashed or converted, and the password value never leaves this call.
    """
    try:
        parameters = argon2.extract_parameters(credential.password_hash)
    except argon2.exceptions.InvalidHashError as exc:
        raise ValueError("administration credential state holds an unreadable hash") from exc
    if parameters.type is not argon2.Type.ID:
        raise ValueError("administration credential state must hold an argon2id hash")
    try:
        verified = _hasher.verify(credential.password_hash, password.get_secret_value())
    except argon2.exceptions.VerifyMismatchError:
        verified = False
    except argon2.exceptions.VerificationError as exc:
        raise ValueError("administration credential state holds an unverifiable hash") from exc
    return verified and username == credential.username


def set_admin_password(*, username: str, password: SecretStr) -> PasswordSetReport:
    """Store one administration account as a closed JSON document with a mode-0600 file.

    The username must be nonblank and NUL-free, and the password must be nonblank. The password's
    characters are preserved and hashed with the library's own argon2id cost parameters. The
    administration state directory is created with parents at mode 0700, and a password leaf that
    is present must be a regular non-symlink file before it is replaced. The acknowledgment reports
    the account as configured.
    """
    checked_username = require_text(username, "username")
    if not password.get_secret_value().strip():
        raise ValueError("password must not be blank")
    path = repository_root() / ADMIN_WEB_STATE_ROOT / PASSWORD_FILENAME
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("administration credential state must be a regular non-symlink file")
    credential = AdminCredential(
        username=checked_username, password_hash=_hasher.hash(password.get_secret_value())
    )
    atomic_write_private_text(path, administrative_json(credential), mode=0o600)
    return PasswordSetReport()
