import os
import re
import json
import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account

# ============================================================
# CONFIG
# ============================================================
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Token Telegram Bot
FOLDER_ID = os.getenv("DRIVE_FOLDER_ID")  # ID thư mục Google Drive gốc

# Lấy credentials từ biến môi trường thay vì file
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS")
if not GOOGLE_CREDENTIALS:
    raise ValueError("⚠️ Chưa có biến môi trường GOOGLE_CREDENTIALS trong Railway")

creds_info = json.loads(GOOGLE_CREDENTIALS)
SCOPES = ['https://www.googleapis.com/auth/drive']
creds = service_account.Credentials.from_service_account_info(creds_info, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=creds)


# ============================================================
# GOOGLE DRIVE FUNCTIONS
# ============================================================
def get_or_create_folder(order_code: str):
    """Tạo folder mới trong Drive nếu chưa tồn tại."""
    query = (
        f"name='{order_code}' and "
        f"mimeType='application/vnd.google-apps.folder' and "
        f"'{FOLDER_ID}' in parents and trashed=false"
    )
    results = drive_service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get('files', [])
    if items:
        return items[0]['id']

    folder_metadata = {
        'name': order_code,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [FOLDER_ID],
    }
    folder = drive_service.files().create(body=folder_metadata, fields='id').execute()
    return folder.get('id')


def upload_to_drive(file_path: str, file_name: str, folder_id: str):
    """Upload file lên Drive và trả về link."""
    media = MediaFileUpload(file_path, resumable=True)
    file_metadata = {'name': file_name, 'parents': [folder_id]}
    uploaded = drive_service.files().create(
        body=file_metadata, media_body=media, fields='id'
    ).execute()
    file_id = uploaded.get('id')
    return f"https://drive.google.com/file/d/{file_id}/view"


def get_folder_link(folder_id: str):
    """Trả về link folder."""
    return f"https://drive.google.com/drive/folders/{folder_id}"


# ============================================================
# TELEGRAM HANDLER
# ============================================================
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

    if media_links:
        folder_link = get_folder_link(folder_id)
        await msg.reply_text(
            f"📦 Mã đơn: {order_code}\n"
            f"✅ Đã upload {len(media_links)} file vào:\n{folder_link}"
        )


# ============================================================
# RUN BOT
# ============================================================
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL, handle_media))
    print("🚀 Bot đang chạy...")
    app.run_polling()


if __name__ == "__main__":
    main()
