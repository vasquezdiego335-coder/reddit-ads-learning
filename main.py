"""
reddit-ads-learning: a personal, read-only Reddit Data API learning tool.

STARTER SCAFFOLD, PENDING REDDIT API APPROVAL.
Reddit requires developers to request Data API access and be approved before
using it. Approval for this project is still pending, so no credentials exist
yet. Until approved credentials are placed in a local .env file, this script
sends no requests to Reddit: it reports what is missing and exits.

Once access is approved and configured, one run will:
  1. read the newest public posts from a short list of advertising subreddits,
  2. read the public comments under each post,
  3. tag each post with simple keyword-based labels (no machine learning),
  4. save posts and comments, with their Reddit permalinks, to a local SQLite
     file that is git-ignored and never published.

It never posts, comments, votes, sends messages, logs in as a Reddit user, or
stores usernames.

The Reddit-facing functions have not been run against the live API yet,
because access is not approved. Expect small fixes on the first real run.
"""

from __future__ import annotations

import os
import re
import sqlite3
import sys
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import praw
from dotenv import load_dotenv
from prawcore.exceptions import (  # prawcore is installed together with praw
    Forbidden,
    NotFound,
    PrawcoreException,
    Redirect,
)

# --- Settings -----------------------------------------------------------------

# Public subreddits to study. Edit the list to suit what you want to learn, and
# read each community's rules before collecting from it.
SUBREDDITS = [
    "PPC",
    "FacebookAds",
    "googleads",
    "adwords",
    "digital_marketing",
]

POSTS_PER_SUBREDDIT = 10     # newest posts read from each subreddit per run
MAX_COMMENTS_PER_POST = 50   # comments kept per post, top-level comments first

PROJECT_DIR = Path(__file__).resolve().parent
ENV_PATH = PROJECT_DIR / ".env"
DATABASE_PATH = PROJECT_DIR / "reddit_ads_learning.db"  # *.db is git-ignored

REQUIRED_SETTINGS = ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT")

NOT_CONFIGURED_MESSAGE = """\
Reddit Data API access is not configured, so nothing was sent to Reddit.

This repository is a starter scaffold. Reddit requires developers to request
Data API access and be approved before using it, and approval for this project
is still pending.

After Reddit approves access:
  1. copy .env.example to .env
  2. fill in REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET and REDDIT_USER_AGENT
  3. run: python main.py

Missing now: {missing}"""

REJECTED_MESSAGE = """\
Reddit rejected the request: {error}

Check that Reddit has approved Data API access for this app and that the
values in .env match the approved app exactly. The run stopped here."""

# Posts and comments whose text is one of these were deleted by their author
# or removed by moderators. They are never stored.
UNAVAILABLE_TEXT = {"[deleted]", "[removed]"}

# --- Keyword labels -----------------------------------------------------------
# categorize_post() uses these fixed keyword lists. It is plain string
# matching: no model is trained on, or fed, any Reddit content.

PLATFORM_KEYWORDS = {
    "meta_ads": ["meta ads", "facebook ads", "fb ads", "instagram ads", "ads manager", "advantage+"],
    "google_ads": ["google ads", "adwords", "performance max", "pmax", "youtube ads"],
    "microsoft_ads": ["microsoft ads", "bing ads"],
    "tiktok_ads": ["tiktok ads"],
    "linkedin_ads": ["linkedin ads"],
}

TOPIC_KEYWORDS = {
    "creative": ["creative", "ad copy", "headline", "ugc", "video ad", "image ad", "hook"],
    "targeting": ["targeting", "audience", "lookalike", "retargeting", "remarketing", "keyword", "negative keyword"],
    "lead_generation": ["lead gen", "lead generation", "lead", "lead form", "instant form"],
    "landing_pages": ["landing page", "page speed", "bounce rate"],
    "conversion_tracking": ["pixel", "conversion tracking", "conversions api", "capi", "enhanced conversions",
                            "tag manager", "gtm", "ga4", "offline conversion"],
    "metrics": ["ctr", "cpc", "cpm", "cpa", "cpl", "roas", "conversion rate", "cost per"],
    "budget_bidding": ["budget", "bid strategy", "bidding", "target cpa", "target roas", "max conversions"],
}

_METRIC_NAME = r"(ctr|cpc|cpm|cpa|cpl|roas|cvr)"
_METRIC_VALUE = r"([$€£]?\d[\d,]*(?:\.\d+)?(?:\s?(?:%|x(?!\w)))?)"
# "CPC of $2.40", "ROAS is 3.1x"
_METRIC_NAME_FIRST = re.compile(rf"(?<!\w){_METRIC_NAME}(?!\w)[^\d$€£\n]{{0,20}}{_METRIC_VALUE}", re.IGNORECASE)
# "$2.40 CPC", "1.8% CTR"
_METRIC_VALUE_FIRST = re.compile(rf"(?<![\w.]){_METRIC_VALUE}\s?{_METRIC_NAME}(?!\w)", re.IGNORECASE)


# --- Configuration and client -------------------------------------------------

def load_config() -> dict[str, str | None]:
    """Read the three Reddit settings from .env (if present) or the environment.

    Returns every required setting, with None for any that are missing or empty.
    Nothing here contacts Reddit.
    """
    load_dotenv(ENV_PATH)
    return {name: (os.getenv(name) or "").strip() or None for name in REQUIRED_SETTINGS}


def create_reddit_client(config: dict[str, str | None]) -> praw.Reddit:
    """Build a read-only PRAW client from approved credentials.

    Only called once all three settings are present. PRAW connects lazily, so
    building the client sends nothing; the first fetch does.
    """
    reddit = praw.Reddit(
        client_id=config["REDDIT_CLIENT_ID"],
        client_secret=config["REDDIT_CLIENT_SECRET"],
        user_agent=config["REDDIT_USER_AGENT"],
        check_for_updates=False,  # otherwise PRAW asks PyPI for a newer version here
    )
    # Application-only access: no Reddit username or password is ever used, and
    # a read-only client cannot post, comment, vote, or send messages.
    reddit.read_only = True
    return reddit


# --- Fetching (runs only after API approval) ----------------------------------

def fetch_recent_posts(reddit: praw.Reddit, subreddit_name: str, limit: int) -> tuple[list[dict], list[str]]:
    """Return (available_posts, unavailable_post_ids) from a subreddit's newest posts.

    Deleted or removed posts are never read into a record. Their IDs are
    returned so any copy saved on an earlier run can be forgotten.
    """
    posts, unavailable_ids = [], []
    for submission in reddit.subreddit(subreddit_name).new(limit=limit):
        if getattr(submission, "removed_by_category", None) or submission.selftext in UNAVAILABLE_TEXT:
            unavailable_ids.append(submission.id)
            continue
        posts.append({
            "post_id": submission.id,
            "subreddit": submission.subreddit.display_name,
            "title": submission.title,
            "body": submission.selftext,  # empty for link and image posts
            "created_at": _utc_iso(submission.created_utc),
            "score": submission.score,
            "comment_count": submission.num_comments,
            "permalink": "https://www.reddit.com" + submission.permalink,
        })
    return posts, unavailable_ids


def fetch_post_comments(reddit: praw.Reddit, post_id: str, max_comments: int) -> list[dict]:
    """Return up to max_comments public comments on a post, top-level comments first.

    Collapsed "load more comments" links are dropped rather than expanded, so
    each post costs one API request. Deleted and removed comments are skipped;
    their public replies are still kept.
    """
    submission = reddit.submission(id=post_id)
    submission.comments.replace_more(limit=0)

    records = []
    queue = deque((comment, 0) for comment in submission.comments)
    while queue and len(records) < max_comments:
        comment, depth = queue.popleft()
        queue.extend((reply, depth + 1) for reply in comment.replies)
        if comment.body in UNAVAILABLE_TEXT:
            continue
        records.append({
            "comment_id": comment.id,
            "post_id": post_id,
            "parent_id": comment.parent_id,  # "t3_<post_id>" or "t1_<comment_id>"
            "comment_body": comment.body,
            "comment_score": comment.score,
            "comment_depth": depth,          # 0 = top-level reply to the post
            "created_at": _utc_iso(comment.created_utc),
            "permalink": "https://www.reddit.com" + comment.permalink,
        })
    return records


def _utc_iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat(timespec="seconds")


# --- Learning labels ----------------------------------------------------------

def categorize_post(post: dict) -> dict[str, str | None]:
    """Label a post with platform, topic and the first ad metric it mentions.

    Keyword matching only, so treat every label as a hint to check while
    reading. subtopic, industry and usefulness_score are left for you to fill
    in by hand (see schema.md); the script never overwrites them.
    """
    text = f"{post['title']}\n{post['body']}".lower()

    platforms = [name for name, words in PLATFORM_KEYWORDS.items() if _count_hits(text, words)]
    topic_hits = {name: _count_hits(text, words) for name, words in TOPIC_KEYWORDS.items()}
    best_topic = max(topic_hits, key=topic_hits.get)
    metric_type, metric_value = _first_metric(text)

    return {
        "platform": platforms[0] if len(platforms) == 1 else ("multiple" if platforms else None),
        "topic": best_topic if topic_hits[best_topic] else None,
        "metric_type": metric_type,
        "metric_value": metric_value,
    }


def _count_hits(text: str, keywords: list[str]) -> int:
    # Whole words only, with an optional plural "s": "lead" matches "leads", not "leader".
    return sum(len(re.findall(rf"(?<!\w){re.escape(word)}s?(?!\w)", text)) for word in keywords)


def _first_metric(text: str) -> tuple[str | None, str | None]:
    matches = []
    if found := _METRIC_NAME_FIRST.search(text):
        matches.append((found.start(), found.group(1), found.group(2)))
    if found := _METRIC_VALUE_FIRST.search(text):
        matches.append((found.start(), found.group(2), found.group(1)))
    if not matches:
        return None, None
    _, name, value = min(matches)
    return name.upper(), value.replace(" ", "")


# --- Local storage ------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS posts (
    post_id          TEXT PRIMARY KEY,
    subreddit        TEXT NOT NULL,
    title            TEXT NOT NULL,
    body             TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    score            INTEGER,
    comment_count    INTEGER,
    permalink        TEXT NOT NULL,
    fetched_at       TEXT NOT NULL,
    platform         TEXT,     -- set by categorize_post()
    topic            TEXT,     -- set by categorize_post()
    metric_type      TEXT,     -- set by categorize_post()
    metric_value     TEXT,     -- set by categorize_post()
    subtopic         TEXT,     -- filled in by hand
    industry         TEXT,     -- filled in by hand
    usefulness_score INTEGER   -- filled in by hand, 1 to 5
);

CREATE TABLE IF NOT EXISTS comments (
    comment_id    TEXT PRIMARY KEY,
    post_id       TEXT NOT NULL REFERENCES posts(post_id),
    parent_id     TEXT NOT NULL,
    comment_body  TEXT NOT NULL,
    comment_score INTEGER,
    comment_depth INTEGER NOT NULL,
    created_at    TEXT NOT NULL,
    permalink     TEXT NOT NULL,
    fetched_at    TEXT NOT NULL
);
"""


def open_database(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_SQL)
    return conn


def save_post(conn: sqlite3.Connection, post: dict, comments: list[dict], labels: dict) -> None:
    """Insert or refresh one post and replace its stored comments.

    Replacing the comment set means a comment deleted on Reddit since the last
    run is also deleted here. Hand-entered labels on the post are kept.
    """
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with conn:
        conn.execute(
            """
            INSERT INTO posts (post_id, subreddit, title, body, created_at, score, comment_count,
                               permalink, fetched_at, platform, topic, metric_type, metric_value)
            VALUES (:post_id, :subreddit, :title, :body, :created_at, :score, :comment_count,
                    :permalink, :fetched_at, :platform, :topic, :metric_type, :metric_value)
            ON CONFLICT (post_id) DO UPDATE SET
                title = excluded.title,
                body = excluded.body,
                score = excluded.score,
                comment_count = excluded.comment_count,
                fetched_at = excluded.fetched_at,
                platform = excluded.platform,
                topic = excluded.topic,
                metric_type = excluded.metric_type,
                metric_value = excluded.metric_value
            """,
            {**post, **labels, "fetched_at": fetched_at},
        )
        conn.execute("DELETE FROM comments WHERE post_id = ?", (post["post_id"],))
        conn.executemany(
            """
            INSERT INTO comments (comment_id, post_id, parent_id, comment_body, comment_score,
                                  comment_depth, created_at, permalink, fetched_at)
            VALUES (:comment_id, :post_id, :parent_id, :comment_body, :comment_score,
                    :comment_depth, :created_at, :permalink, :fetched_at)
            """,
            [{**comment, "fetched_at": fetched_at} for comment in comments],
        )


def forget_post(conn: sqlite3.Connection, post_id: str) -> None:
    """Delete a post and its comments, used when the post is now deleted on Reddit."""
    with conn:
        conn.execute("DELETE FROM comments WHERE post_id = ?", (post_id,))
        conn.execute("DELETE FROM posts WHERE post_id = ?", (post_id,))


# --- Entry point --------------------------------------------------------------

def main() -> int:
    config = load_config()
    missing = [name for name, value in config.items() if not value]
    if missing:
        # The normal state until Reddit approves access: stop before any request.
        print(NOT_CONFIGURED_MESSAGE.format(missing=", ".join(missing)))
        return 1

    reddit = create_reddit_client(config)
    conn = open_database(DATABASE_PATH)
    saved_posts = saved_comments = 0
    try:
        for subreddit_name in SUBREDDITS:
            try:
                posts, unavailable_ids = fetch_recent_posts(reddit, subreddit_name, POSTS_PER_SUBREDDIT)
            except (Forbidden, NotFound, Redirect):
                print(f"Skipping r/{subreddit_name}: it is private, banned, or does not exist.")
                continue
            for post_id in unavailable_ids:
                forget_post(conn, post_id)
            for post in posts:
                comments = fetch_post_comments(reddit, post["post_id"], MAX_COMMENTS_PER_POST)
                save_post(conn, post, comments, categorize_post(post))
                saved_posts += 1
                saved_comments += len(comments)
    except PrawcoreException as error:
        print(REJECTED_MESSAGE.format(error=error))
        return 1
    finally:
        conn.close()

    print(f"Saved {saved_posts} posts and {saved_comments} comments to {DATABASE_PATH.name}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
