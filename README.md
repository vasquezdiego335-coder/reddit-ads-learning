# reddit-ads-learning

> **Status: starter scaffold. Reddit Data API approval is pending.**
> This repository contains no API credentials. Authenticated Reddit Data API
> access will be turned on only after Reddit approves it. Until then, running
> the script sends nothing to Reddit. It explains what is missing and exits.

## Purpose

A private, read-only, personal learning tool for studying public Reddit
discussions about paid advertising:

- Meta Ads and Google Ads, and PPC in general
- ad creative and targeting
- lead generation and landing pages
- conversion tracking
- advertising metrics (CTR, CPC, CPM, CPA, CPL, ROAS)

It is for my own learning. It is not a product, a service, or a dataset.

## What it will do (once approved)

- **Read only.** It reads recent public posts and their public comments from a
  short, editable list of advertising subreddits, using the official Reddit
  Data API through [PRAW](https://praw.readthedocs.io/) in read-only mode.
- **Organize by topic.** Each post gets simple keyword-based labels (platform,
  topic, and the first ad metric it mentions) so posts can be browsed by
  subject. These are plain keyword rules, not machine learning.
- **Keep Reddit permalinks.** Every saved post and comment keeps its permalink,
  so each note points back to the original discussion on Reddit.
- **Stay local.** Everything is saved to a SQLite file on my own computer. That
  file is git-ignored, so Reddit content is never committed to this repository
  or published anywhere.

## What it will never do

- Post, comment, vote, or send messages. The client runs in PRAW's read-only
  mode and never logs in as a Reddit user.
- Message, track, or profile users. Usernames are not collected or stored.
- Access private or deleted content. Private communities are skipped, and
  posts or comments marked `[deleted]` or `[removed]` are never stored.
- Sell, license, or share datasets built from Reddit content.
- Train, fine-tune, or evaluate an AI model on Reddit content.
- Scrape Reddit web pages, or work around API rate limits. All access goes
  through the official API, and PRAW waits when Reddit's rate-limit headers
  say to. Default request volumes are deliberately small.

## Reddit API approval

Reddit requires developers to request Data API access and receive approval
before using it (see Reddit's
[Responsible Builder Policy](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy),
[Data API Terms](https://redditinc.com/policies/data-api-terms) and
[Developer Terms](https://redditinc.com/policies/developer-terms)).

For this project, that approval is **pending**. Until it is granted:

- `.env.example` holds empty placeholders only;
- `main.py` checks for credentials before doing anything else, and exits with
  a clear message when they are missing;
- the Reddit-facing code has not been run against the live API, so expect
  small fixes on the first real run.

## Setup

Requires Python 3.10 or newer.

```bash
python -m venv .venv
```

Activate it (`source .venv/bin/activate` on macOS or Linux,
`.venv\Scripts\activate` on Windows), then install the dependencies:

```bash
pip install -r requirements.txt
```

Running the script now, before approval, prints the "not configured" message:

```bash
python main.py
```

**After Reddit approves access**, copy `.env.example` to `.env` and fill in the
three values for the approved app. `REDDIT_USER_AGENT` should be a unique,
descriptive string in the format Reddit asks for, for example
`script:reddit-ads-learning:v0.1.0 (by /u/<your-reddit-username>)`. The `.env`
file is git-ignored and must never be committed.

## Files

| File | What it is |
| --- | --- |
| `main.py` | The whole tool: config check, read-only client, fetch, keyword labels, SQLite storage |
| `schema.md` | Planned fields for posts and comments, plus the optional learning labels |
| `requirements.txt` | PRAW and python-dotenv |
| `.env.example` | Empty placeholders for the three Reddit settings |
| `.gitignore` | Keeps `.env`, virtual environments, caches and `*.db` out of git |

## Known gaps

- Deleted content is handled only for posts that are re-read. A stored post
  deleted on Reddit is removed from the local database the next time it shows
  up in a subreddit's newest posts. Posts that have already dropped out of that
  window are not re-checked yet. A `prune` step that re-checks older posts is
  planned and should exist before any regular use.
- The keyword labels are rough hints. Always read the linked discussion.
