# Instagram + Facebook setup (Meta Graph API)

Publishing to Instagram Reels and Facebook needs a Meta app with reviewed permissions.
Budget **~2–4 weeks** for app review — start this early.

## Prerequisites

1. **Instagram Business (or Creator) account** — Creator accounts are *not* supported for
   content publishing, so use **Business**.
2. A **Facebook Page**, with the Instagram account **linked** to it
   (Page → Settings → Linked accounts → Instagram).
3. A **Meta developer app** at https://developers.facebook.com/ (type: Business).

## Permissions to request (App Review)

Submit each for review (screencast of the flow required):
- `instagram_business_basic`
- `instagram_business_content_publish`
- `pages_show_list`, `pages_read_engagement`, `pages_manage_posts` (for Facebook)

While in **Development mode**, you can test with your own admin/test accounts before review
is approved.

## Get the IDs and token

- **FB_PAGE_ID** — on your Page → About, or via Graph API Explorer `GET /me/accounts`.
- **IG_USER_ID** — `GET /{page-id}?fields=instagram_business_account`.
- **META_ACCESS_TOKEN** — a **long-lived Page access token**:
  1. In Graph API Explorer, select your app + Page, grant the permissions above.
  2. Exchange the short-lived token for a long-lived one
     (`GET /oauth/access_token?grant_type=fb_exchange_token&...`). Long-lived Page tokens
     don't expire as long as the user stays active.

Put them in `.env` (copy from `.env.example`):

```
META_ACCESS_TOKEN=EAAB...
IG_USER_ID=1784xxxxxxxxx
FB_PAGE_ID=1029xxxxxxxxx
PUBLIC_BASE_URL=https://your-host/graphbot
```

## The Instagram public-URL requirement

Instagram's API does **not** accept a local file — it downloads the video from a public URL.
So the approved mp4 must be reachable at:

```
{PUBLIC_BASE_URL}/{date}/{key}/video.mp4
```

Options to provide that URL:
- Host the `output/` folder on any static web host / S3 / CDN, or
- Serve locally and tunnel: `python -m http.server 8000 --directory output` then expose it
  with ngrok, and set `PUBLIC_BASE_URL=https://<ngrok-id>.ngrok.io`.

Facebook uploads the local file directly, so it needs no public URL.

## Run

```bash
# check readiness without calling the API
.\.venv\Scripts\python.exe -m graph_bot.publish.meta --dry-run

# publish an approved item
.\.venv\Scripts\python.exe -m graph_bot.publish.meta --key population --targets instagram,facebook

# facebook only (no public URL needed)
.\.venv\Scripts\python.exe -m graph_bot.publish.meta --all --targets facebook
```
