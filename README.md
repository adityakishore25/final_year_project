🔧 Steps to Create Reddit API Credentials:
Log in to Reddit
Go to: https://www.reddit.com/prefs/apps
(Make sure you are logged in to your Reddit account.)
Create a Developer Application
Scroll down to the bottom and click on “are you a developer? create an app...”
Fill Out the Application Form:
Name: Choose a name (e.g., Reddit Analyzer)
App Type: Select "script" (for personal use, like analysis apps or bots)
Description: Optional
About URL: Can leave blank
Redirect URI: Use http://localhost:8080 (or any placeholder; it's not used for script apps)
Permissions: You don’t set this manually — PRAW manages it based on usage.
Click "Create app"
✅ You’ll Get:
Client ID (APP_ID): Shown right under the app name (above the “secret”)
Client Secret (APP_SECRET): Shown as "secret"
User Agent (USER_AGENT): You create this string yourself, but it should follow this format:
<platform>:<app ID>:<version string> (by /u/<reddit username>)
Example:

python:reddit-analyzer:v1.0 (by /u/Miserable-Meet5365)




## 💻 Twitter(X) Platform Scraping

![twitter drawio](https://github.com/user-attachments/assets/30a23a7c-7aee-4613-af38-7fe8fd2615e0)


We have used a library called playwright launches a headless browser. The file [automated scraping.py](https://github.com/adityakishore25/final_year_project/blob/main/twitter/automated-scraping.py) enables extraction of tweets of verified accounts into JSON format. This is done by first extracting tweet URL's and executing the script in multi-threaded manner.

After this the images and text are fed to Ollama3.2: 1b model for further analysis.

The folder [frontend-design](https://github.com/adityakishore25/final_year_project/tree/main/twitter/frontend-design) contains the templates , model and server files.
