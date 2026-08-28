"""One-time (and occasional) YouTube authorisation.

The OAuth consent screen for this project is in **Testing** mode, which means
Google issues refresh tokens that expire after ~7 days. That is a deliberate
trade: publishing to production requires a homepage, a privacy policy and a
Search Console–verified domain, which are only worth building alongside the
YouTube API audit. Until then, re-run this when an upload reports an expired
token:

    python -m graph_bot.publish.auth          # authorise / re-authorise
    python -m graph_bot.publish.auth --status # who am I, which scopes, still valid?

Scopes requested, and why each is needed:
    youtube.upload    videos.insert + thumbnails.set
    youtube.force-ssl playlists.list + playlistItems.insert (playlist auto-add)
Nothing broader is requested; force-ssl is already the widest of the two because
it implies delete rights on the channel.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys

from ..config import CONFIG_DIR, load_settings

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]
CLIENT_SECRET = CONFIG_DIR / "client_secret.json"
TOKEN_FILE = CONFIG_DIR / "youtube_token.json"


class AuthError(RuntimeError):
    """Raised with a message a human can act on."""


def _libs():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        return Request, Credentials, InstalledAppFlow, build
    except ImportError as exc:
        raise AuthError(
            "Google API libraries are missing. Run:\n"
            "  .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt"
        ) from exc


def token_info() -> dict:
    """What the cached token is, without contacting Google."""
    if not TOKEN_FILE.exists():
        return {"present": False, "reason": "no token yet — run: python -m graph_bot.publish.auth"}
    try:
        raw = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"present": False, "reason": f"token file unreadable: {exc}"}

    have = set(raw.get("scopes") or [])
    missing = [s for s in SCOPES if s not in have]
    expiry = raw.get("expiry")
    expired = False
    if expiry:
        try:
            expired = dt.datetime.fromisoformat(expiry.replace("Z", "+00:00")) < dt.datetime.now(dt.timezone.utc)
        except ValueError:
            pass
    return {
        "present": True,
        "scopes": sorted(have),
        "missing_scopes": missing,
        "has_refresh_token": bool(raw.get("refresh_token")),
        "access_token_expired": expired,
        # An expired access token is normal and refreshes silently; a missing
        # scope or refresh token is what actually requires a human.
        "needs_reauth": bool(missing) or not raw.get("refresh_token"),
    }


def credentials(interactive: bool = False):
    """Return valid credentials, refreshing silently when possible.

    interactive=False (the dashboard) never opens a browser: it raises with an
    instruction instead, because a server thread cannot complete a consent flow.
    """
    Request, Credentials, InstalledAppFlow, _ = _libs()
    if not CLIENT_SECRET.exists():
        raise AuthError(
            f"Missing {CLIENT_SECRET.name}. Download the OAuth client (Desktop app) "
            "from Google Cloud → Credentials and save it to config/client_secret.json."
        )

    creds = None
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        except Exception:
            creds = None

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
            return creds
        except Exception as exc:
            if not interactive:
                raise AuthError(
                    "YouTube authorisation has expired. The consent screen is in Testing "
                    "mode, so refresh tokens last about 7 days.\n"
                    "Run:  python -m graph_bot.publish.auth"
                ) from exc

    if not interactive:
        raise AuthError(
            "Not authorised for YouTube yet (or the scopes changed).\n"
            "Run:  python -m graph_bot.publish.auth"
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
    creds = flow.run_local_server(port=0)
    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    return creds


def service(interactive: bool = False):
    _, _, _, build = _libs()
    return build("youtube", "v3", credentials=credentials(interactive), cache_discovery=False)


def expected_channel() -> dict[str, str]:
    cfg = (load_settings().get("youtube") or {})
    return {"id": cfg.get("channel_id", ""), "name": cfg.get("channel_name", "")}


def whoami() -> dict:
    """Which channel this token actually controls."""
    yt = service()
    r = yt.channels().list(part="snippet,contentDetails,statistics", mine=True).execute()
    items = r.get("items") or []
    if not items:
        raise AuthError("Authorised, but this account has no YouTube channel.")
    c = items[0]
    want = expected_channel()
    return {
        "channel_id": c["id"],
        "title": c["snippet"]["title"],
        "videos": c.get("statistics", {}).get("videoCount"),
        "subscribers": c.get("statistics", {}).get("subscriberCount"),
        "expected_id": want["id"],
        "expected_name": want["name"],
        "matches": (not want["id"]) or c["id"] == want["id"],
    }


def assert_right_channel() -> dict:
    """Refuse to act on the wrong channel.

    The Google account owns a personal channel as well as the brand channel, and
    the OAuth account chooser offers the personal one first. Uploading there is
    not silently recoverable -- the video must be deleted and re-uploaded -- so
    this is checked before every upload, not only at authorisation time.
    """
    me = whoami()
    if not me["matches"]:
        raise AuthError(
            f"Authorised for the WRONG channel: {me['title']!r} ({me['channel_id']}). "
            f"Expected {me['expected_name']!r} ({me['expected_id']}). "
            "Re-authorise and pick the right channel: "
            "python -m graph_bot.publish.auth --reset"
        )
    return me


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m graph_bot.publish.auth")
    ap.add_argument("--status", action="store_true", help="report the cached token; no browser")
    ap.add_argument("--reset", action="store_true",
                    help="discard the cached token and choose the account/channel again")
    args = ap.parse_args()

    if args.status:
        info = token_info()
        if not info["present"]:
            sys.exit(f"❌ {info['reason']}")
        print(f"scopes            : {', '.join(info['scopes']) or 'none'}")
        print(f"missing scopes    : {', '.join(info['missing_scopes']) or 'none'}")
        print(f"refresh token     : {'yes' if info['has_refresh_token'] else 'NO'}")
        print(f"access token      : {'expired (refreshes itself)' if info['access_token_expired'] else 'valid'}")
        print(f"needs re-auth     : {'YES' if info['needs_reauth'] else 'no'}")
        if not info["needs_reauth"]:
            try:
                me = whoami()
                mark = "✅" if me["matches"] else "❌"
                print(f"\n{mark} reaches channel : {me['title']}  ({me['videos']} videos,"
                      f" {me['subscribers']} subscribers)")
                if not me["matches"]:
                    print(f"   expected        : {me['expected_name']} ({me['expected_id']})")
                    print("   WRONG CHANNEL -- uploads are blocked. Fix with:")
                    print("     python -m graph_bot.publish.auth --reset")
            except Exception as exc:
                print(f"\n⚠ could not reach the API: {str(exc).splitlines()[0]}")
        return

    if args.reset and TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
        print("Discarded the cached token.")

    want = expected_channel()
    if want["name"]:
        print(f"IMPORTANT: at the account chooser pick the channel {want['name']!r} --")
        print("  NOT your personal channel. Uploading to the wrong one means")
        print("  deleting the video and starting over.")
        print()
    print("Opening a browser to authorise. The consent screen will warn that")
    print("'Google hasn't verified this app' — that is expected for an unverified")
    print("project. Click Advanced → Go to Graph-Bot (unsafe), then approve.\n")
    print(f"Scopes requested:\n  " + "\n  ".join(SCOPES) + "\n")
    try:
        credentials(interactive=True)
        me = whoami()
    except AuthError as exc:
        sys.exit(f"❌ {exc}")
    if not me["matches"]:
        sys.exit(
            f"❌ That authorised {me['title']!r}, but this project uploads to "
            f"{me['expected_name']!r}. Run it again and pick the right channel: "
            "python -m graph_bot.publish.auth --reset"
        )
    print(f"✅ authorised for {me['title']} ({me['videos']} videos)")
    print(f"   token cached at {TOKEN_FILE.relative_to(CONFIG_DIR.parent)}")


if __name__ == "__main__":
    main()
