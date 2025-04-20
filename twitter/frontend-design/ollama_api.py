import requests
import logging
import time

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OllamaAPI:
    """Simple client for interacting with Ollama API."""
    
    def __init__(self, base_url="http://localhost:11434", model="llama3.2:1b"):
        """
        Initialize the Ollama API client.
        
        Args:
            base_url: Ollama API base URL (default: http://localhost:11434)
            model: Model to use (default: llama2)
        """
        self.base_url = base_url
        self.model = model
        self.generate_endpoint = f"{base_url}/api/generate"
        
        # Check if Ollama is running
        try:
            requests.get(f"{base_url}/api/tags", timeout=2)
            logger.info(f"Connected to Ollama at {base_url}")
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
                error_msg = f"Error from Ollama API: {response.status_code} {response.text}"
                logger.error(error_msg)
                return f"API Error: {response.status_code}"
                
        except requests.exceptions.Timeout:
            logger.error(f"Request to Ollama timed out after {timeout} seconds")
            return "Request timed out. Try a simpler prompt or check Ollama's status."
            
        except Exception as e:
            logger.error(f"Error generating response from Ollama: {str(e)}")
            return f"Error: {str(e)}"
    
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
    

