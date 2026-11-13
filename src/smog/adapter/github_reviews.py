"""Review data for the human-review measurements: a JSON file, filled from the GitHub REST API on request.

Nothing is sent to GitHub but the repository's owner and name, commit hashes, pull request numbers and paging
numbers, all inside API paths, plus a token in the `Authorization` header when one is found. The API must be
reached over https, and a redirect is followed only to the same host over https, so the token reaches no other
host. No email address is read, stored or sent: of a review, only the login, the state and the time are kept.

An answer of any other shape than the API documents gives "not run" for the tool, never a value.
"""

import http.client
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from smog.domain.reviews import PullRequest, Review, ReviewData
from smog.ports import ToolUnavailable

# `git@host:owner/name.git`, `https://host/owner/name` and `ssh://git@host:22/owner/name.git`.
_REMOTE = re.compile(r"^(?:[a-z+]+://)?(?:[^@/]+@)?([^/:]+)(?::\d+)?[:/]([^/]+)/([^/]+?)(?:\.git)?/?$")
# Seconds to wait for one answer. Not a rule: it changes whether a run gets its data, never a value.
_TIMEOUT_SECONDS = 30

# Status, headers with lower-case names, body.
Response = tuple[int, dict[str, str], bytes]


def review_data(root: str, commits: list[str], fetch: bool, settings: dict, get: Callable[[str], Response] | None = None) -> ReviewData:
    """What the file of the setting `reviews_file` knows, and with `fetch` what GitHub knows about the commits it lacks.

    A commit the file does not know is always asked for, first, so that a run after a new commit needs no
    flag. Without `fetch` that is all that is asked. The file, if one is set, is written back with what was
    fetched, also when the fetch fails part way, so the next run asks only for the rest. `get` replaces the
    HTTP request in tests.

    What `fetch` asks for again is the setting `reviews_refetch`. With `unmerged`, the default, so is every commit the file records without a merged pull
    request: when the file was written the commit may have been on a branch whose pull request was open, or
    not pushed at all. With `all`, every commit is asked for again and so are the reviews of its pull requests,
    which picks up an approval dismissed since. With `none`, only unknown commits are asked for.

    A failure while a commit the file does not know is still open raises ToolUnavailable: the data is incomplete.
    A failure after that, while asking again, discards nothing: the commits not asked again keep what the file
    says about them, and the data names them with the reason (`ReviewData.not_refreshed`).
    """
    path = settings["reviews_file"]
    target = Path(root) / path if path else None
    data = _read(target) if target and target.exists() else ReviewData()
    refetch = settings["reviews_refetch"] if fetch else "none"
    unknown = sorted(data.unknown(commits))
    again = sorted({"all": data.known(commits), "unmerged": data.without_merged_pull_request(commits), "none": set()}[refetch])
    if not unknown and not again:
        return data
    fetched: list[str] = []
    client = None
    failure = ""
    try:
        client = _client(root, data, settings, get)
        for sha in [*unknown, *again]:
            client.look_up(sha, data, refetch_reviews=refetch == "all")
            fetched.append(sha)
    except ToolUnavailable as error:
        if len(fetched) < len(unknown):
            failure = str(error)
            kept = ", kept in the reviews file" if target else ""
            raise ToolUnavailable(f"{error}; {len(fetched)} of {len(unknown) + len(again)} commits fetched{kept}") from None
        data.keep_saved(again[len(fetched) - len(unknown) :], str(error))
    finally:
        if target and (client or failure):
            _write(target, data)
    return data


def _client(root: str, data: ReviewData, settings: dict, get: Callable[[str], Response] | None) -> "_GitHub":
    """The GitHub of the `origin` remote. Raises ToolUnavailable when it may not be asked or the data is of another repository."""
    if urlsplit(settings["reviews_api_url"]).scheme != "https":
        raise ToolUnavailable("the setting reviews_api_url must start with https://, so that the token is sent encrypted")
    repository = origin_repository(root, settings["reviews_api_url"])
    if data.repository and data.repository.lower() != repository.lower():
        raise ToolUnavailable(f"the reviews file is for {data.repository} and the `origin` remote is {repository}")
    data.name_repository(repository)
    if get is not None:
        return _GitHub(repository, settings, get, logged_in=True)
    token = _token()
    return _GitHub(repository, settings, _http_get(token), logged_in=bool(token))


def origin_repository(root: str, api_url: str) -> str:
    """`owner/name` from the URL of the `origin` remote, which must be on the host of the API. The URL is never
    printed: it can hold a password."""
    host = (urlsplit(api_url).hostname or "").removeprefix("api.")
    result = subprocess.run(["git", "-C", root, "remote", "get-url", "origin"], capture_output=True, text=True)
    match = _REMOTE.match(result.stdout.strip()) if result.returncode == 0 else None
    if match is None or match.group(1).lower() != host:
        raise ToolUnavailable(f"the repository has no `origin` remote on {host}")
    return f"{match.group(2)}/{match.group(3)}"


class _GitHub:
    def __init__(self, repository: str, settings: dict, get: Callable[[str], Response], logged_in: bool):
        self._repository = repository
        self._logged_in = logged_in
        self._api = settings["reviews_api_url"].rstrip("/")
        self._base = f"{self._api}/repos/{repository}"
        self._page_size = settings["reviews_page_size"]
        self._max_pages = settings["reviews_max_pages"]
        self._get = get

    def look_up(self, sha: str, data: ReviewData, refetch_reviews: bool = False) -> None:
        """Record the merged pull requests a commit belongs to, each with its reviews, or that it belongs to none.

        `GET /repos/{owner}/{repo}/commits/{sha}/pulls` lists the pull requests of a commit, its merge or squash
        commit included; GitHub answers 422 for a hash it does not hold, which is a commit never pushed. The
        data changes only after every request for the commit has succeeded. The reviews of a pull request the
        data holds already are asked for again only with `refetch_reviews`.
        """
        rows = self._rows(f"/commits/{sha}/pulls", unknown_is_empty=True)
        found = []
        for row in rows:
            if not row.get("merged_at"):
                continue
            number, merge_commit = row.get("number"), row.get("merge_commit_sha") or ""
            if isinstance(number, bool) or not isinstance(number, int) or not isinstance(merge_commit, str):
                raise ToolUnavailable("GitHub answered with a pull request that has no number or no commit hash")
            fresh = refetch_reviews or not data.holds(number)
            reviews, merged_by = (self._reviews(number), self._login(f"/pulls/{number}", "merged_by")) if fresh else ([], "")
            found.append((PullRequest(number, merge_commit, [] if sha == merge_commit else [sha], reviews, merged_by), fresh))
        for pull_request, fresh in found:
            data.add(pull_request, replace_reviews=fresh)
        if not found:
            data.add_without_pull_request(sha, self._login(f"/commits/{sha}", "author", unknown_is_empty=True))

    def _login(self, path: str, field: str, unknown_is_empty: bool = False) -> str:
        """The login in `field` of one object, such as who merged a pull request or who authored a commit, or empty.
        With `unknown_is_empty`, a 422 is empty: GitHub does not hold the commit, so it was never pushed."""
        status, headers, body = self._get(f"{self._base}{path}")
        if status == 422 and unknown_is_empty:
            return ""
        if status != 200:
            raise ToolUnavailable(self._failure(status, headers, body))
        try:
            user = json.loads(body).get(field) or {}
        except (ValueError, AttributeError):
            raise ToolUnavailable(f"GitHub answered {path} with something that is not a JSON object") from None
        login = user.get("login") if isinstance(user, dict) else None
        return login if isinstance(login, str) else ""

    def _reviews(self, number: int) -> list[Review]:
        reviews = []
        for row in self._rows(f"/pulls/{number}/reviews"):
            user, state, time = row.get("user") or {}, row.get("state"), row.get("submitted_at") or ""
            login = user.get("login") or "" if isinstance(user, dict) else None
            if not isinstance(login, str) or not isinstance(state, str) or not isinstance(time, str):
                raise ToolUnavailable(f"GitHub answered with a review of pull request {number} that has no state or no user")
            reviews.append(Review(login, state, time))
        return reviews

    def _rows(self, path: str, unknown_is_empty: bool = False) -> list[dict]:
        """Every row of a paged list. GitHub names the next page in the `Link` header. A list of more than
        `reviews_max_pages` pages is not read to its end: an answer that always names a next page would never end."""
        rows: list[dict] = []
        for page in range(1, self._max_pages + 1):
            status, headers, body = self._get(f"{self._base}{path}?per_page={self._page_size}&page={page}")
            if status == 422 and unknown_is_empty:
                return []
            if status != 200:
                raise ToolUnavailable(self._failure(status, headers, body))
            try:
                found = json.loads(body)
            except ValueError:
                found = None
            if not isinstance(found, list) or not all(isinstance(row, dict) for row in found):
                raise ToolUnavailable("GitHub answered with something that is not a JSON list of objects")
            rows.extend(found)
            if 'rel="next"' not in headers.get("link", ""):
                return rows
        raise ToolUnavailable(f"GitHub lists more than {self._max_pages} pages for {path} (setting reviews_max_pages)")

    def _failure(self, status: int, headers: dict[str, str], body: bytes = b"") -> str:
        """GitHub's own answer, with the account the request was made as."""
        if status in (403, 429) and (headers.get("x-ratelimit-remaining") == "0" or "retry-after" in headers):
            reset = headers.get("x-ratelimit-reset", "")
            until = f", open again at {datetime.fromtimestamp(int(reset), UTC):%H:%M} UTC" if reset.isdigit() else ""
            return f"GitHub rate limit reached{until}"
        said = _message(body)
        account = self._account()
        return f"GitHub answered {status}{f' {said}' if said else ''} for {self._repository}, {account}"

    def _account(self) -> str:
        """Which GitHub account the requests are made as, as far as GitHub says."""
        if not self._logged_in:
            return "with no GitHub login: no GITHUB_TOKEN, GH_TOKEN or signed-in gh"
        status, _, body = self._get(f"{self._api}/user")
        if status == 401:
            return "and GitHub rejected the token"
        if status != 200:
            return f"and GitHub did not say which account the token belongs to (status {status})"
        try:
            login = json.loads(body).get("login")
        except (ValueError, AttributeError):
            login = None
        return f"logged in as {login}" if isinstance(login, str) else "with an account GitHub did not name"


def _token() -> str:
    """`GITHUB_TOKEN`, else `GH_TOKEN`, else the token of a signed-in `gh`, else none: public repositories need none."""
    for name in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(name):
            return os.environ[name]
    if shutil.which("gh"):
        result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
    return ""


class _SameHostRedirects(urllib.request.HTTPRedirectHandler):
    """Follows a redirect only to the host it came from, over https. `urllib` sends the request's headers, the
    token among them, to wherever a redirect points; any other redirect is therefore left unfollowed and comes
    back as its 3xx status."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old, new = urlsplit(req.full_url), urlsplit(newurl)
        if new.scheme != "https" or new.netloc.lower() != old.netloc.lower():
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _http_get(token: str) -> Callable[[str], Response]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "smog"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    opener = urllib.request.build_opener(_SameHostRedirects)

    def get(url: str) -> Response:
        try:
            with opener.open(urllib.request.Request(url, headers=headers), timeout=_TIMEOUT_SECONDS) as response:
                return response.status, _lower(response.headers), response.read()
        except urllib.error.HTTPError as error:
            return error.code, _lower(error.headers), error.read()
        except (OSError, http.client.HTTPException) as error:
            # A refused connection, a timeout, an answer cut off in its body, a status line that is not HTTP.
            raise ToolUnavailable(f"GitHub is not reachable: {getattr(error, 'reason', None) or error or type(error).__name__}") from None

    return get


def _lower(headers) -> dict[str, str]:
    return {name.lower(): value for name, value in headers.items()}


def _read(path: Path) -> ReviewData:
    try:
        return ReviewData.from_record(json.loads(path.read_text()))
    except (OSError, ValueError) as error:
        raise ToolUnavailable(f"the reviews file {path.name} cannot be read: {error}") from None


def _message(body: bytes) -> str:
    """The `message` of a GitHub error answer, such as "Not Found"."""
    try:
        message = json.loads(body).get("message")
    except (ValueError, AttributeError):
        return ""
    return message if isinstance(message, str) else ""


def _write(path: Path, data: ReviewData) -> None:
    record = data.to_record()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2) + "\n")
    except OSError as error:
        raise ToolUnavailable(f"the reviews file {path.name} cannot be written: {error}") from None
