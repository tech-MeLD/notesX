insert into public.rss_sources (
  slug,
  title,
  feed_url,
  site_url,
  category,
  tags,
  source_priority,
  fetch_interval_minutes,
  is_active
)
values
  (
    'techcrunch',
    'TechCrunch',
    'https://techcrunch.com/feed/',
    'https://techcrunch.com/',
    'technology',
    '{}'::text[],
    5,
    15,
    true
  ),
  (
    'ars-technica',
    'Ars Technica',
    'https://feeds.arstechnica.com/arstechnica/index',
    'https://arstechnica.com/',
    'technology',
    '{}'::text[],
    4,
    20,
    true
  ),
  (
    'the-verge',
    'The Verge',
    'https://www.theverge.com/rss/index.xml',
    'https://www.theverge.com/',
    'technology',
    '{}'::text[],
    4,
    20,
    true
  ),
  (
    'hacker-news',
    'Hacker News',
    'https://news.ycombinator.com/rss',
    'https://news.ycombinator.com/',
    'technology',
    '{}'::text[],
    5,
    15,
    true
  ),
  (
    'reuters-business',
    'Reuters Business',
    'https://www.reuters.com/business/rss',
    'https://www.reuters.com/business/',
    'finance',
    '{}'::text[],
    5,
    20,
    true
  ),
  (
    'cnbc-finance',
    'CNBC Finance',
    'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664',
    'https://www.cnbc.com/finance/',
    'finance',
    '{}'::text[],
    4,
    20,
    true
  ),
  (
    'investing-com',
    'Investing.com',
    'https://www.investing.com/rss/news.rss',
    'https://www.investing.com/news/',
    'finance',
    '{}'::text[],
    4,
    20,
    true
  ),
  (
    'imf-blog',
    'IMF Blog',
    'https://www.imf.org/news/rss',
    'https://www.imf.org/en/Blogs',
    'economy',
    '{}'::text[],
    4,
    30,
    true
  ),
  (
    'marginal-revolution',
    'Marginal Revolution',
    'https://marginalrevolution.com/feed',
    'https://marginalrevolution.com/',
    'economy',
    '{}'::text[],
    5,
    20,
    true
  )
on conflict (slug)
do update set
  title = excluded.title,
  feed_url = excluded.feed_url,
  site_url = excluded.site_url,
  category = excluded.category,
  tags = excluded.tags,
  source_priority = excluded.source_priority,
  fetch_interval_minutes = excluded.fetch_interval_minutes,
  is_active = excluded.is_active,
  updated_at = timezone('utc', now());

delete from public.rss_sources
where slug = 'nyt-homepage';
