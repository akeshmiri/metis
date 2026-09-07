"""
Obtain a repository to analyse (Atlas's `git-repository-cloner`).

**The gap this closes.** `metis analyse` has always required a checkout already
on disk, and nothing in the spec says why — it is unaddressed rather than
decided. So a run that could otherwise be described end to end ("model this
service") needed a manual step nobody wrote down.

**A checkout is an intake source, not the system under test** (X-7a). Reading a
repository to learn what the code says is the same act as reading a tracker to
learn what somebody asked for; it is not calling the service the code
implements. So this needs no execution tier — but it does need the rest of the
care an outward action gets.

**A git URL is an execution vector, and this is the whole reason the module is
not three lines.** `git clone ext::sh -c '<cmd>'` runs the command. So does a
remote whose `--upload-pack` is supplied. So does a URL that is really an
option, because `git clone --upload-pack=... <dir>` parses as flags. Each is
refused by shape here rather than trusted to a caller, the same way
`observers/sql.assert_read_only` refuses a statement it cannot prove is a read.

Credentials never come from an argument (PLT-005): a token belongs in the
environment or in git's own credential helper, and a URL carrying one would land
in the process listing and in this module's own error messages.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

# Only these reach a network the way a reader expects. `ext::` and `file::` are
# refused by name because they are the documented execution vectors; anything
# not matched here is refused for being unrecognised rather than allowed by
# default.
_ALLOWED = re.compile(r"^(?:https://|ssh://|git@[\w.-]+:)[\w.\-/~@:]+$")
_FORBIDDEN_PREFIX = ("ext::", "file://", "-", "--")

TIMEOUT_SECONDS = 300


class UnsafeRemote(Exception):
    """The URL is not provably a plain fetch. Nothing was run."""


class CheckoutFailed(Exception):
    """git could not produce the checkout."""


def assert_fetchable(url: str) -> None:
    """Refuse anything that is not plainly a remote to fetch from.

    Deliberately conservative, for the reason `sql.assert_read_only` gives: a
    refused clone is a message, and an accepted `ext::` URL is somebody else's
    command running on this machine.
    """
    text = (url or "").strip()
    if not text:
        raise UnsafeRemote("no remote given")
    lowered = text.lower()
    for bad in _FORBIDDEN_PREFIX:
        if lowered.startswith(bad):
            raise UnsafeRemote(
                f"{text[:40]!r} starts with {bad!r}. A remote that is an option "
                f"or a transport helper is arbitrary command execution, not a "
                f"fetch. Nothing was run.")
    if "@" in text and "://" not in text and not text.startswith("git@"):
        raise UnsafeRemote(f"{text[:40]!r} is not a form this recognises")
    if not _ALLOWED.match(text):
        # An existing local checkout is allowed, and the narrowness matters: it
        # must already BE a repository. `git clone /some/path` uses the local
        # transport -- no network, no helper, nothing executed -- so the vectors
        # this module refuses do not apply. Requiring `.git` to exist keeps it
        # from becoming "any path", and it is what makes the happy path
        # testable offline; a clone nothing can exercise is a clone nothing
        # defends.
        candidate = Path(text).expanduser()
        if not (candidate.is_dir() and (candidate / ".git").exists()):
            raise UnsafeRemote(
                f"{text[:60]!r} is not an https, ssh or git@host remote, and "
                f"not an existing local checkout. Refused for being "
                f"unrecognised rather than allowed by default.")
    if "\n" in url or "\r" in url:
        raise UnsafeRemote("a remote containing a newline is not a remote")


def clone(url: str, into: str | Path, *, ref: str = "",
          depth: int = 1, replace: bool = False) -> dict:
    """A disposable checkout of `url` at `into`.

    **Shallow by default**, because this exists to be read once and thrown away:
    extraction reads the working tree, and full history is cost with no reader.
    Pass `depth=0` for the whole history when a range comparison needs it.

    **Refuses to overwrite** unless asked. A clone that silently replaced a
    directory would be the one command here capable of destroying work.
    """
    assert_fetchable(url)
    target = Path(into).expanduser()

    if target.exists():
        if not replace:
            raise CheckoutFailed(
                f"{target} already exists. Pass replace=True to discard it, or "
                f"point somewhere else — this does not overwrite by default.")
        if not (target / ".git").exists():
            # Refuse to delete something that is not a checkout: the argument
            # could be a home directory as easily as a scratch path.
            raise CheckoutFailed(
                f"{target} exists and is not a git checkout. Refusing to "
                f"delete it.")
        shutil.rmtree(target)

    command = ["git", "clone", "--quiet"]
    if depth:
        command += ["--depth", str(depth)]
    if ref:
        command += ["--branch", ref]
    # `--` ends option parsing, so a remote that looks like a flag cannot become
    # one. `assert_fetchable` already refuses those; this is the second lock.
    command += ["--", url, str(target)]

    try:
        result = subprocess.run(command, capture_output=True, text=True,
                                timeout=TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise CheckoutFailed(f"git clone could not run: {e}") from None

    if result.returncode != 0:
        # **git's own message, with the remote redacted out of it.** The comment
        # here used to say "never the URL" and the code did not deliver that:
        # git echoes the remote in almost every failure, so the URL travelled
        # into the exception and from there into logs. A URL may carry a token
        # somebody embedded despite PLT-005, so the substitution is the point,
        # not the intention.
        raise CheckoutFailed(
            f"git clone failed ({result.returncode}): "
            f"{_redact(result.stderr, url).strip()[:200]}")

    return {
        "ok": True,
        "path": str(target),
        "ref": ref or "(default branch)",
        "depth": depth or "full",
        "commit": _head(target),
        "means": ("an intake source on disk, not the system under test (X-7a) "
                  "— reading a repository is not calling the service it builds"),
    }


def _redact(text: str, url: str) -> str:
    """Remove the remote from a message that is about to be raised or logged."""
    return (text or "").replace(url, "<remote>") if url else (text or "")


def _head(target: Path) -> str:
    try:
        out = subprocess.run(["git", "-C", str(target), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=30)
        return out.stdout.strip() if out.returncode == 0 else "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
