import os
import json
import requests
from dotenv import load_dotenv
import tweepy
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Twitter credentials
BEARER_TOKEN = os.getenv("BEARER_TOKEN")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
ACCESS_SECRET = os.getenv("ACCESS_SECRET")
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

# Gemini API key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Validate required environment variables
required_vars = [
    "API_KEY", "API_SECRET", 
    "ACCESS_TOKEN", "ACCESS_SECRET", "GEMINI_API_KEY"
]

missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    raise ValueError(f"Missing required environment variables: {missing_vars}")

# Initialize Twitter client
twitter_client = tweepy.Client(
    bearer_token=BEARER_TOKEN,
    consumer_key=API_KEY,
    consumer_secret=API_SECRET,
    access_token=ACCESS_TOKEN,
    access_token_secret=ACCESS_SECRET,
)

class HistoryBot:
    def __init__(self):
        self.gemini_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
        self.headers = {
            'Content-Type': 'application/json',
            'X-goog-api-key': GEMINI_API_KEY
        }
        
    def get_formatted_date(self):
        """Get formatted date string (e.g., 'Aug 14th')"""
        today = datetime.now()
        month_name = today.strftime("%b")
        day = today.day
        
        # Add ordinal suffix
        if 10 <= day % 100 <= 20:
            suffix = 'th'
        else:
            suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
        
        return f"{month_name} {day}{suffix}"
        
    def fetch_historical_events(self):
        """Fetch historical events for today's date"""
        try:
            today = datetime.now()
            url = f"https://byabbe.se/on-this-day/{today.month}/{today.day}/events.json"
            
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            events = data.get("events", [])
            
            # Format events for better processing
            formatted_events = []
            for event in events:
                formatted_events.append(f"{event['year']}: {event['description']}")
            
            logger.info(f"Fetched {len(formatted_events)} events for {today.month}/{today.day}")
            return formatted_events
            
        except requests.RequestException as e:
            logger.error(f"Error fetching events: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return []
    
    def generate_tweet_with_gemini(self, events):
        """Generate tweet using Gemini 2.0 Flash"""
        if not events:
            return None
            
        events_text = "\n".join(events)
        formatted_date = self.get_formatted_date()
        
        prompt = f"""Create a Twitter post about historical events that happened on this day.

EXACT FORMAT REQUIRED:
📅 {formatted_date} in history:
• YEAR — Brief description of event
• YEAR — Brief description of event  
• YEAR — Brief description of event
#OTD #History

RULES:
- Start with "📅 {formatted_date} in history:"
- Use bullet points with • symbol
- Format each event as "YEAR — description"
- Select 3 interesting but lesser-known events (avoid the most famous ones)
- Keep descriptions very brief to fit under 280 characters total
- End with "#OTD #History"
- Make sure the entire tweet is under 280 characters

Historical events for today:
{events_text}

Generate only the tweet text in the exact format shown above:"""

        payload = {
            "contents": [{
                "parts": [{
                    "text": prompt
                }]
            }],
            "generationConfig": {
                "temperature": 0.7,
                "topK": 40,
                "topP": 0.9,
                "maxOutputTokens": 300,
            }
        }
        
        try:
            response = requests.post(
                self.gemini_url,
                headers=self.headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            
            if 'candidates' in result and result['candidates']:
                tweet_text = result['candidates'][0]['content']['parts'][0]['text'].strip()
                
                # Ensure tweet is within character limit
                if len(tweet_text) > 280:
                    logger.warning(f"Generated tweet too long ({len(tweet_text)} chars)")
                    # Try to truncate gracefully
                    lines = tweet_text.split('\n')
                    if len(lines) >= 4:  # Header + 3 events + hashtags
                        # Remove one event and try again
                        tweet_text = '\n'.join(lines[:3] + lines[-1:])
                        if len(tweet_text) > 280:
                            tweet_text = tweet_text[:277] + "..."
                
                logger.info(f"Generated tweet ({len(tweet_text)} chars): {tweet_text}")
                return tweet_text
            else:
                logger.error("No content generated by Gemini")
                return None
                
        except requests.RequestException as e:
            logger.error(f"Error calling Gemini API: {e}")
            return None
        except Exception as e:
            logger.error(f"Error processing Gemini response: {e}")
            return None
    
    def post_tweet(self, text):
        """Post tweet to Twitter"""
        if not text:
            logger.error("No text provided for tweet")
            return False
            
        try:
            response = twitter_client.create_tweet(text=text)
            tweet_id = response.data['id']
            tweet_url = f"https://twitter.com/user/status/{tweet_id}"
            
            logger.info(f"✅ Tweet posted successfully: {tweet_url}")
            return True
            
        except tweepy.TooManyRequests:
            logger.error("❌ Twitter API rate limit exceeded")
            return False
        except tweepy.Forbidden:
            logger.error("❌ Twitter API access forbidden - check credentials")
            return False
        except Exception as e:
            logger.error(f"❌ Error posting tweet: {e}")
            return False
    
    def run(self):
        """Main execution function"""
        logger.info(f"🚀 Starting history bot at {datetime.now()}")
        
        # Fetch events
        events = self.fetch_historical_events()
        if not events:
            logger.warning("No events fetched, exiting")
            return False
        
        # Generate tweet
        tweet_text = self.generate_tweet_with_gemini(events)
        if not tweet_text:
            logger.warning("Failed to generate tweet, exiting")
            return False
        
        # Post tweet
        success = self.post_tweet(tweet_text)
        if success:
            logger.info("✅ Bot completed successfully")
            return True
        else:
            logger.error("❌ Bot failed to post tweet")
            return False

def main():
    """Main function - runs once and exits"""
    bot = HistoryBot()
    success = bot.run()
    exit(0 if success else 1)

if __name__ == "__main__":
    main()