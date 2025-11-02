import os
import re
import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account

# -------------------------
# CONFIG
# -------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")  # lấy token từ biến môi trường
FOLDER_ID = os.getenv("DRIVE_FOLDER_ID")  # ID thư mục gốc Drive

SERVICE_ACCOUNT_FILE = "credentials.json"
SCOPES = ['https://www.googleapis.com/auth/drive']
creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=creds)


# -------------------------
# Google Drive functions
# -------------------------
def get_or_create_folder(order_code):
    """Tạo folder nếu chưa có"""
    query = f"name='{order_code}' and mimeType='application/vnd.google-apps.folder' and '{FOLDER_ID}' in parents and trashed=false"
    results = drive_service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get('files', [])
    if items:
        return items[0]['id']

    folder_metadata = {
        'name': order_code,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [FOLDER_ID]
    }
    folder = drive_service.files().create(body=folder_metadata, fields='id').execute()
    return folder.get('id')


def upload_to_drive(file_path, file_name, folder_id):
    media = MediaFileUpload(file_path, resumable=True)
    file_metadata = {'name': file_name, 'parents': [folder_id]}
    file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    file_id = file.get('id')
    return f"https://drive.google.com/file/d/{file_id}/view"


def get_folder_link(folder_id):
    return f"https://drive.google.com/drive/folders/{folder_id}"


# -------------------------
# Telegram handler
# -------------------------
async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    text = msg.caption or msg.text or ""
    match = re.search(r'\b([A-Z0-9]{6,})\b', text)
    if not match:
        return

    order_code = match.group(1)
    folder_id = get_or_create_folder(order_code)

    media_links = []

    # Ảnh
    if msg.photo:
        for i, photo in enumerate(msg.photo):
            file = await photo.get_file()
            file_path = f"{order_code}_{i}.jpg"
            await file.download_to_drive(file_path)
            link = upload_to_drive(file_path, os.path.basename(file_path), folder_id)
            media_links.append(link)
            os.remove(file_path)

    # Video
    if msg.video:
        file = await msg.video.get_file()
        file_path = f"{order_code}.mp4"
        await file.download_to_drive(file_path)
        link = upload_to_drive(file_path, os.path.basename(file_path), folder_id)
        media_links.append(link)
        os.remove(file_path)

    folder_link = get_folder_link(folder_id)
    if media_links:
        await msg.reply_text(f"📦 {order_code}\nĐã upload {len(media_links)} file vào folder:\n{folder_link}")


# -------------------------
# Run bot
# -------------------------
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL, handle_media))
    app.run_polling()

if __name__ == "__main__":
    main()
