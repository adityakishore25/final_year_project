import streamlit as st
import praw
from typing import List, Dict
from operator import itemgetter
import re
import io
from xhtml2pdf import pisa
import html
import requests
from PIL import Image
import base64
from io import BytesIO
import tempfile
import os

## Set to your production values (or use Streamlit secrets)
#APP_ID = "D2wBQZzXWeMlGU95UcR8HA"
#APP_SECRET = "o_GLz9rvt-Rdn4-HizSyde-qICjOTA"
#USER_AGENT = "reddit-analyzer by u/Miserable-Meet5365"
APP_ID = "D2wBQZzXWeMlGU95UcR8H"
APP_SECRET = "o_GLz9rvt-Rdn4-HizSyde-qICjOT"
USER_AGENT = "reddit-analyzer by u/Miserable-Meet536"

## --- Feature Configuration ---
# Basic list - expand this significantly for real-world use
POTENTIALLY_MALICIOUS_WORDS = {
    "idiot", "stupid", "hate", "kill", "attack", "dumb", "sexy"
    # Add many more words, including variations, slang, etc.
}

# --- Utility Functions ---

def escape_html(text: str) -> str:
    """Escapes HTML special characters."""
    return html.escape(text or "")

def highlight_text(text: str, words_to_highlight: set, color="red") -> str:
    """Highlights specified words (case-insensitive) in a given text using HTML spans."""
    if not text or not words_to_highlight:
        return escape_html(text) # Return escaped text if no highlighting needed

    # Escape the text first to prevent issues with existing HTML-like content
    escaped_text = escape_html(text)

    # Create a regex pattern for case-insensitive whole or partial word matching
    try:
        # Ensure words are valid for regex (e.g., not empty)
        valid_words = [re.escape(word) for word in words_to_highlight if word]
        if not valid_words:
             return escaped_text # No valid words to highlight

        pattern = r'(' + '|'.join(valid_words) + r')'
        # Use re.sub with a lambda to wrap matches
        highlighted_text = re.sub(
            pattern,
            lambda m: f'<span style="color: {color}; font-weight: bold;">{m.group(0)}</span>',
            escaped_text,
            flags=re.IGNORECASE
        )
        return highlighted_text
    except re.error as e:
        st.warning(f"Regex error during highlighting: {e}. Returning unhighlighted text.")
        return escaped_text # Return escaped text on regex error

def highlight_username(text: str, username: str, color="purple") -> str:
    """Highlights username mentions in text."""
    if not text or not username:
        return escape_html(text)
    
    escaped_text = escape_html(text)
    pattern = r'(u/' + re.escape(username) + r'|' + re.escape(username) + r')'
    
    try:
        highlighted_text = re.sub(
            pattern,
            lambda m: f'<span style="color: {color}; font-weight: bold;">{m.group(0)}</span>',
            escaped_text,
            flags=re.IGNORECASE
        )
        return highlighted_text
    except re.error:
        return escaped_text

def download_image(url: str) -> str:
    """Downloads an image and returns base64 encoded data for embedding in HTML."""
    try:
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            # Create a temporary file to save the image
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_file:
                temp_file_path = temp_file.name
                for chunk in response.iter_content(1024):
                    temp_file.write(chunk)
            
            # Open the image with PIL to resize if needed
            with Image.open(temp_file_path) as img:
                # Resize if too large (optional)
                max_width = 800
                if img.width > max_width:
                    ratio = max_width / img.width
                    new_height = int(img.height * ratio)
                    img = img.resize((max_width, new_height), Image.LANCZOS)
                
                # Convert to base64
                buffered = BytesIO()
                img.save(buffered, format="JPEG")
                img_str = base64.b64encode(buffered.getvalue()).decode()
            
            # Clean up the temporary file
            os.unlink(temp_file_path)
            
            return f"data:image/jpeg;base64,{img_str}"
        else:
            return ""
    except Exception as e:
        st.warning(f"Error downloading image: {str(e)}")
        return ""

# --- Reddit Interaction ---

def search_reddit_user_posts(reddit: praw.Reddit, username: str, num_posts: int) -> List[Dict]:
    """Search Reddit for posts by a specific username."""
    user_posts = []
    try:
        redditor = reddit.redditor(username)
        # Check if redditor exists by accessing an attribute; raises exception if not found
        _ = redditor.id
        st.write(f"Fetching posts for user: {redditor.name}...") # Use redditor.name for correct casing

        # Fetch submissions (can change sort: new, hot, top)
        submissions = redditor.submissions.new(limit=num_posts)

        for post in submissions:
            # Check if post has an image
            image_url = ""
            if hasattr(post, 'url') and post.url.endswith(('.jpg', '.jpeg', '.png', '.gif')):
                image_url = post.url
            
            post_data = {
                "title": post.title,
                "score": post.score,
                "url": post.url,
                "subreddit": post.subreddit.display_name,
                "selftext": post.selftext,
                "created_utc": post.created_utc,
                "id": post.id,
                "is_potentially_malicious": False, # Flag for malicious content
                "malicious_words_found": set(),    # Store found words
                "keywords_found": set(),           # Store found keywords
                "image_url": image_url,            # Store image URL if available
                "comments": []                     # Will store comments
            }
            
            # Fetch comments for this post
            post.comments.replace_more(limit=0)  # Replace MoreComments objects with actual comments
            for comment in post.comments.list():
                comment_data = {
                    "author": str(comment.author) if comment.author else "[deleted]",
                    "body": comment.body,
                    "score": comment.score,
                    "is_potentially_malicious": False,
                    "malicious_words_found": set(),
                    "keywords_found": set(),
                }
                post_data["comments"].append(comment_data)
            
            user_posts.append(post_data)

        # Sort posts by score (or date: key=itemgetter("created_utc"))
        return sorted(user_posts, key=itemgetter("score"), reverse=True)

    except praw.exceptions.NotFound:
        st.error(f"Reddit user '{username}' not found.")
        return []
    except Exception as e:
        st.error(f"Error fetching posts for user '{username}': {str(e)}")
        return []

# --- Content Analysis ---

def analyze_post_content(
    posts: List[Dict],
    keywords: List[str],
    scan_malicious: bool
) -> List[Dict]:
    """Scans post content and comments for keywords and potentially malicious words."""
    keyword_set = {kw.strip().lower() for kw in keywords if kw.strip()} # Prepare keywords

    for post in posts:
        # Combine title and selftext for scanning, convert to lowercase
        content_to_scan = (post['title'].lower() if post['title'] else "") + " " + (post['selftext'].lower() if post['selftext'] else "")

        # Scan for malicious words if requested
        if scan_malicious:
            for word in POTENTIALLY_MALICIOUS_WORDS:
                 # Use regex findall for case-insensitive check within the text (ensure word is not empty)
                if word and re.search(r'\b' + re.escape(word) + r'\b', content_to_scan, re.IGNORECASE):
                    post['is_potentially_malicious'] = True
                    post['malicious_words_found'].add(word) # Store the base word found

        # Scan for keywords
        for keyword in keyword_set:
             # Ensure keyword is not empty before searching
             if keyword and re.search(r'\b' + re.escape(keyword) + r'\b', content_to_scan, re.IGNORECASE):
                post['keywords_found'].add(keyword) # Store the keyword found
        
        # Analyze comments
        for comment in post['comments']:
            comment_content = comment['body'].lower() if comment['body'] else ""
            
            # Scan comments for malicious words
            if scan_malicious:
                for word in POTENTIALLY_MALICIOUS_WORDS:
                    if word and re.search(r'\b' + re.escape(word) + r'\b', comment_content, re.IGNORECASE):
                        comment['is_potentially_malicious'] = True
                        comment['malicious_words_found'].add(word)
            
            # Scan comments for keywords
            for keyword in keyword_set:
                if keyword and re.search(r'\b' + re.escape(keyword) + r'\b', comment_content, re.IGNORECASE):
                    comment['keywords_found'].add(keyword)

    return posts


# --- PDF Output Generation ---

def generate_pdf_report(
    username: str,
    analyzed_posts: List[Dict],
    keywords: List[str],
    scanned_malicious: bool
) -> bytes | None:
    """Generates a PDF report with highlighted keywords and malicious words."""

    html_content = f"""
    <html>
    <head>
        <title>Reddit User Analysis: {escape_html(username)}</title>
        <style>
            body {{ font-family: sans-serif; }}
            h1, h2, h3 {{ color: #333; }}
            .post {{ border-bottom: 1px solid #eee; margin-bottom: 15px; padding-bottom: 10px; }}
            .metadata {{ font-size: 0.9em; color: #666; }}
            .highlight-malicious {{ color: red; font-weight: bold; }}
            .highlight-keyword {{ color: blue; font-weight: bold; }}
            .label {{ font-weight: bold; }}
            .content {{ white-space: pre-wrap; word-wrap: break-word; }}
            .comment {{ margin-left: 20px; border-left: 3px solid #ccc; padding-left: 10px; margin-top: 10px; }}
            .comment-author {{ font-weight: bold; color: #555; }}
            .post-image {{ max-width: 100%; height: auto; margin: 10px 0; }}
        </style>
    </head>
    <body>
        <h1>Reddit User Analysis: '{escape_html(username)}'</h1>
        <p>Number of posts analyzed: {len(analyzed_posts)}</p>
        <p>Keywords searched: {escape_html(', '.join(keywords)) if keywords else 'None'}</p>
        <p>Malicious word scan enabled: {'Yes' if scanned_malicious else 'No'}</p>
        <hr>

        <h2>Analyzed Posts (Sorted by Score)</h2>
    """

    words_to_highlight_malicious = POTENTIALLY_MALICIOUS_WORDS if scanned_malicious else set()
    words_to_highlight_keywords = {kw.strip() for kw in keywords if kw.strip()}

    for post in analyzed_posts:
        # Combine all words that need highlighting for this post for easier processing
        all_highlight_terms = set()
        if scanned_malicious and post['is_potentially_malicious']:
            # Use the actual words found for more precise highlighting
            all_highlight_terms.update(post['malicious_words_found'])
        if post['keywords_found']:
             # Use the actual keywords found
            all_highlight_terms.update(post['keywords_found'])

        # Highlight Title - use red for any highlight in main text for simplicity
        highlighted_title = highlight_text(post['title'], all_highlight_terms, color="red")
        # Also highlight username mentions
        highlighted_title = highlight_username(highlighted_title, username)

        # Highlight Selftext - use red for any highlight in main text for simplicity
        highlighted_selftext = highlight_text(post['selftext'], all_highlight_terms, color="red")
        # Also highlight username mentions
        highlighted_selftext = highlight_username(highlighted_selftext, username)

        # --- FIX: Perform replace BEFORE f-string insertion and use actual newline ---
        formatted_selftext_for_html = highlighted_selftext.replace('\n', '<br>')
        # --- End Fix ---

        html_content += f"""
        <div class="post">
            <h3><a href="{escape_html(post['url'])}">{highlighted_title}</a></h3>
            <p class="metadata">
                Subreddit: r/{escape_html(post['subreddit'])} | Score: {post['score']} | Post ID: {post['id']}
            </p>
            <div class="content">
                {formatted_selftext_for_html}
            </div>
        """
        
        # Add image if available
        if post['image_url']:
            # Download and embed the image
            img_data = download_image(post['image_url'])
            if img_data:
                html_content += f'<img src="{img_data}" class="post-image" alt="Post image"><br>'
            else:
                html_content += f'<p><a href="{escape_html(post["image_url"])}" target="_blank">View Image</a></p>'
        
        # Add labels if issues were found
        if scanned_malicious and post['is_potentially_malicious']:
            found_words_str = ', '.join(escape_html(w) for w in post['malicious_words_found'])
            html_content += f'<p><span class="label" style="color: red;">Malicious words detected:</span> {found_words_str}</p>'
        if post['keywords_found']:
            found_words_str = ', '.join(escape_html(w) for w in post['keywords_found'])
            html_content += f'<p><span class="label" style="color: blue;">Keywords detected:</span> {found_words_str}</p>'
        
        # Add comments section
        if post['comments']:
            html_content += f"<h4>Comments ({len(post['comments'])})</h4>"
            
            for comment in post['comments']:
                # Prepare highlighting for comment
                comment_highlight_terms = set()
                if scanned_malicious and comment['is_potentially_malicious']:
                    comment_highlight_terms.update(comment['malicious_words_found'])
                if comment['keywords_found']:
                    comment_highlight_terms.update(comment['keywords_found'])
                
                # Highlight comment text
                highlighted_comment = highlight_text(comment['body'], comment_highlight_terms, color="red")
                # Also highlight username mentions
                highlighted_comment = highlight_username(highlighted_comment, username)
                # Highlight the comment author if it matches the analyzed username
                author_display = comment['author']
                if comment['author'].lower() == username.lower():
                    author_display = f'<span style="color: purple; font-weight: bold;">{escape_html(comment["author"])}</span>'
                
                formatted_comment = highlighted_comment.replace('\n', '<br>')
                
                html_content += f"""
                <div class="comment">
                    <p class="comment-author">{author_display} • Score: {comment['score']}</p>
                    <div class="content">{formatted_comment}</div>
                """
                
                # Add labels for comment if issues were found
                if scanned_malicious and comment['is_potentially_malicious']:
                    found_words_str = ', '.join(escape_html(w) for w in comment['malicious_words_found'])
                    html_content += f'<p><span class="label" style="color: red;">Malicious words detected:</span> {found_words_str}</p>'
                if comment['keywords_found']:
                    found_words_str = ', '.join(escape_html(w) for w in comment['keywords_found'])
                    html_content += f'<p><span class="label" style="color: blue;">Keywords detected:</span> {found_words_str}</p>'
                
                html_content += "</div>" # Close comment div
        
        html_content += "</div>" # Close post div

    html_content += """
    </body>
    </html>
    """

    # Generate PDF
    pdf_buffer = io.BytesIO()
    # Ensure encoding is set to UTF-8 for broader character support
    pisa_status = pisa.CreatePDF(io.StringIO(html_content), dest=pdf_buffer, encoding='utf-8')

    if pisa_status.err:
        st.error(f"Error generating PDF: {pisa_status.err}")
        return None
    else:
        pdf_buffer.seek(0)
        return pdf_buffer.getvalue()


# --- Main Streamlit App ---

def main():
    st.set_page_config(page_title="Reddit User Analyzer", layout="wide")
    st.title("Reddit User Post Analyzer")

    # --- Basic Password Protection ---
    # Use Streamlit secrets for password in production: st.secrets["app_password"]
    APP_PASSWORD = "planet" # CHANGE THIS!
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        password_input = st.text_input("Enter App Password", type="password")
        if st.button("Login"):
            if password_input == APP_PASSWORD:
                st.session_state.logged_in = True
                st.rerun() # Use st.rerun instead of experimental_rerun
            else:
                st.error("Incorrect password.")
        st.info("Enter the password configured for this application to proceed.")
        st.stop() # Stop execution if not logged in
    # --- End Basic Password Protection ---


    st.write(
        "Analyze recent posts by a specific Reddit user. Optionally scan for keywords and potentially malicious language."
    )

    # Sidebar for configurations
    with st.sidebar:
        st.header("Settings")

        # Reddit API credentials display (read-only)
        st.subheader("Reddit API Credentials")
        st.text(f"App ID: ...{APP_ID[-4:]}") # Show only last 4 chars
        st.text(f"User Agent: {USER_AGENT}")
        st.caption("These are developer credentials used by the app.")


        # Number of posts to analyze
        st.subheader("Analysis Options")
        num_posts = st.slider(
            "Number of recent posts to fetch", min_value=5, max_value=100, value=25
        )

        # Malicious Scan Option
        scan_malicious = st.checkbox("Scan for potentially malicious words", value=True)
        if scan_malicious:
            st.caption(f"Using a predefined list of {len(POTENTIALLY_MALICIOUS_WORDS)} words.")


    # Main content area
    st.header("User & Keyword Input")

    username = st.text_input("Enter Reddit Username (case-sensitive)", key="username_input")
    keywords_input = st.text_input("Enter Keywords to search for (comma-separated)", key="keywords_input")

    if st.button("Analyze User Posts", key="analyze_button"):
        if not username:
            st.warning("Please enter a Reddit username.")
            return

        # Prepare keywords list
        keywords = [kw.strip() for kw in keywords_input.split(',') if kw.strip()]

        with st.spinner(f"Fetching and analyzing posts for user '{username}'..."):
            try:
                # Initialize Reddit client (consider doing this only once if app structure allows)
                reddit = praw.Reddit(
                    client_id=APP_ID, client_secret=APP_SECRET, user_agent=USER_AGENT,
                    # Added read_only=True as we are only fetching data
                    read_only=True
                )

                # 1. Fetch user posts
                user_posts = search_reddit_user_posts(reddit, username, num_posts)
                if not user_posts:
                    # Error messages are handled within the search function
                    # st.warning(f"No posts found or user '{username}' could not be accessed.") # Already shown in search func
                    return # Stop if no posts

                # 2. Analyze content for keywords and malicious words
                analyzed_posts = analyze_post_content(user_posts, keywords, scan_malicious)

                # Display summary results in the app
                st.subheader("Analysis Summary")
                malicious_count = sum(1 for post in analyzed_posts if post['is_potentially_malicious'])
                keyword_count = sum(1 for post in analyzed_posts if post['keywords_found'])
                
                # Count comments with issues
                comment_malicious_count = 0
                comment_keyword_count = 0
                total_comments = 0
                
                for post in analyzed_posts:
                    total_comments += len(post['comments'])
                    for comment in post['comments']:
                        if comment['is_potentially_malicious']:
                            comment_malicious_count += 1
                        if comment['keywords_found']:
                            comment_keyword_count += 1

                st.metric("Total Posts Analyzed", len(analyzed_posts))
                st.metric("Total Comments Analyzed", total_comments)
                
                col1, col2 = st.columns(2)
                with col1:
                    if scan_malicious:
                        st.metric("Posts Flagged (Malicious)", malicious_count)
                    st.metric("Posts with Keywords", keyword_count)
                
                with col2:
                    if scan_malicious:
                        st.metric("Comments Flagged (Malicious)", comment_malicious_count)
                    st.metric("Comments with Keywords", comment_keyword_count)

                # 3. Generate PDF report
                st.subheader("Download Report")
                pdf_data = generate_pdf_report(username, analyzed_posts, keywords, scan_malicious)

                if pdf_data:
                    st.download_button(
                        label="Download Analysis Report (PDF)",
                        data=pdf_data,
                        file_name=f"reddit_analysis_{username}.pdf",
                        mime="application/pdf",
                    )
                else:
                    st.error("Failed to generate PDF report.")

            except Exception as e:
                st.error(f"An unexpected error occurred during analysis: {str(e)}")


if __name__ == "__main__":
    main()