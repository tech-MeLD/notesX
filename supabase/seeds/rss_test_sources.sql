insert into public.rss_sources (
  slug,
  title,
  feed_url,
  site_url,
  tags,
  source_priority,
  fetch_interval_minutes,
  is_active
)
values
  (
    'hacker-news',
    'Hacker News',
    'https://news.ycombinator.com/rss',
    'https://news.ycombinator.com/',
    array['tech', 'startup', 'programming'],
    5,
    15,
    true
  ),
  (
    'nyt-homepage',
    'The New York Times | Home Page',
    'https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml',
    'https://www.nytimes.com/',
    array['news', 'world', 'media'],
    4,
    20,
    true
  )
on conflict (slug)
do update set
  title = excluded.title,
  feed_url = excluded.feed_url,
  site_url = excluded.site_url,
  tags = excluded.tags,
  source_priority = excluded.source_priority,
  fetch_interval_minutes = excluded.fetch_interval_minutes,
  is_active = excluded.is_active,
  updated_at = timezone('utc', now());
