from flask import Flask, render_template, request, jsonify, send_from_directory
import os
import json
import logging
import shutil
import base64
import requests
from PIL import Image
import io
import re
from vqa_model import extract_text_from_image, answer_question, analyze_tweet_text

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Folders for storing data
UPLOAD_FOLDER = 'uploads'
IMAGES_FOLDER = 'images'
PDF_FOLDER = 'pdfs'

# Create folders if they don't exist
for folder in [UPLOAD_FOLDER, IMAGES_FOLDER, PDF_FOLDER]:
    os.makedirs(folder, exist_ok=True)

@app.route('/')
def index():
    """Main page."""
    return render_template('index.html')

@app.route('/twitter_json', methods=['GET', 'POST'])
def twitter_json():
    """Handle Twitter JSON scraping."""
    if request.method == 'POST':
        username = request.form.get('username', '')
        scroll_count = request.form.get('scroll_count', 5, type=int)
        
        if not username:
            return render_template('twitter_json.html', error='Please enter a valid username')
        
        # Call the scraping script with subprocess
        try:
            import subprocess
            cmd = ['python', 'scraper.py', '--username', username, '--max', str(scroll_count)]
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()
            
            if process.returncode != 0:
                logger.error(f"Error running scraper: {stderr.decode('utf-8')}")
                return render_template('twitter_json.html', error=f"Error running scraper: {stderr.decode('utf-8')[:500]}")
                
            # Return with success message
            return render_template('twitter_json.html', success=f"Successfully downloaded data for @{username}")
            
        except Exception as e:
            logger.error(f"Error: {str(e)}")
            return render_template('twitter_json.html', error=f"Error: {str(e)}")
    
    return render_template('twitter_json.html')

@app.route('/tweet_analysis', methods=['GET', 'POST'])
def tweet_analysis():
    """Handle tweet analysis from JSON file."""
    if request.method == 'POST':
        # Check if a file was uploaded
        if 'tweet_json' not in request.files:
            return render_template('tweet_analysis.html', error='No file selected')
            
        file = request.files['tweet_json']
        
        # Check if the file is empty
        if file.filename == '':
            return render_template('tweet_analysis.html', error='No file selected')
            
        # Check if the file is a JSON file
        if not file.filename.endswith('.json'):
            return render_template('tweet_analysis.html', error='Please upload a JSON file')
            
        # Save the file
        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)
        
        try:
            # Read the JSON file
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Check if the file format is correct
            if not isinstance(data, dict):
                return render_template('tweet_analysis.html', error='Invalid JSON format')
                
            # Extract tweet data
            tweets = []
            for tweet_id, tweet_data in data.items():
                # Handle different tweet formats
                if "legacy" in tweet_data:
                    # Extract user info
                    user_info = None
                    if "core" in tweet_data and "user_results" in tweet_data["core"]:
                        user_info = tweet_data["core"]["user_results"]["result"]["legacy"]
                    
                    # Extract text
                    text = tweet_data["legacy"].get("full_text", "")
                    
                    # Create tweet object
                    tweet = {
                        "id": tweet_id,
                        "text": text,
                        "created_at": tweet_data["legacy"].get("created_at", ""),
                        "user": user_info["name"] if user_info else "Unknown",
                        "username": user_info["screen_name"] if user_info else "Unknown"
                    }
                    tweets.append(tweet)
                else:
                    # Fallback for alternative format
                    logger.warning(f"Alternative tweet format for {tweet_id}")
                    tweet = {
                        "id": tweet_id,
                        "text": str(tweet_data),
                        "created_at": "Unknown",
                        "user": "Unknown",
                        "username": "Unknown"
                    }
                    tweets.append(tweet)
            
            # Render the template with tweets
            return render_template('tweet_analysis.html', tweets=tweets, success=f"Found {len(tweets)} tweets")
            
        except Exception as e:
            logger.error(f"Error processing JSON: {str(e)}")
            return render_template('tweet_analysis.html', error=f"Error processing JSON: {str(e)}")
    
    return render_template('tweet_analysis.html')



@app.route('/ask_tweet', methods=['POST'])
def ask_tweet():
    """Handle questions about tweets."""
    tweet_id = request.form.get('tweet_id')
    tweet_text = request.form.get('tweet_text')
    tweet_user = request.form.get('tweet_user')
    tweet_username = request.form.get('tweet_username')
    tweet_created_at = request.form.get('tweet_created_at')
    question = request.form.get('question')
    
    logger.info(f"Tweet question: {question} for tweet {tweet_id}")
    
    if not tweet_id or not question:
        return jsonify({"error": "Missing tweet_id or question"}), 400
    
    try:
        # Create a tweet object
        tweet = {
            "id": tweet_id,
            "text": tweet_text,
            "user": tweet_user,
            "username": tweet_username,
            "created_at": tweet_created_at
        }
        
        # Analyze the tweet
        answer = analyze_tweet_text(tweet, question)
        
        return jsonify({
            "tweet_id": tweet_id,
            "question": question,
            "answer": answer
        })
    
    except Exception as e:
        logger.error(f"Error analyzing tweet: {str(e)}")
        return jsonify({"error": f"Error analyzing tweet: {str(e)}"}), 500
    

@app.route('/tweet_images', methods=['GET', 'POST'])
def tweet_images():
    """Handle image extraction from tweets."""
    if request.method == 'POST':
        # Check if a file was uploaded
        if 'tweet_json' not in request.files:
            return render_template('tweet_images.html', error='No file selected')
            
        file = request.files['tweet_json']
        
        # Check if the file is empty
        if file.filename == '':
            return render_template('tweet_images.html', error='No file selected')
            
        # Check if the file is a JSON file
        if not file.filename.endswith('.json'):
            return render_template('tweet_images.html', error='Please upload a JSON file')
            
        # Save the file
        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)
        
        try:
            # Read the JSON file
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Check if the file format is correct
            if not isinstance(data, dict):
                return render_template('tweet_images.html', error='Invalid JSON format')
                
            # Extract tweet data with media
            tweets_with_media = []
            all_images = []
            
            for tweet_id, tweet_data in data.items():
                # Check if tweet has media
                has_media = False
                media_items = []
                
                # Handle different tweet formats
                if "legacy" in tweet_data:
                    # Check for media in entities
                    if "entities" in tweet_data["legacy"] and "media" in tweet_data["legacy"]["entities"]:
                        for media in tweet_data["legacy"]["entities"]["media"]:
                            if media["type"] == "photo":
                                media_url = media.get("media_url_https", "")
                                if media_url:
                                    has_media = True
                                    media_items.append({
                                        "type": "photo",
                                        "url": media_url
                                    })
                    
                    # Extract user info
                    user_info = None
                    if "core" in tweet_data and "user_results" in tweet_data["core"]:
                        user_info = tweet_data["core"]["user_results"]["result"]["legacy"]
                    
                    if has_media:
                        # Create tweet object with media
                        tweet = {
                            "id": tweet_id,
                            "text": tweet_data["legacy"].get("full_text", ""),
                            "created_at": tweet_data["legacy"].get("created_at", ""),
                            "user": user_info["name"] if user_info else "Unknown",
                            "username": user_info["screen_name"] if user_info else "Unknown",
                            "media": media_items
                        }
                        tweets_with_media.append(tweet)
                
            # Download and save all images
            for tweet in tweets_with_media:
                for i, media_item in enumerate(tweet["media"]):
                    try:
                        media_url = media_item["url"]
                        img_filename = f"{tweet['id']}_{i}.jpg"
                        img_path = os.path.join(IMAGES_FOLDER, img_filename)
                        
                        # Download the image
                        response = requests.get(media_url, stream=True)
                        if response.status_code == 200:
                            with open(img_path, 'wb') as f:
                                response.raw.decode_content = True
                                shutil.copyfileobj(response.raw, f)
                            
                            # Make file readable by all
                            try:
                                os.chmod(img_path, 0o644)
                            except Exception as e:
                                logger.warning(f"Could not set permissions on {img_path}: {e}")
                            
                            # Add to list of images
                            all_images.append({
                                "tweet_id": tweet["id"],
                                "path": img_path,
                                "filename": img_filename
                            })
                            
                            # Add path to media item
                            media_item["local_path"] = img_path
                            
                            logger.info(f"Downloaded image: {img_path}")
                        else:
                            logger.warning(f"Failed to download image: {media_url}")
                            
                    except Exception as e:
                        logger.error(f"Error downloading image: {str(e)}")
            
            # Render the template with tweets that have media
            return render_template(
                'tweet_images.html', 
                tweets=tweets_with_media, 
                images=all_images,
                success=f"Found {len(tweets_with_media)} tweets with media and {len(all_images)} images"
            )
            
        except Exception as e:
            logger.error(f"Error processing JSON: {str(e)}")
            return render_template('tweet_images.html', error=f"Error processing JSON: {str(e)}")
    
    return render_template('tweet_images.html')

@app.route("/ask_image", methods=["POST"])
def ask_image():
    """Handle visual QA for tweet images."""
    image_path = request.form.get("image_path")
    question = request.form.get("question")
    
    logger.info(f"Received image question. Path: {image_path}, Question: {question}")
    
    if not image_path or not question:
        logger.error("Missing image_path or question")
        return jsonify({"error": "Missing image_path or question"}), 400
    
    try:
        # Verify image path exists
        if not os.path.exists(image_path):
            logger.error(f"Image not found: {image_path}")
            
            # Try relative path as fallback
            filename = os.path.basename(image_path)
            alt_path = os.path.join(IMAGES_FOLDER, filename)
            
            if os.path.exists(alt_path):
                logger.info(f"Found image at alternate path: {alt_path}")
                image_path = alt_path
            else:
                logger.error(f"Image not found at alternate path either: {alt_path}")
                return jsonify({"error": f"Image not found at: {image_path}"}), 404
        
        # Load the image
        logger.info(f"Loading image from: {image_path}")
        image = Image.open(image_path)
        
        # Use the VQA model to answer the question
        logger.info(f"Analyzing image with question: {question}")
        answer = answer_question(image, question)
        logger.info(f"Generated answer: {answer}")
        
        return jsonify({
            "image_path": image_path,
            "question": question,
            "answer": answer
        })
    
    except Exception as e:
        logger.error(f"Error in visual QA: {str(e)}", exc_info=True)
        return jsonify({"error": f"Error processing image: {str(e)}"}), 500
    
    
@app.route('/images/<filename>')
def serve_image(filename):
    """Serve images from the images folder."""
    return send_from_directory(IMAGES_FOLDER, filename)

@app.route('/uploads/<filename>')
def serve_upload(filename):
    """Serve files from the uploads folder."""
    return send_from_directory(UPLOAD_FOLDER, filename)

if __name__ == '__main__':
    app.run(debug=True)