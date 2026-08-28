# YouTube upload setup (one-time, ~10 minutes)

The publisher uses the **YouTube Data API v3** with an OAuth "Desktop app" client.
This is free. Upload cost is ~1600 quota units each; the default daily quota (10,000)
allows ~6 uploads/day.

## Steps

1. **Create / pick a Google Cloud project**
   - Go to https://console.cloud.google.com/ and create a project (any name).

2. **Enable the API**
   - APIs & Services → Library → search **"YouTube Data API v3"** → **Enable**.

3. **Configure the OAuth consent screen**
   - APIs & Services → OAuth consent screen.
   - User type: **External**. Fill in app name + your email. Save.
   - Under **Test users**, add the Google account that owns the YouTube channel.
   - (Staying in "Testing" mode is fine for personal use — no Google verification needed.)

4. **Create the OAuth client**
   - APIs & Services → Credentials → **Create Credentials → OAuth client ID**.
   - Application type: **Desktop app**. Create.
   - Click **Download JSON**.

5. **Drop it in the project**
   - Save the downloaded file as:  `config/client_secret.json`

## First run

```bash
# make sure the video is approved first
.\.venv\Scripts\python.exe -m graph_bot.review approve population

# dry run (no upload, no auth) to confirm what will publish
.\.venv\Scripts\python.exe -m graph_bot.publish.youtube --dry-run

# real upload as a PRIVATE video (safe default)
.\.venv\Scripts\python.exe -m graph_bot.publish.youtube --key population
```

- The first real run opens a browser to authorize. A token is cached at
  `config/youtube_token.json` so later runs are non-interactive.
- Uploaded videos are **private** by default. Review them in
  [YouTube Studio](https://studio.youtube.com), then publish, or upload with
  `--privacy public` once you trust the output.

## Notes

- `config/client_secret.json` and `config/youtube_token.json` are secrets — they are
  gitignored. Never commit or share them.
- Videos are 1080×1920 and typically under 60s, so YouTube treats them as **Shorts**
  automatically; the `#Shorts` tag in the title reinforces it.
