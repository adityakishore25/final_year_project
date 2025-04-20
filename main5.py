import sys
import os
import csv
import asyncio
import re
import datetime

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, 
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QTextEdit, QFileDialog, QMessageBox,
    QStackedWidget, QInputDialog
)
from PyQt5.QtGui import QPixmap, QFont
from PyQt5.QtWidgets import QGraphicsOpacityEffect

from PyQt5.QtCore import QTimer, Qt, QPropertyAnimation, QEasingCurve

from telethon import TelegramClient

# --------------------------------------------------
# Abusive Language Detector
# --------------------------------------------------
class AbusiveLanguageDetector:
    def __init__(self):
        # Initial list of abusive words - you can train/expand thisa
        self.abusive_words = [
            "fuck", "shit", "bitch", "ass", "damn", "crap", "idiot", 
            "stupid", "dumb", "loser", "jerk", "bastard", "asshole",
             "kill", "murder", "assault", "attack", "hate", "violent", "terror",
        "bomb", "shoot", "racist", "abuse", "threat", "harass", "genocide",
        "extremist", "rape", "torture", "massacre", "suicide", "riot",
        "hostage", "kidnap", "lynch", "brutal", "bloodshed", "slaughter",
        "militant", "radicalize", "jihad", "supremacist"
        ]
        # You can add more categories or severity levels if needed
        
    def add_words(self, new_words):
        """Add new words to the abusive words list (training)"""
        if isinstance(new_words, str):
            new_words = [new_words]
        self.abusive_words.extend([word.lower() for word in new_words])
        # Remove duplicates
        self.abusive_words = list(set(self.abusive_words))
        
    def detect(self, text):
        """
        Detect abusive words in text
        Returns: list of (word, start_pos, end_pos) tuples
        """
        if not text:
            return []
            
        results = []
        text_lower = text.lower()
        
        for word in self.abusive_words:
            for match in re.finditer(r'\b' + re.escape(word) + r'\b', text_lower):
                start, end = match.span()
                # Get the actual case from the original text
                original_word = text[start:end]
                results.append((original_word, start, end))
                
        return results
    
    def highlight_text(self, text):
        """Returns text with HTML highlighting for abusive words"""
        if not text:
            return ""
            
        # Get all matches with positions
        matches = self.detect(text)
        if not matches:
            return text
            
        # Sort by position (start) in descending order to avoid position shifts
        matches.sort(key=lambda x: x[1], reverse=True)
        
        # Replace each match with highlighted version
        result = text
        for word, start, end in matches:
            highlighted = f'<span style="background-color: #ffcccc; color: red; font-weight: bold;">{word}</span>'
            result = result[:start] + highlighted + result[end:]
            
        return result

# --------------------------------------------------
# Welcome Page
# --------------------------------------------------
class WelcomePage(QWidget):
    def __init__(self, switch_callback=None, parent=None):
        super().__init__(parent)
        self.switch_callback = switch_callback  # Function to switch pages

        layout = QVBoxLayout()
        layout.setSpacing(20)
        layout.setContentsMargins(50, 50, 50, 50)
        
        # Title label
        self.title_label = QLabel("Welcome to Telegram Scraper!")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setFont(QFont("Arial", 24, QFont.Bold))

        # Add fade-in effect to the title
        self.title_opacity_effect = QGraphicsOpacityEffect()
        self.title_label.setGraphicsEffect(self.title_opacity_effect)
        
        self.title_animation = QPropertyAnimation(self.title_opacity_effect, b"opacity")
        self.title_animation.setDuration(1500)       # 1.5 seconds
        self.title_animation.setStartValue(0.0)
        self.title_animation.setEndValue(1.0)
        self.title_animation.setEasingCurve(QEasingCurve.InOutQuad)
        self.title_animation.start()

        # Description label
        desc_label = QLabel(
            "This application allows you to log in to Telegram, fetch recent chats "
            "and messages (including images), and export them to CSV or PDF. "
            "\n\nThe app can also detect and highlight abusive language in messages."
            "\n\nClick Continue to proceed to the main scraper."
        )
        desc_label.setAlignment(Qt.AlignCenter)
        desc_label.setWordWrap(True)

        # Continue button
        continue_button = QPushButton("Continue →")
        continue_button.setFixedWidth(150)
        continue_button.setStyleSheet("font-size: 16px; padding: 8px;")
        continue_button.clicked.connect(self.handle_continue)

        # Add widgets to layout
        layout.addWidget(self.title_label, alignment=Qt.AlignCenter)
        layout.addWidget(desc_label, alignment=Qt.AlignCenter)
        layout.addWidget(continue_button, alignment=Qt.AlignCenter)

        self.setLayout(layout)

    def handle_continue(self):
        """Switch to the scraper page when the button is clicked."""
        if self.switch_callback:
            self.switch_callback()


# --------------------------------------------------
# Scraper Page (Your Telethon-based UI)
# --------------------------------------------------
class ScraperPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Initialize the abusive language detector
        self.language_detector = AbusiveLanguageDetector()

        # Main layout
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # Input layout
        input_layout = QVBoxLayout()
        main_layout.addLayout(input_layout)

        # Row for screenshot/export/report buttons
        button_layout = QHBoxLayout()
        main_layout.addLayout(button_layout)

        # ===== API Input Fields =====
        self.api_id_edit = QLineEdit()
        self.api_hash_edit = QLineEdit()
        self.phone_edit = QLineEdit()

        input_layout.addWidget(QLabel("API ID:"))
        input_layout.addWidget(self.api_id_edit)

        input_layout.addWidget(QLabel("API HASH:"))
        input_layout.addWidget(self.api_hash_edit)

        input_layout.addWidget(QLabel("Phone:"))
        input_layout.addWidget(self.phone_edit)

        # ===== Login Button =====
        self.login_button = QPushButton("Login")
        self.login_button.clicked.connect(self.handle_login)
        input_layout.addWidget(self.login_button)

        # ===== Output Text Area =====
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        main_layout.addWidget(self.output_text)

        # ===== Screenshot Button =====
        self.screenshot_button = QPushButton("Take Screenshot")
        self.screenshot_button.clicked.connect(self.take_screenshot)
        button_layout.addWidget(self.screenshot_button)

        # ===== Export CSV Button =====
        self.export_csv_button = QPushButton("Export to CSV")
        self.export_csv_button.clicked.connect(self.export_to_csv)
        button_layout.addWidget(self.export_csv_button)

        # ===== Export PDF Button (Report) =====
        self.export_pdf_button = QPushButton("Export to PDF")
        self.export_pdf_button.clicked.connect(self.export_to_pdf)
        button_layout.addWidget(self.export_pdf_button)

        # ===== Train Detector Button =====
        self.train_button = QPushButton("Train Detector")
        self.train_button.clicked.connect(self.train_detector)
        button_layout.addWidget(self.train_button)

        # Telethon client
        self.client = None
        # Store scraped messages (text + image paths)
        self.scraped_data = []

    # -----------------------------
    # 1. Telethon Login Logic
    # -----------------------------
    def handle_login(self):
        """Trigger the login process using Telethon."""
        try:
            api_id_val = int(self.api_id_edit.text())
            api_hash_val = self.api_hash_edit.text()
            phone_val = self.phone_edit.text()

            self.client = TelegramClient('session_name', api_id_val, api_hash_val)
            asyncio.ensure_future(self.login_telegram(phone_val))
        except Exception as e:
            self.output_text.append(f"Error in handle_login: {str(e)}")

    async def login_telegram(self, phone):
        """Async function to start the client and do the login."""
        try:
            await self.client.start(phone=phone)
            me = await self.client.get_me()
            self.output_text.append(f"Logged in as: {me.username or me.first_name}")
            await self.fetch_dialogs()
        except Exception as e:
            self.output_text.append(f"Error in login_telegram: {str(e)}")

    async def fetch_dialogs(self):
        """Fetch and display a few recent chats and messages, including images."""
        try:
            # Clear out old data to avoid duplicates
            self.scraped_data.clear()

            dialogs = await self.client.get_dialogs(limit=5)
            for dialog in dialogs:
                chat = dialog.entity
                name = getattr(chat, 'title', chat.username)
                if not name:
                    name = f"PrivateChat_{chat.id}"

                self.output_text.append(f"Found chat: {name}")

                messages = await self.client.get_messages(chat, limit=5)
                for msg in messages:
                    sender_id = msg.sender_id
                    text = msg.text or ""

                    # Check for abusive language
                    abusive_matches = self.language_detector.detect(text)
                    has_abuse = len(abusive_matches) > 0

                    # Check for photo or other media
                    media_path = None
                    if msg.photo:
                        # Download the photo to 'downloads/' folder
                        os.makedirs("downloads", exist_ok=True)
                        media_path = await msg.download_media(file="downloads/")
                        self.output_text.append(f"   -> [Image saved: {media_path}]")

                    # Build a record
                    record = {
                        "chat_name": name,
                        "sender_id": sender_id,
                        "message_text": text,
                        "media_path": media_path,  # might be None if no media
                        "has_abuse": has_abuse,
                        "abuse_matches": abusive_matches
                    }
                    self.scraped_data.append(record)

                    # Display text in the GUI
                    display_text = f"   -> {sender_id}: {text}"
                    if media_path:
                        display_text += " (has image)"
                    if has_abuse:
                        display_text += " [CONTAINS ABUSIVE LANGUAGE]"
                    
                    self.output_text.append(display_text)

        except Exception as e:
            self.output_text.append(f"Error fetching dialogs: {str(e)}")

    # -----------------------------
    # 2. Take Screenshot
    # -----------------------------
    def take_screenshot(self):
        screen = self.screen()
        if not screen:
            self.output_text.append("Failed to capture screen.")
            return

        window_id = self.winId()
        pixmap = screen.grabWindow(window_id)

        save_path, _ = QFileDialog.getSaveFileName(self, "Save Screenshot", "screenshot.png", "PNG Files (*.png)")
        if save_path:
            if pixmap.save(save_path, "PNG"):
                self.output_text.append(f"Screenshot saved to: {save_path}")
            else:
                self.output_text.append("Failed to save screenshot.")

    # -----------------------------
    # 3. Export to CSV
    # -----------------------------
    def export_to_csv(self):
        """Write the scraped_data to a CSV file, including media paths and abuse flags."""
        if not self.scraped_data:
            QMessageBox.warning(self, "No Data", "No chat data available to export.")
            return

        save_path, _ = QFileDialog.getSaveFileName(self, "Save CSV", "chat_export.csv", "CSV Files (*.csv)")
        if not save_path:
            return  # user canceled

        try:
            with open(save_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['chat_name', 'sender_id', 'message_text', 'media_path', 'has_abusive_language'])
                for item in self.scraped_data:
                    writer.writerow([
                        item['chat_name'], 
                        item['sender_id'], 
                        item['message_text'], 
                        item['media_path'] or '',  # blank if None
                        'Yes' if item['has_abuse'] else 'No'
                    ])
            QMessageBox.information(self, "Export Success", f"Data exported to {save_path} successfully!")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"An error occurred: {e}")

    # -----------------------------
    # 4. Export to PDF (Report)
    # -----------------------------
    def export_to_pdf(self):
        """Generate a PDF report with highlighted abusive language"""
        try:
            import weasyprint
        except ImportError:
            QMessageBox.critical(self, "WeasyPrint not installed",
                                "Please install WeasyPrint: pip install weasyprint")
            return

        if not self.scraped_data:
            QMessageBox.warning(self, "No Data", "No chat data available for PDF report.")
            return

        # Prompt user for file path
        save_path, _ = QFileDialog.getSaveFileName(self, "Save PDF", "report.pdf", "PDF Files (*.pdf)")
        if not save_path:
            return

        # Track abusive language statistics
        total_messages = 0
        messages_with_abuse = 0
        total_abusive_words = 0
        abusive_word_counts = {}

        # Build a simple HTML from scraped data
        html_content = """
        <html>
        <head>
          <meta charset="utf-8">
          <style>
            body { font-family: sans-serif; }
            .message {
                margin-bottom: 10px;
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 5px;
            }
            .message.has-abuse {
                border-left: 5px solid red;
            }
            .image {
                margin-top: 5px;
                max-height: 200px;
            }
            .abuse-summary {
                margin-top: 20px;
                padding: 15px;
                background-color: #f8f8f8;
                border: 1px solid #ddd;
                border-radius: 5px;
            }
            .abuse-stats {
                margin-top: 10px;
            }
            h2 {
                color: #d32f2f;
            }
          </style>
        </head>
        <body>
        <h1>Telegram Report</h1>
        <p>Generated on: """ + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + """</p>
        
        <h2>Messages</h2>
        """

        for item in self.scraped_data:
            total_messages += 1
            chat_name = item["chat_name"]
            sender_id = item["sender_id"]
            text = item["message_text"]
            media_path = item["media_path"]
            has_abuse = item["has_abuse"]
            
            if has_abuse:
                messages_with_abuse += 1
                abusive_matches = item["abuse_matches"]
                total_abusive_words += len(abusive_matches)
                
                # Update word counts
                for word, _, _ in abusive_matches:
                    word_lower = word.lower()
                    if word_lower in abusive_word_counts:
                        abusive_word_counts[word_lower] += 1
                    else:
                        abusive_word_counts[word_lower] = 1
            
            # Highlight abusive words in the text
            highlighted_text = self.language_detector.highlight_text(text)
            
            # Add CSS class if message has abuse
            abuse_class = " has-abuse" if has_abuse else ""
            
            html_content += f"""
            <div class="message{abuse_class}">
                <strong>Chat:</strong> {chat_name}<br/>
                <strong>Sender:</strong> {sender_id}<br/>
                <strong>Text:</strong> {highlighted_text}
            """

            if media_path and os.path.exists(media_path):
                # Convert local path to file:// for HTML embedding
                abs_path = os.path.abspath(media_path)
                url_path = 'file://' + abs_path.replace(' ', '%20')
                html_content += f'<br/><img src="{url_path}" class="image" />'

            html_content += "</div>"

        # Add abuse summary section
        html_content += """
        <div class="abuse-summary">
            <h2>Abusive Language Summary</h2>
        """
        
        if total_abusive_words > 0:
            abuse_percentage = (messages_with_abuse / total_messages) * 100
            html_content += f"""
            <div class="abuse-stats">
                <p><strong>Total messages analyzed:</strong> {total_messages}</p>
                <p><strong>Messages containing abusive language:</strong> {messages_with_abuse} ({abuse_percentage:.1f}%)</p>
                <p><strong>Total abusive words detected:</strong> {total_abusive_words}</p>
                
                <h3>Most common abusive words:</h3>
                <ul>
            """
            
            # Sort words by frequency
            sorted_words = sorted(abusive_word_counts.items(), key=lambda x: x[1], reverse=True)
            for word, count in sorted_words[:10]:  # Show top 10
                html_content += f"<li><strong>{word}</strong>: {count} occurrences</li>"
                
            html_content += """
                </ul>
            </div>
            """
        else:
            html_content += "<p>No abusive language detected in the analyzed messages.</p>"
        
        html_content += """
        </div>
        </body>
        </html>
        """

        # Use WeasyPrint to convert HTML to PDF
        try:
            pdf = weasyprint.HTML(string=html_content).write_pdf()
            with open(save_path, 'wb') as f:
                f.write(pdf)
            QMessageBox.information(self, "PDF Export", f"PDF report saved: {save_path}")
        except Exception as e:
            QMessageBox.critical(self, "PDF Export Error", str(e))

    # -----------------------------
    # 5. Train Abusive Language Detector
    # -----------------------------
    def train_detector(self):
        """Open a dialog to add new abusive words to the detector"""
        text, ok = QInputDialog.getText(
            self, 
            "Train Abusive Language Detector",
            "Enter new abusive words (comma-separated):"
        )
        
        if ok and text:
            # Split by comma and strip whitespace
            new_words = [word.strip() for word in text.split(',')]
            self.language_detector.add_words(new_words)
            QMessageBox.information(
                self, 
                "Training Complete", 
                f"Added {len(new_words)} new words to the detector."
            )


# --------------------------------------------------
# Main Window with QStackedWidget
# --------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Telegram Scraper with Abusive Language Detection")
        self.resize(800, 600)
        
        # Create stacked widget
        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)

        # Create pages
        self.welcome_page = WelcomePage(self.show_scraper_page)
        self.scraper_page = ScraperPage()

        # Add pages to the stack
        self.stacked_widget.addWidget(self.welcome_page)  # index 0
        self.stacked_widget.addWidget(self.scraper_page)   # index 1

        # Start on the welcome page
        self.stacked_widget.setCurrentIndex(0)

    def show_scraper_page(self):
        """Switch to the scraper page."""
        self.stacked_widget.setCurrentIndex(1)


# --------------------------------------------------
# main() function
# --------------------------------------------------
def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()

    loop = asyncio.get_event_loop()

    def step():
        loop.call_soon(loop.stop)
        loop.run_forever()
        app.processEvents()

    timer = QTimer()
    timer.timeout.connect(step)
    timer.start(50)  # 50 ms

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()