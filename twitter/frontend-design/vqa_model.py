import pytesseract
from PIL import Image
import fitz  # PyMuPDF
import io
import logging
import os
import re
import requests
import time

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OllamaAPI:
    """Simple client for interacting with Ollama API."""
    
    def __init__(self, base_url="http://localhost:11434", model="llama2"):
        """
        Initialize the Ollama API client.
        
        Args:
            base_url: Ollama API base URL (default: http://localhost:11434)
            model: Model to use (default: llama2)
        """
        self.base_url = base_url
        self.model = model
        self.generate_endpoint = f"{base_url}/api/generate"
        self.available = False
        
        # Check if Ollama is running
        try:
            response = requests.get(f"{base_url}/api/tags", timeout=2)
            if response.status_code == 200:
                self.available = True
                logger.info(f"Connected to Ollama at {base_url}")
                
                # Check if model is available
                models = response.json().get("models", [])
                model_names = [m.get('name', '') for m in models]
                
                if model not in model_names and len(model_names) > 0:
                    # Use the first available model as fallback
                    self.model = model_names[0]
                    logger.warning(f"Model {model} not found, using {self.model} instead")
            else:
                logger.warning(f"Ollama returned non-200 status: {response.status_code}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Could not connect to Ollama: {e}")
            logger.warning("Make sure Ollama is running on your system")
    
    def generate(self, prompt, max_tokens=1000, temperature=0.7, timeout=60):
        """
        Generate a response from Ollama.
        
        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (higher = more creative)
            timeout: Request timeout in seconds
            
        Returns:
            Response text or error message
        """
        if not self.available:
            return "Ollama not available. Please make sure Ollama is running."
            
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens
                }
            }
            
            logger.debug(f"Sending request to Ollama: {prompt[:50]}...")
            start_time = time.time()
            
            response = requests.post(
                self.generate_endpoint,
                json=payload,
                timeout=timeout
            )
            
            elapsed = time.time() - start_time
            logger.debug(f"Ollama response received in {elapsed:.2f} seconds")
            
            if response.status_code == 200:
                result = response.json()
                return result.get("response", "No response from model")
            else:
                # Fallback to simple response if Ollama fails
                error_msg = f"Error from Ollama API: {response.status_code} {response.text}"
                logger.error(error_msg)
                
                # We'll return a custom fallback response
                return f"Unable to process with AI. Analyze the content yourself using the information provided."
                
        except requests.exceptions.Timeout:
            logger.error(f"Request to Ollama timed out after {timeout} seconds")
            return "Analysis request timed out. The tweet might be complex or Ollama might be busy."
            
        except Exception as e:
            logger.error(f"Error generating response from Ollama: {str(e)}")
            return f"Could not analyze with AI. Review the tweet content directly."
    
    def analyze_text(self, text, question, max_tokens=500):
        """
        Analyze text content with a specific question.
        
        Args:
            text: Text to analyze
            question: Question to answer about the text
            max_tokens: Maximum tokens for response
            
        Returns:
            Analysis response
        """
        # Craft a detailed prompt for analysis
        prompt = f"""
You are a helpful AI assistant analyzing social media content. 
You need to answer a question about the following text content:

TEXT CONTENT:
{text}

QUESTION: {question}

Provide a detailed, insightful analysis of the text in relation to the question.
If asked about sentiment, hate speech, or harmful content, be especially thorough in your analysis.
If the text contains hate speech or harmful content, clearly identify it.
Keep your response focused and concise.
"""
        return self.generate(prompt, max_tokens=max_tokens)
    
    def analyze_image_content(self, extracted_text, image_description, question, max_tokens=500):
        """
        Analyze image content using extracted text and basic image description.
        
        Args:
            extracted_text: Text extracted from the image using OCR
            image_description: Basic description of the image (dimensions, colors, etc.)
            question: Question to answer about the image
            max_tokens: Maximum tokens for response
            
        Returns:
            Analysis response
        """
        # Craft a detailed prompt for image analysis
        prompt = f"""
You are a helpful AI assistant analyzing social media images. 
You need to answer a question about an image based on the following information:

IMAGE DESCRIPTION: {image_description}

TEXT EXTRACTED FROM IMAGE: 
{extracted_text}

QUESTION: {question}

Provide a detailed, insightful analysis of what might be in the image based on the description and text.
If asked about sentiment, hate speech, or harmful content, be especially thorough in your analysis.
If the extracted text contains hate speech or harmful content, clearly identify it.
Be clear that your analysis is based on limited information, not the actual image.
Keep your response focused and concise.
"""
        return self.generate(prompt, max_tokens=max_tokens)

# Initialize Ollama API client
ollama_client = OllamaAPI(model="llama3.2:1b")

def extract_images_from_pdf(pdf_path):
    """Extract images from a PDF file."""
    result = []
    
    try:
        doc = fitz.open(pdf_path)
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            image_list = page.get_images(full=True)
            
            for img_index, img in enumerate(image_list):
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                
                # Convert to PIL Image
                image = Image.open(io.BytesIO(image_bytes))
                result.append(image)
                
        return result
    except Exception as e:
        logger.error(f"Error extracting images from PDF: {str(e)}")
        raise

def extract_text_from_image(image):
    """Extract text from an image using OCR."""
    try:
        # Use Tesseract OCR
        text = pytesseract.image_to_string(image)
        return text
    except Exception as e:
        logger.error(f"Error extracting text from image: {str(e)}")
        return ""

def get_image_description(image):
    """
    Get basic description of an image (size, colors, etc.)
    
    Args:
        image: PIL Image object
        
    Returns:
        String description of the image
    """
    try:
        # Get basic image properties
        width, height = image.size
        aspect_ratio = width / height if height > 0 else 0
        
        # Analyze image for dominant colors
        small_img = image.resize((50, 50))
        if small_img.mode != 'RGB':
            small_img = small_img.convert('RGB')
        
        # Get color frequencies
        colors = small_img.getcolors(50*50)
        dominant_colors = []
        
        if colors:
            # Sort by frequency (most common first)
            colors.sort(reverse=True, key=lambda x: x[0])
            # Get the most common colors
            for count, (r, g, b) in colors[:3]:  # Take top 3 colors
                # Simple color detection
                if r > 200 and g > 200 and b > 200:
                    dominant_colors.append("white")
                elif r < 50 and g < 50 and b < 50:
                    dominant_colors.append("black")
                elif r > 200 and g < 100 and b < 100:
                    dominant_colors.append("red")
                elif r < 100 and g > 200 and b < 100:
                    dominant_colors.append("green")
                elif r < 100 and g < 100 and b > 200:
                    dominant_colors.append("blue")
                elif r > 200 and g > 200 and b < 100:
                    dominant_colors.append("yellow")
                elif r > 200 and g < 100 and b > 200:
                    dominant_colors.append("purple")
                elif r > 200 and g > 100 and b < 100:
                    dominant_colors.append("orange")
                else:
                    pass  # Skip undefined colors
            
            # Remove duplicates
            dominant_colors = list(set(dominant_colors))
        
        # Determine shape/orientation
        if aspect_ratio > 1.2:
            shape = "wide/landscape"
        elif aspect_ratio < 0.8:
            shape = "tall/portrait"
        else:
            shape = "square-ish"
        
        # Build description
        description = f"This is a {width}x{height} pixel image with a {shape} orientation."
        
        if dominant_colors:
            description += f" The dominant colors appear to be: {', '.join(dominant_colors)}."
        
        return description
        
    except Exception as e:
        logger.error(f"Error analyzing image: {e}")
        return "Unable to analyze image properties"

def answer_question(image, question):
    """
    Answer a question about an image using OCR and Ollama.
    
    Args:
        image: PIL Image object
        question: String containing the question
    
    Returns:
        String containing the answer
    """
    try:
        # Extract text from the image
        extracted_text = extract_text_from_image(image)
        
        # Get basic image description
        image_description = get_image_description(image)
        
        # Determine if the question is about basic properties or needs more analysis
        basic_properties_keywords = ["size", "dimension", "width", "height", "color", "colours", "shape", "orientation"]
        needs_basic_info = any(keyword in question.lower() for keyword in basic_properties_keywords)
        
        # Is this a question about what's in the image text?
        text_question_keywords = ["say", "text", "write", "written", "word", "read"]
        is_text_question = any(keyword in question.lower() for keyword in text_question_keywords)
        
        # Check if this is a sentiment/hate speech question
        sentiment_keywords = ["sentiment", "hate", "harmful", "offensive", "toxic", "angry", "negative"]
        is_sentiment_question = any(keyword in question.lower() for keyword in sentiment_keywords)
        
        # Simple question about text content
        if is_text_question and not is_sentiment_question and extracted_text.strip():
            if len(extracted_text) > 300:
                return f"The text in the image says: {extracted_text[:297]}..."
            else:
                return f"The text in the image says: {extracted_text}"
        
        # Question about basic image properties
        elif needs_basic_info and not is_sentiment_question:
            return image_description
            
        # For all other questions, try to use Ollama
        else:
            # If no text was extracted, indicate this
            text_for_analysis = extracted_text if extracted_text.strip() else "No readable text detected in the image."
            
            if ollama_client.available:
                # Send to Ollama for analysis
                answer = ollama_client.analyze_image_content(
                    text_for_analysis, 
                    image_description, 
                    question
                )
                return answer
            else:
                # Fallback if Ollama isn't available
                if is_sentiment_question:
                    return "To analyze sentiment or detect harmful content, I need AI capabilities which aren't currently available. Here's what I can tell you: " + image_description + (f" The image contains text: {extracted_text}" if extracted_text.strip() else "")
                else:
                    if extracted_text.strip():
                        return f"I can tell you that {image_description} The image contains text that says: \"{extracted_text}\""
                    else:
                        return f"I can only provide basic information: {image_description}"
            
    except Exception as e:
        logger.error(f"Error in answer_question: {str(e)}", exc_info=True)
        return f"Sorry, I couldn't process that question: {str(e)}"

def analyze_tweet_text(tweet, question):
    """
    Analyze tweet text based on the question using Ollama.
    
    Args:
        tweet: Dictionary containing tweet data
        question: Question to answer about the tweet
        
    Returns:
        String containing the analysis
    """
    # Extract basic tweet information
    text = tweet.get("text", "")
    user = tweet.get("user", "Unknown")
    username = tweet.get("username", "Unknown")
    created_at = tweet.get("created_at", "Unknown date")
    
    # Basic who/when questions don't need Ollama
    who_patterns = ["who", "author", "wrote", "tweeted", "user"]
    when_patterns = ["when", "date", "time", "posted", "tweeted"]
    
    question_lower = question.lower()
    
    # Basic factual questions
    if any(pattern in question_lower for pattern in who_patterns) and not any(p for p in ["hate", "harmful", "sentiment"] if p in question_lower):
        return f"This tweet was written by {user} (@{username})."
    
    elif any(pattern in question_lower for pattern in when_patterns) and not any(p for p in ["hate", "harmful", "sentiment"] if p in question_lower):
        return f"This tweet was posted on {created_at}."
    
    # For all other questions, try to use Ollama for more insightful analysis
    else:
        try:
            # Create additional context for the model
            tweet_context = f"Tweet by {user} (@{username}) posted on {created_at}"
            
            # Format the full text for analysis
            full_text = f"{tweet_context}\nTweet text: {text}"
            
            if ollama_client.available:
                # Send to Ollama for analysis
                answer = ollama_client.analyze_text(full_text, question)
                return answer
            else:
                # Fallback to simple analysis
                logger.warning("Ollama not available, using fallback analysis")
                
                if "sentiment" in question_lower or "emotion" in question_lower or "feel" in question_lower:
                    # Very basic sentiment analysis
                    positive_words = ["good", "great", "awesome", "amazing", "excellent", "happy", "joy", "love", "wonderful", "fantastic"]
                    negative_words = ["bad", "awful", "terrible", "sad", "angry", "hate", "poor", "horrible", "disappointing", "worst"]
                    
                    text_lower = text.lower()
                    positive_count = sum(1 for word in positive_words if word in text_lower)
                    negative_count = sum(1 for word in negative_words if word in text_lower)
                    
                    if positive_count > negative_count:
                        return "The sentiment of this tweet appears to be positive."
                    elif negative_count > positive_count:
                        return "The sentiment of this tweet appears to be negative."
                    else:
                        return "The sentiment of this tweet appears to be neutral."
                
                elif "hate" in question_lower or "harmful" in question_lower or "offensive" in question_lower:
                    # Very basic hate speech detection
                    problematic_words = ["hate", "kill", "die", "attack", "stupid", "idiot", "dumb", "racist", "sexist"]
                    text_lower = text.lower()
                    problematic_count = sum(1 for word in problematic_words if word in text_lower)
                    
                    if problematic_count > 0:
                        return "This tweet may contain potentially inappropriate language that could be considered harmful or offensive."
                    else:
                        return "No obvious hate speech detected in this tweet, but this is a very basic analysis."
                
                elif "topic" in question_lower or "about" in question_lower or "subject" in question_lower:
                    # Return a simple analysis of what the tweet is about
                    words = text.split()
                    if len(words) > 5:
                        return f"This tweet seems to be about: {' '.join(words[:5])}..."
                    else:
                        return f"This tweet is brief but appears to be about: {text}"
                
                else:
                    # For other questions, just return the tweet content
                    return f"The tweet says: \"{text}\""
                
        except Exception as e:
            logger.error(f"Error in analyze_tweet_text: {str(e)}")
            return f"Error analyzing tweet: {str(e)}"