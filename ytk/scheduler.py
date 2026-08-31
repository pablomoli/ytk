# pyright: basic
# Not strict-clean yet (#122). Delete these two lines once the module
# passes strict — the list of files carrying them only shrinks.
"""YouTube Data API v3 playlist polling and ingestion pipeline for ytk."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import googleapiclient.discovery
from google.auth.external_account_authorized_user import Credentials as ExternalCredentials
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from . import capture_log, db
from .config import Config

_YTK_DIR = Path.home() / ".ytk"
_CLIENT_SECRETS = _YTK_DIR / "client_secrets.json"
_TOKEN_FILE = _YTK_DIR / "token.json"
_SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]


@dataclass
class SyncResult:
    seen: int = 0
    already_processed: int = 0
    skipped: int = 0
    failed: int = 0
    ingested: int = 0

    @property
    def new(self) -> int:
        return self.seen - self.already_processed


def authenticate() -> googleapiclient.discovery.Resource:
    """
    Load or create OAuth credentials for the YouTube Data API v3.
    On first use this opens a browser-based consent flow and saves token.json.
    Subsequent calls reuse the cached token, refreshing it automatically if expired.
    Returns a googleapiclient Resource ready for API calls.
    """
    _YTK_DIR.mkdir(parents=True, exist_ok=True)

    # InstalledAppFlow can hand back either credential class, so the local has
    # to admit both or the assignment below leaves creds looking Optional.
    creds: Credentials | ExternalCredentials | None = None

    if _TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(_TOKEN_FILE), _SCOPES)

    if creds is None or not creds.valid:
        if creds is not None and creds.expired and creds.refresh_token:
            import google.auth.transport.requests as tr

            creds.refresh(tr.Request())
        else:
            if not _CLIENT_SECRETS.exists():
                raise FileNotFoundError(
                    f"Client secrets file not found: {_CLIENT_SECRETS}\n"
                    "Download it from the Google Cloud Console and place it there."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(_CLIENT_SECRETS), _SCOPES)
            flow.redirect_uri = "http://localhost"
            creds = flow.run_local_server(port=80, open_browser=False)

        _TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
        _TOKEN_FILE.chmod(0o600)

    return googleapiclient.discovery.build("youtube", "v3", credentials=creds)


def fetch_playlist_videos(
    service: googleapiclient.discovery.Resource,
    playlist_name: str = "ytk",
) -> list[dict]:
    """
    Find the playlist named `playlist_name` among the authenticated user's playlists
    and return all its videos as a list of dicts: [{video_id, title, added_at}].
    Handles pagination for both the playlist list and the items list.
    Raises RuntimeError if no playlist with that name is found.
    """
    playlist_id = _find_playlist_id(service, playlist_name)

    videos: list[dict] = []
    page_token: str | None = None

    while True:
        kwargs: dict = {
            "part": "snippet",
            "playlistId": playlist_id,
            "maxResults": 50,
        }
        if page_token:
            kwargs["pageToken"] = page_token

        response = service.playlistItems().list(**kwargs).execute()  # type: ignore[reportAttributeAccessIssue]

        for item in response.get("items", []):
            snippet = item.get("snippet", {})
            resource = snippet.get("resourceId", {})
            video_id = resource.get("videoId", "")
            if not video_id:
                continue
            videos.append(
                {
                    "video_id": video_id,
                    "title": snippet.get("title", ""),
                    "added_at": snippet.get("publishedAt", ""),
                }
            )

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return videos


def _find_playlist_id(service: googleapiclient.discovery.Resource, name: str) -> str:
    """Search the user's playlists for one matching `name` (case-insensitive)."""
    page_token: str | None = None
    target = name.lower()

    while True:
        kwargs: dict = {
            "part": "snippet",
            "mine": True,
            "maxResults": 50,
        }
        if page_token:
            kwargs["pageToken"] = page_token

        response = service.playlists().list(**kwargs).execute()  # type: ignore[reportAttributeAccessIssue]

        for item in response.get("items", []):
            snippet = item.get("snippet", {})
            if snippet.get("title", "").lower() == target:
                return item["id"]

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    raise RuntimeError(f"No YouTube playlist named '{name}' found in your account.")


def _write_playlist_cache(videos: list[dict]) -> None:
    """Persist playlist membership for signals.signal_map: a playlist add is a
    deliberate capture (section 28), and the profile reads intent from here."""
    import json
    from datetime import UTC, datetime

    payload = {
        "updated_at": datetime.now(UTC).isoformat(),
        "video_ids": sorted({v["video_id"] for v in videos}),
    }
    target = _YTK_DIR / "playlist_ids.json"
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    tmp.replace(target)


def sync(
    service: googleapiclient.discovery.Resource,
    cfg: Config,
    *,
    dry_run: bool = False,
    verbose: bool = False,
) -> SyncResult:
    """P2 (#197): fetch the 'ytk' playlist and capture every new video into
    the curator ledger (surface sync, actor sweep). The vault-writing half of
    sync is gone — notes land only after an item passes the owner. A read
    failure leaves the video unprocessed so the next run retries it; the
    capture row itself is idempotent.

    Returns a SyncResult; `ingested` now counts captures.
    """
    from . import capture as capture_verb
    from . import (
        evidence,
        gatherers,  # noqa: F401 — import fills evidence.GATHERERS
    )
    from .ledger import connect

    def _log(msg: str) -> None:
        if verbose:
            print(f"[ytk] {msg}", file=sys.stderr)

    result = SyncResult()
    _log("fetching playlist...")
    videos = fetch_playlist_videos(service)
    _write_playlist_cache(videos)
    result.seen = len(videos)
    new_videos = [v for v in videos if not db.is_processed(v["video_id"])]
    result.already_processed = len(videos) - len(new_videos)
    _log(
        f"{len(videos)} in playlist - {result.already_processed} already processed, {len(new_videos)} new"
    )

    conn = connect()
    try:
        for entry in new_videos:
            video_id: str = entry["video_id"]
            title: str = entry["title"]
            url = f"https://www.youtube.com/watch?v={video_id}"

            if dry_run:
                print(f"[dry-run] would capture: {title} ({video_id})", file=sys.stderr)
                continue

            _log(f"capturing: {title!r}")
            try:
                res = capture_verb.capture(
                    conn,
                    source="youtube",
                    url=url,
                    title=title,
                    surface="sync",
                    actor="sweep",
                    log=False,
                )
                if not res.duplicate:
                    rr = evidence.read_item(conn, res.item_id, actor="sweep")
                    if rr.error:
                        raise RuntimeError(f"read failed: {rr.error}")
            except Exception as exc:
                print(f"[ytk] FAILED {title!r}: {exc}", file=sys.stderr)
                db.mark_failed(video_id, title, str(exc))
                capture_log.log_capture(
                    "sync", url, source="youtube", outcome="error", error=str(exc)
                )
                result.failed += 1
                continue

            db.mark_processed(video_id, title)
            print(f"[ytk] captured: {title!r}", file=sys.stderr)
            capture_log.log_capture("sync", url, source="youtube", outcome="captured")
            result.ingested += 1
    finally:
        conn.close()

    return result
