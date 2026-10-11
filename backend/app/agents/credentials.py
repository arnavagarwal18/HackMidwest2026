"""Spots expired or invalid AWS credentials, which no retry can fix, so a run can go straight to the rule fallback."""
from typing import Iterable

from botocore.exceptions import ClientError, CredentialRetrievalError, NoCredentialsError, TokenRetrievalError

CREDENTIALS_EXPIRED_LINE = "AWS credentials expired: refresh the hackmidwest profile"
CREDENTIAL_EXCEPTIONS = (NoCredentialsError, TokenRetrievalError, CredentialRetrievalError)
EXPIRED_CODES = {"ExpiredTokenException", "ExpiredToken", "UnrecognizedClientException", "InvalidClientTokenId", "InvalidSignatureException"}
TOKEN_WORDS = ("token", "expired")  # in an AccessDeniedException's message, what marks a token problem


def exception_chain(exc: BaseException | None):
    """`exc` and its causes, outermost first."""
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        yield exc
        exc = exc.__cause__ or exc.__context__


def _is_credential_failure(exc: BaseException) -> bool:
    if isinstance(exc, CREDENTIAL_EXCEPTIONS):
        return True
    if not isinstance(exc, ClientError):
        return False
    error = exc.response.get("Error", {})
    code = error.get("Code", "")
    if code in EXPIRED_CODES:
        return True
    return code == "AccessDeniedException" and any(word in str(error.get("Message", "")).lower() for word in TOKEN_WORDS)


def is_credential_error(exc: BaseException | None) -> bool:
    """True when `exc` or one of its causes says the AWS credentials are expired, missing or invalid."""
    return any(_is_credential_failure(cause) for cause in exception_chain(exc))


def first_credential_error(errors: Iterable[BaseException | None]) -> BaseException | None:
    return next((e for e in errors if is_credential_error(e)), None)
