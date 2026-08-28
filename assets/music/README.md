# Background music — put your tracks here

Drop audio files (`.mp3`, `.wav`, `.m4a`, `.ogg`, `.flac`, `.opus`) into this folder.
The pipeline picks one per topic (deterministically) and mixes it under the video with
a fade in/out. Toggle and tune it in `config/settings.yaml` under `audio:`.

## ⚠️ Only use music you're licensed to use

Social platforms run **Content ID** on every upload. Using commercial/popular songs will
get the video muted, blocked, demonetized, or the account struck. Use only royalty-free,
Creative Commons, or public-domain music **that allows commercial use**.

### Safe, free sources

| Source | License | Attribution | Link |
|---|---|---|---|
| YouTube Audio Library | Free for use | Sometimes | studio.youtube.com → Audio Library |
| Pixabay Music | Royalty-free | No | https://pixabay.com/music/ |
| Free Music Archive | CC0 / CC-BY (varies) | Varies | https://freemusicarchive.org/ |
| Incompetech (Kevin MacLeod) | CC-BY | Yes (credit) | https://incompetech.com/music/ |
| ccMixter | CC (varies) | Varies | http://ccmixter.org/ |

### Notes

- **CC0 / "no attribution"** tracks are simplest — nothing extra to do.
- **CC-BY** requires crediting the artist. Put the credit in the video caption; you can
  add it to a topic's `hashtags`/description or the caption template.
- Even royalty-free tracks can appear in Content ID as a *benign* match (credits the
  composer, no strike). YouTube's own Audio Library avoids even that — safest for Shorts.
- Prefer calm/ambient/lo-fi instrumental for a "soothing" feel; 30–60s+ tracks are fine
  since anything shorter is looped automatically to cover the video.

This folder's audio files are gitignored — they stay on your machine only.
