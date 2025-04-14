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
