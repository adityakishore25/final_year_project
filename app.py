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
from datetime import datetime

## Set to your production values (or use Streamlit secrets)
APP_ID = "D2wBQZzXWeMlGU95UcR8H"
APP_SECRET = "o_GLz9rvt-Rdn4-HizSyde-qICjOTA"
USER_AGENT = "reddit-analyzer by u/Miserable-Meet536"

## --- Feature Configuration ---
POTENTIALLY_MALICIOUS_WORDS = {
    "idiot", "stupid", "hate", "kill", "attack", "dumb", "sexy"
}

# --- Utility Functions ---

def escape_html(text: str) -> str:
    """Escapes HTML special characters."""
    return html.escape(text or "")

def highlight_text(text: str, words_to_highlight: set, color="red") -> str:
    """Highlights specified words (case-insensitive) in a given text using HTML spans."""
    if not text or not words_to_highlight:
        return escape_html(text)

    escaped_text = escape_html(text)
    try:
        valid_words = [re.escape(word) for word in words_to_highlight if word]
        if not valid_words:
            return escaped_text

        pattern = r'(' + '|'.join(valid_words) + r')'
        highlighted_text = re.sub(
            pattern,
            lambda m: f'<span style="color: {color}; font-weight: bold;">{m.group(0)}</span>',
            escaped_text,
            flags=re.IGNORECASE
        )
        return highlighted_text
    except re.error as e:
        st.warning(f"Regex error during highlighting: {e}. Returning unhighlighted text.")
        return escaped_text

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
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_file:
                temp_file_path = temp_file.name
                for chunk in response.iter_content(1024):
                    temp_file.write(chunk)
            
            with Image.open(temp_file_path) as img:
                max_width = 800
                if img.width > max_width:
                    ratio = max_width / img.width
                    new_height = int(img.height * ratio)
                    img = img.resize((max_width, new_height), Image.LANCZOS)
                
                buffered = BytesIO()
                img.save(buffered, format="JPEG")
                img_str = base64.b64encode(buffered.getvalue()).decode()
            
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
        _ = redditor.id
        st.write(f"Fetching posts for user: {redditor.name}...")

        submissions = redditor.submissions.new(limit=num_posts)

        for post in submissions:
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
                "is_potentially_malicious": False,
                "malicious_words_found": set(),
                "keywords_found": set(),
                "image_url": image_url,
                "comments": []
            }
            
            post.comments.replace_more(limit=0)
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
    keyword_set = {kw.strip().lower() for kw in keywords if kw.strip()}

    for post in posts:
        content_to_scan = (post['title'].lower() if post['title'] else "") + " " + (post['selftext'].lower() if post['selftext'] else "")

        if scan_malicious:
            for word in POTENTIALLY_MALICIOUS_WORDS:
                if word and re.search(r'\b' + re.escape(word) + r'\b', content_to_scan, re.IGNORECASE):
                    post['is_potentially_malicious'] = True
                    post['malicious_words_found'].add(word)

        for keyword in keyword_set:
            if keyword and re.search(r'\b' + re.escape(keyword) + r'\b', content_to_scan, re.IGNORECASE):
                post['keywords_found'].add(keyword)
        
        for comment in post['comments']:
            comment_content = comment['body'].lower() if comment['body'] else ""
            
            if scan_malicious:
                for word in POTENTIALLY_MALICIOUS_WORDS:
                    if word and re.search(r'\b' + re.escape(word) + r'\b', comment_content, re.IGNORECASE):
                        comment['is_potentially_malicious'] = True
                        comment['malicious_words_found'].add(word)
            
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
    
    total_posts = len(analyzed_posts)
    total_comments = sum(len(post['comments']) for post in analyzed_posts)
    
    malicious_posts_count = sum(1 for post in analyzed_posts if post['is_potentially_malicious'])
    malicious_comments_count = sum(
        sum(1 for comment in post['comments'] if comment['is_potentially_malicious'])
        for post in analyzed_posts
    )
    
    keyword_posts_count = sum(1 for post in analyzed_posts if post['keywords_found'])
    keyword_comments_count = sum(
        sum(1 for comment in post['comments'] if comment['keywords_found'])
        for post in analyzed_posts
    )
    
    all_malicious_words = set()
    for post in analyzed_posts:
        all_malicious_words.update(post['malicious_words_found'])
        for comment in post['comments']:
            all_malicious_words.update(comment['malicious_words_found'])
    
    current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html_content = f"""
    <html>
    <head>
        <title>Reddit User Analysis: {escape_html(username)}</title>
        <style>
            body {{ font-family: sans-serif; margin: 20px; }}
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
            .summary-box {{ 
                border: 1px solid #ddd; 
                padding: 15px; 
                margin-bottom: 20px; 
                background-color: #f9f9f9;
                border-radius: 5px;
            }}
            .warning {{ color: red; font-weight: bold; }}
            .stat-grid {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 10px;
                margin-bottom: 15px;
            }}
            .stat-item {{
                padding: 8px;
                border: 1px solid #eee;
                border-radius: 4px;
            }}
            .stat-label {{ font-weight: bold; }}
            .stat-value {{ font-size: 1.2em; }}
            .malicious-stat {{ color: red; }}
            .malicious-post {{ background-color: #fff0f0; }}
            .malicious-comment {{ background-color: #fff0f0; }}
            .red-box {{
                border: 2px solid red;
                padding: 10px;
                margin: 10px 0;
                background-color: #ffe6e6;
                border-radius: 5px;
            }}
        </style>
    </head>
    <body>
        <h1>Reddit User Analysis: '{escape_html(username)}'</h1>
        <p>Report generated on: {current_datetime}</p>
        
        <div class="summary-box">
            <h2>Analysis Summary</h2>
            
            <div class="stat-grid">
                <div class="stat-item">
                    <div class="stat-label">Total Posts Analyzed:</div>
                    <div class="stat-value">{total_posts}</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">Total Comments Analyzed:</div>
                    <div class="stat-value">{total_comments}</div>
                </div>
                
                <div class="stat-item">
                    <div class="stat-label">Posts with Keywords:</div>
                    <div class="stat-value">{keyword_posts_count}</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">Comments with Keywords:</div>
                    <div class="stat-value">{keyword_comments_count}</div>
                </div>
    """
    
    if scanned_malicious:
        malicious_percentage_posts = (malicious_posts_count / total_posts * 100) if total_posts > 0 else 0
        malicious_percentage_comments = (malicious_comments_count / total_comments * 100) if total_comments > 0 else 0
        
        html_content += f"""
                <div class="stat-item">
                    <div class="stat-label">Potentially Malicious Posts:</div>
                    <div class="stat-value malicious-stat">{malicious_posts_count} ({malicious_percentage_posts:.1f}%)</div>
                </div>
                <div class="stat-item">
                    <div class="stat-label">Potentially Malicious Comments:</div>
                    <div class="stat-value malicious-stat">{malicious_comments_count} ({malicious_percentage_comments:.1f}%)</div>
                </div>
        """
        
        if all_malicious_words:
            html_content += f"""
                <div class="stat-item" style="grid-column: span 2;">
                    <div class="stat-label">Malicious Words Detected:</div>
                    <div class="stat-value malicious-stat">{escape_html(', '.join(sorted(all_malicious_words)))}</div>
                </div>
            """
    
    html_content += f"""
            </div>
            
            <p>Keywords searched: {escape_html(', '.join(keywords)) if keywords else 'None'}</p>
            <p>Malicious word scan enabled: {'Yes' if scanned_malicious else 'No'}</p>
            
            {f'<div class="red-box">⚠️ WARNING: This user has potentially malicious content in {malicious_posts_count} posts and {malicious_comments_count} comments.</div>' if scanned_malicious and (malicious_posts_count > 0 or malicious_comments_count > 0) else ''}
        </div>
        
        <hr>
        <h2>Analyzed Posts (Sorted by Score)</h2>
    """

    words_to_highlight_malicious = POTENTIALLY_MALICIOUS_WORDS if scanned_malicious else set()
    words_to_highlight_keywords = {kw.strip() for kw in keywords if kw.strip()}

    for post in analyzed_posts:
        all_highlight_terms = set()
        if scanned_malicious and post['is_potentially_malicious']:
            all_highlight_terms.update(post['malicious_words_found'])
        if post['keywords_found']:
            all_highlight_terms.update(post['keywords_found'])

        highlighted_title = highlight_text(post['title'], all_highlight_terms, color="red")
        highlighted_title = highlight_username(highlighted_title, username)

        highlighted_selftext = highlight_text(post['selftext'], all_highlight_terms, color="red")
        highlighted_selftext = highlight_username(highlighted_selftext, username)

        formatted_selftext_for_html = highlighted_selftext.replace('\n', '<br>')

        post_class = "post" + (" malicious-post" if post['is_potentially_malicious'] else "")
        
        html_content += f"""
        <div class="{post_class}">
            <h3><a href="{escape_html(post['url'])}">{highlighted_title}</a></h3>
            <p class="metadata">
                Subreddit: r/{escape_html(post['subreddit'])} | Score: {post['score']} | Post ID: {post['id']}
            </p>
            <div class="content">
                {formatted_selftext_for_html}
            </div>
        """
        
        if post['image_url']:
            image_data = download_image(post['image_url'])
            if image_data:
                html_content += f'<img src="{image_data}" class="post-image" alt="Post Image">'
        
        for comment in post['comments']:
            comment_class = "comment" + (" malicious-comment" if comment['is_potentially_malicious'] else "")
            highlighted_comment_body = highlight_text(comment['body'], all_highlight_terms, color="red")
            highlighted_comment_body = highlight_username(highlighted_comment_body, username)
            formatted_comment_body_for_html = highlighted_comment_body.replace('\n', '<br>')
            
            html_content += f"""
            <div class="{comment_class}">
                <p class="comment-author">{escape_html(comment['author'])}:</p>
                <div class="content">{formatted_comment_body_for_html}</div>
            </div>
            """
        
        html_content += "</div>"

    html_content += "</body></html>"

    pdf_buffer = io.BytesIO()
    pisa_status = pisa.CreatePDF(io.StringIO(html_content), dest=pdf_buffer)
    
    if pisa_status.err:
        st.error("Error generating PDF report.")
        return None
    
    return pdf_buffer.getvalue()

# --- Main Streamlit App ---

def main():
    st.set_page_config(page_title="Reddit User Analyzer", layout="wide")
    st.title("Reddit User Post Analyzer")

    APP_PASSWORD = "planet"
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        password_input = st.text_input("Enter App Password", type="password")
        if st.button("Login"):
            if password_input == APP_PASSWORD:
                st.session_state.logged_in = True
                st.experimental_rerun()
            else:
                st.error("Incorrect password.")
        st.info("Enter the password configured for this application to proceed.")
        st.stop()

    st.write(
        "Analyze recent posts by a specific Reddit user. Optionally scan for keywords and potentially malicious language."
    )

    with st.sidebar:
        st.header("Settings")

        st.subheader("Reddit API Credentials")
        st.text(f"App ID: ...{APP_ID[-4:]}")
        st.text(f"User Agent: {USER_AGENT}")
        st.caption("These are developer credentials used by the app.")

        st.subheader("Analysis Options")
        num_posts = st.slider(
            "Number of recent posts to fetch", min_value=5, max_value=100, value=25
        )

        scan_malicious = st.checkbox("Scan for potentially malicious words", value=True)
        if scan_malicious:
            st.caption(f"Using a predefined list of {len(POTENTIALLY_MALICIOUS_WORDS)} words.")

    st.header("User & Keyword Input")

    username = st.text_input("Enter Reddit Username (case-sensitive)", key="username_input")
    keywords_input = st.text_input("Enter Keywords to search for (comma-separated)", key="keywords_input")

    if st.button("Analyze User Posts", key="analyze_button"):
        if not username:
            st.warning("Please enter a Reddit username.")
            return

        keywords = [kw.strip() for kw in keywords_input.split(',') if kw.strip()]

        with st.spinner(f"Fetching and analyzing posts for user '{username}'..."):
            try:
                reddit = praw.Reddit(
                    client_id=APP_ID, client_secret=APP_SECRET, user_agent=USER_AGENT,
                    read_only=True
                )

                user_posts = search_reddit_user_posts(reddit, username, num_posts)
                if not user_posts:
                    return

                analyzed_posts = analyze_post_content(user_posts, keywords, scan_malicious)

                st.subheader("Analysis Summary")
                malicious_count = sum(1 for post in analyzed_posts if post['is_potentially_malicious'])
                keyword_count = sum(1 for post in analyzed_posts if post['keywords_found'])
                
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