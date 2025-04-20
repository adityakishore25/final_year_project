# pip install playwright requests
# playwright install chromium

from playwright.sync_api import sync_playwright
import json
import time
import logging
import os
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import Queue, Process, Manager
import argparse
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("twitter_scraper.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def scrape_twitter_info(url, boolean_user, timeout=60):
    """Scrape a single tweet or user profile."""
    _xhr_calls = []
    start_time = time.time()

    def intercept_response(response):
        if response.request.resource_type == "xhr":
            _xhr_calls.append(response)
        return response
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)  # Use headless for server deployment
            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            )
            page = context.new_page()

            page.on("response", intercept_response)
            
            # Try to handle redirects and different URL formats
            logger.info(f"Navigating to: {url}")
            
            # Set a timeout for navigation
            page.goto(url, timeout=timeout * 1000)  # Convert seconds to milliseconds
            
            # If URL redirected, note the new URL
            current_url = page.url
            if current_url != url:
                logger.info(f"Redirected to: {current_url}")

            if boolean_user:
                selector = "[data-testid='primaryColumn']"
                xhr_condition = "UserBy"
                json_condition = "user"
            else:
                selector = "[data-testid='tweet']"
                xhr_condition = "TweetResultByRestId"
                json_condition = "tweetResult"

            # Wait for selector with timeout
            page.wait_for_selector(selector, timeout=timeout * 1000)
            
            # Find matching XHR calls
            usercalls = [f for f in _xhr_calls if xhr_condition in f.url]
            
            if not usercalls:
                logger.warning(f"No matching XHR calls found for {url}")
                
                # If we can't find the right XHR calls, try to get data from HTML
                if not boolean_user:
                    logger.info("Attempting to extract tweet data from HTML")
                    try:
                        # Extract tweet text from HTML as fallback
                        tweet_text_elem = page.query_selector("[data-testid='tweetText']")
                        tweet_text = tweet_text_elem.inner_text() if tweet_text_elem else ""
                        
                        # Extract tweet ID from URL
                        tweet_id = url.split("/")[-1]
                        
                        # Extract username from URL
                        username = url.split("/")[-3]
                        
                        # Create a basic result dictionary
                        basic_result = {
                            "rest_id": tweet_id,
                            "legacy": {
                                "full_text": tweet_text,
                                "created_at": "Unknown date"  # We don't have this info
                            },
                            "core": {
                                "user_results": {
                                    "result": {
                                        "legacy": {
                                            "name": username,
                                            "screen_name": username
                                        }
                                    }
                                }
                            }
                        }
                        
                        # Try to get media
                        media_elements = page.query_selector_all("img[src*='pbs.twimg.com/media']")
                        if media_elements:
                            media_urls = [elem.get_attribute("src") for elem in media_elements if elem.get_attribute("src")]
                            
                            if media_urls:
                                # Add media to result
                                basic_result["legacy"]["entities"] = {
                                    "media": [
                                        {
                                            "type": "photo",
                                            "media_url_https": url
                                        } for url in media_urls
                                    ]
                                }
                        
                        browser.close()
                        return basic_result
                    except Exception as e:
                        logger.error(f"Error extracting tweet data from HTML: {e}")
                
                browser.close()
                return None
                
            for uc in usercalls:
                try:
                    data = uc.json()
                    result = data['data'][json_condition]['result']
                    browser.close()
                    return result
                except Exception as e:
                    logger.error(f"Error parsing XHR response: {e}")
            
            browser.close()
            return None
            
    except Exception as e:
        logger.error(f"Error scraping {url}: {e}")
        if 'browser' in locals():
            browser.close()
        return None
    finally:
        elapsed = time.time() - start_time
        logger.info(f"Scraping {url} took {elapsed:.2f} seconds")

def extract_tweet_urls_from_profile(username, max_tweets=50):
    """Extract tweet URLs from a user's profile."""
    # Try both x.com and twitter.com URLs
    profile_urls = [f"https://x.com/{username}", f"https://twitter.com/{username}"]
    tweet_urls = []
    _xhr_calls = []
    
    def intercept_response(response):
        if response.request.resource_type == "xhr":
            _xhr_calls.append(response)
        return response
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            )
            page = context.new_page()
            
            # Start intercepting responses
            page.on("response", intercept_response)
            
            # Try both URL formats
            profile_url = None
            for url in profile_urls:
                try:
                    logger.info(f"Trying to navigate to {url}")
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(5000)
                    
                    # Check if we loaded the profile page
                    if page.query_selector("[data-testid='primaryColumn']") is not None:
                        profile_url = url
                        logger.info(f"Successfully loaded profile at {url}")
                        break
                except Exception as e:
                    logger.warning(f"Failed to load {url}: {e}")
            
            if not profile_url:
                logger.error(f"Could not load profile for user: {username}")
                browser.close()
                return tweet_urls
                
            # Determine base URL for tweets (same domain as profile)
            base_url = profile_url.split("/")[0] + "//" + profile_url.split("/")[2]
            logger.info(f"Using base URL: {base_url}")
            
            # Scroll and collect tweet IDs
            scroll_count = min(max_tweets // 10 + 1, 10)  # Reasonable limit on scrolls
            
            # Process UserTweets XHR calls to extract tweet IDs
            for i in range(scroll_count):
                logger.info(f"Scroll {i+1}/{scroll_count}")
                
                # Look for UserTweets XHR responses
                user_tweets_calls = [call for call in _xhr_calls if "UserTweets" in call.url]
                
                for call in user_tweets_calls:
                    try:
                        data = call.json()
                        if "data" in data and "user" in data["data"] and "result" in data["data"]["user"]:
                            timeline = data["data"]["user"]["result"]["timeline"]["timeline"]
                            
                            if "instructions" in timeline:
                                for instruction in timeline["instructions"]:
                                    if "entries" in instruction:
                                        for entry in instruction["entries"]:
                                            if "content" in entry and "itemContent" in entry["content"]:
                                                item = entry["content"]["itemContent"]
                                                if "tweet_results" in item and "result" in item["tweet_results"]:
                                                    tweet = item["tweet_results"]["result"]
                                                    if "rest_id" in tweet:
                                                        tweet_id = tweet["rest_id"]
                                                        # Use the same base URL we successfully loaded
                                                        tweet_url = f"{base_url}/{username}/status/{tweet_id}"
                                                        if tweet_url not in tweet_urls:
                                                            tweet_urls.append(tweet_url)
                                                            logger.info(f"Found tweet: {tweet_url}")
                                                            
                                                            # Exit if we have enough tweets
                                                            if len(tweet_urls) >= max_tweets:
                                                                browser.close()
                                                                return tweet_urls
                    except Exception as e:
                        logger.error(f"Error processing XHR call: {e}")
                
                # Clear processed XHR calls
                _xhr_calls = []
                
                # Scroll down to load more tweets
                page.evaluate("window.scrollBy(0, window.innerHeight)")
                page.wait_for_timeout(3000)
            
            browser.close()
            return tweet_urls
            
    except Exception as e:
        logger.error(f"Error extracting tweet URLs: {e}")
        if 'browser' in locals():
            browser.close()
        return tweet_urls

def worker_process(task_queue, result_dict, worker_id):
    """Worker process to scrape tweets from the queue."""
    logger.info(f"Worker {worker_id} started")
    
    while not task_queue.empty():
        try:
            url = task_queue.get(block=False)
            logger.info(f"Worker {worker_id} processing: {url}")
            
            # Scrape the tweet
            result = scrape_twitter_info(url, boolean_user=False)
            
            if result:
                # Extract tweet ID from URL
                tweet_id = url.split("/")[-1]
                result_dict[tweet_id] = result
                logger.info(f"Worker {worker_id} completed: {url}")
            else:
                logger.warning(f"Worker {worker_id} failed to get data for: {url}")
                
        except Exception as e:
            logger.error(f"Worker {worker_id} error: {e}")
            continue
    
    logger.info(f"Worker {worker_id} finished")

def bulk_scrape_tweets(username, output_dir="tweets", num_workers=4, max_tweets=50):
    """
    Scrape multiple tweets from a user's profile using multiple processes.
    
    Args:
        username: Twitter username
        output_dir: Directory to save results
        num_workers: Number of worker processes
        max_tweets: Maximum number of tweets to scrape
    """
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Extract tweet URLs from profile
    logger.info(f"Extracting tweet URLs for user: {username}")
    tweet_urls = extract_tweet_urls_from_profile(username, max_tweets)
    logger.info(f"Found {len(tweet_urls)} tweets")
    
    if not tweet_urls:
        logger.error(f"No tweets found for user: {username}")
        return False
    
    # Create a manager for sharing data between processes
    with Manager() as manager:
        # Create a shared dictionary to store results
        result_dict = manager.dict()
        
        # Create a queue of tasks (URLs)
        task_queue = Queue()
        for url in tweet_urls:
            task_queue.put(url)
        
        # Start worker processes
        processes = []
        for i in range(min(num_workers, len(tweet_urls))):
            p = Process(target=worker_process, args=(task_queue, result_dict, i))
            processes.append(p)
            p.start()
        
        # Wait for all processes to complete
        for p in processes:
            p.join()
        
        # Convert manager dict to regular dict for JSON serialization
        results = dict(result_dict)
        
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(output_dir, f"{username}_tweets_{timestamp}.json")
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4)
    
    logger.info(f"Scraped {len(results)} tweets and saved to {output_file}")
    return output_file

def main():
    parser = argparse.ArgumentParser(description="Twitter Tweet Scraper")
    parser.add_argument("--username", "-u", required=True, help="Twitter username to scrape")
    parser.add_argument("--output", "-o", default="tweets", help="Output directory")
    parser.add_argument("--workers", "-w", type=int, default=4, help="Number of worker processes")
    parser.add_argument("--max", "-m", type=int, default=8, help="Maximum number of tweets to scrape")
    
    args = parser.parse_args()
    
    logger.info(f"Starting bulk scrape for user: {args.username}")
    output_file = bulk_scrape_tweets(
        args.username, 
        output_dir=args.output,
        num_workers=args.workers,
        max_tweets=args.max
    )
    
    if output_file:
        logger.info(f"Results saved to: {output_file}")
    else:
        logger.error("Scraping failed")

if __name__ == "__main__":
    main()