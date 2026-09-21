# Data schema (planned)

> **Starter scaffold, pending Reddit API approval.** `main.py` creates these two
> SQLite tables, but no Reddit data has been collected: the tables stay empty
> until Reddit approves Data API access for this project. The database file
> (`reddit_ads_learning.db`) is local only and git-ignored.

All text comes from public posts and comments. Timestamps are ISO 8601 in UTC.
Scores and comment counts are whatever Reddit reported at `fetched_at`, and
they change over time.

## `posts`

| Field | Type | Description |
| --- | --- | --- |
| `post_id` | text, primary key | Reddit's base-36 post ID |
| `subreddit` | text | Subreddit name, without the `r/` prefix |
| `title` | text | Post title |
| `body` | text | Post text. Empty for link and image posts |
| `created_at` | text | When the post was created |
| `score` | integer | Post score when fetched |
| `comment_count` | integer | Reddit's comment count when fetched. Can be higher than the number of comments stored |
| `permalink` | text | Full `https://www.reddit.com/r/...` link to the post |
| `fetched_at` | text | When this row was last refreshed from the API |

## `comments`

| Field | Type | Description |
| --- | --- | --- |
| `comment_id` | text, primary key | Reddit's base-36 comment ID |
| `post_id` | text | The post this comment belongs to (`posts.post_id`) |
| `parent_id` | text | Reddit "fullname" of the parent: `t3_<post_id>` for a top-level comment, `t1_<comment_id>` for a reply |
| `comment_body` | text | Comment text |
| `comment_score` | integer | Comment score when fetched |
| `comment_depth` | integer | 0 for a top-level comment, 1 for a reply to it, and so on |
| `created_at` | text | When the comment was created |
| `permalink` | text | Full link to the comment on Reddit |
| `fetched_at` | text | When this row was last refreshed from the API |

At most `MAX_COMMENTS_PER_POST` comments are kept per post, top-level comments
first. Collapsed "load more comments" threads are not expanded, which keeps
each post to a single API request.

## Optional learning labels (stored on `posts`)

These exist only to help organize reading. They are produced by fixed keyword
rules or typed in by hand, and are never used to train or evaluate any model.

| Field | Filled by | Values |
| --- | --- | --- |
| `platform` | `categorize_post()` | `meta_ads`, `google_ads`, `microsoft_ads`, `tiktok_ads`, `linkedin_ads`, `multiple`, or empty |
| `topic` | `categorize_post()` | The topic with the most keyword hits: `creative`, `targeting`, `lead_generation`, `landing_pages`, `conversion_tracking`, `metrics`, `budget_bidding`, or empty |
| `subtopic` | hand | A finer label of your choice within the topic, such as `lookalike audiences` under `targeting` |
| `industry` | hand | The business type the post is about, when it says, such as `home services` or `ecommerce` |
| `metric_type` | `categorize_post()` | The first ad metric named with a number: `CTR`, `CPC`, `CPM`, `CPA`, `CPL`, `ROAS`, `CVR`, or empty |
| `metric_value` | `categorize_post()` | That number as written, such as `$2.40`, `1.8%` or `3.1x`. Stored as text because units vary |
| `usefulness_score` | hand | 1 to 5, how useful the thread was for learning (1 = not useful, 5 = worth re-reading) |

Re-running the script refreshes the automatic labels but never overwrites the
hand-filled ones.

## Not stored, on purpose

- Usernames, user IDs, profile data, or anything used to follow a person
- Posts or comments marked `[deleted]` or `[removed]`, or content from
  private communities
- Images, videos, or other media files
- Voting data about any user
