"""
Who may see the answers.

The assessment module protects three things that, if read by a coder, defeat
the point of assessing them at all:

  - the question bank, which carries `correct_answer`
  - the answer-key and paper exports
  - session tokens, since holding someone else's token means sitting their exam

Those were open on the public internet. `export`, `export-all` and the question
DELETE already checked the passphrase, so the rule existed — it had simply been
applied where it was written and not next door. This module exists so the check
has one home and new endpoints inherit it rather than re-deriving it.

Deliberately NOT authentication. The platform has no accounts, and a shared
passphrase in a query string is a weak control: it reaches server logs, and
anyone who has it has everything. It raises the bar from "know the URL" to
"know the secret", which closes the accidental-discovery case that matters
today. Real per-user auth is a separate decision.
"""
from fastapi import Depends, HTTPException, Query

from config import settings


def require_passphrase(passphrase: str = Query(default="")) -> None:
    """
    Reject the request unless it carries the master passphrase.

    Attached as a router-level dependency rather than repeated per endpoint —
    per-endpoint is exactly how the gap that made this necessary appeared.
    """
    if not passphrase or passphrase != settings.MASTER_ADMIN_PASSPHRASE:
        raise HTTPException(
            status_code=403,
            detail="This view is passphrase-protected. Enter the trainer passphrase to continue.",
        )


#: Convenience for `include_router(..., dependencies=TRAINER_ONLY)`.
TRAINER_ONLY = [Depends(require_passphrase)]
