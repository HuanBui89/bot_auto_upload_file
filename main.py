import os
import re
import json
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account

# ============================================================
# CONFIG
# ============================================================
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Token Telegram Bot
FOLDER_ID = os.getenv("DRIVE_FOLDER_ID")  # ID thư mục Drive gốc

# Lấy credentials từ biến môi trường (Railway)
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
        print(f"📁 Folder {order_code} đã tồn tại.")
        return items[0]['id']

    folder_metadata = {
        'name': order_code,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [FOLDER_ID],
    }
    folder = drive_service.files().create(body=folder_metadata, fields='id').execute()
    print(f"🆕 Đã tạo folder mới: {order_code}")
    return folder.get('id')


def upload_to_drive(file_path: str, file_name: str, folder_id: str):
    """Upload file lên Drive và trả về link."""
    try:
        media = MediaFileUpload(file_path, resumable=True)
        file_metadata = {'name': file_name, 'parents': [folder_id]}
        uploaded = drive_service.files().create(
            body=file_metadata, media_body=media, fields='id'
        ).execute()
        file_id = uploaded.get('id')
        print(f"✅ Upload thành công: {file_name}")
        return f"https://drive.google.com/file/d/{file_id}/view"
    except Exception as e:
        print(f"❌ Lỗi upload {file_name}: {e}")
        return None


def get_folder_link(folder_id: str):
    """Trả về link folder."""
    return f"https://drive.google.com/drive/folders/{folder_id}"


# ============================================================
# TELEGRAM HANDLER
# ============================================================
async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message

    # --- Nếu là tin nhắn forward ---
    source_msg = msg
    if msg.forward_from or msg.forward_from_chat:
        print("📩 Tin nhắn forward được phát hiện.")
        source_msg = msg  # Telegram vẫn gửi kèm media trong forward
    else:
        print("💬 Tin nhắn gửi trực tiếp.")

    # --- Lấy mã đơn ---
    text = source_msg.caption or msg.caption or msg.text or ""
    match = re.search(r'\b([A-Z0-9]{6,})\b', text)
    if not match:
        print("⚠️ Không tìm thấy mã đơn trong tin nhắn.")
        return
    order_code = match.group(1)
    print(f"📦 Mã đơn phát hiện: {order_code}")

    folder_id = get_or_create_folder(order_code)
    media_links = []

    # --- ẢNH ---
    if source_msg.photo:
        print(f"🖼 Có {len(source_msg.photo)} ảnh, đang tải...")
        for i, photo in enumerate(source_msg.photo):
            file = await photo.get_file()
            file_path = f"{order_code}_{i}.jpg"
            await file.download_to_drive(file_path)
            link = upload_to_drive(file_path, os.path.basename(file_path), folder_id)
            if link:
                media_links.append(link)
            os.remove(file_path)

    # --- VIDEO ---
    if source_msg.video:
        print("🎬 Có video, đang tải...")
        file = await source_msg.video.get_file()
        file_path = f"{order_code}.mp4"
        await file.download_to_drive(file_path)
        link = upload_to_drive(file_path, os.path.basename(file_path), folder_id)
        if link:
            media_links.append(link)
        os.remove(file_path)

    # --- Phản hồi ---
    if media_links:
        folder_link = get_folder_link(folder_id)
        await msg.reply_text(
            f"📦 Mã đơn: {order_code}\n"
            f"✅ Đã upload {len(media_links)} file vào thư mục:\n{folder_link}"
        )
        print(f"✅ Upload hoàn tất cho đơn {order_code}")
    else:
        print("⚠️ Không có media nào được phát hiện.")


# ============================================================
# RUN BOT
# ============================================================
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL, handle_media))
    print("🚀 Bot đang chạy 24/7 trên Railway...")
    app.run_polling()


if __name__ == "__main__":
    main()
