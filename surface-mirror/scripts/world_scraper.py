import feedparser
import datetime
import os

# Configuration
FEEDS = [
    'https://news.google.com/rss/search?q=artificial+intelligence&hl=en-US&gl=US&ceid=US:en',
    'https://www.theverge.com/rss/index.xml',
    'https://techcrunch.com/feed/'
]
LOG_FILE = r"C:\Users\KING\.ultron\watchdog\live_world_feed.log"
OUTPUT_DIR = r"C:\Users\KING\.ultron\watchdog"

def fetch_and_append():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] Starting feed scrape...")
    
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        for url in FEEDS:
            try:
                print(f"Fetching {url}...")
                feed = feedparser.parse(url)
                entries_added = 0
                for entry in feed.entries:
                    # We only append if it's relatively new (though for a simple log we just take recent)
                    # In a real prod system, we'd check the published date against the last entry time
                    line = f"[{timestamp}] [{entry.get('title', 'No Title')}] - {entry.link}\n"
                    f.write(line)
                    entries_added += 1
                print(f"Added {entries_added} entries from {url}")
            except Exception as e:
                print(f"Error fetching {url}: {e}")

if __name__ == "__main__":
    fetch_and_append()
