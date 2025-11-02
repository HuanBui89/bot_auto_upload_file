import os
import re
import json
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account

# ============================================================
# LOGGING
# ============================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================
# CONFIG
# ============================================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
FOLDER_ID = os.getenv("DRIVE_FOLDER_ID")
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS")

if not BOT_TOKEN or not FOLDER_ID or not GOOGLE_CREDENTIALS:
    raise ValueError("⚠️ Thiếu biến môi trường BOT_TOKEN hoặc DRIVE_FOLDER_ID hoặc GOOGLE_CREDENTIALS")

creds_info = json.loads(GOOGLE_CREDENTIALS)
SCOPES = ["https://www.googleapis.com/auth/drive"]
creds = service_account.Credentials.from_service_account_info(creds_info, scopes=SCOPES)
drive_service = build("drive", "v3", credentials=creds)


# ============================================================
# GOOGLE DRIVE FUNCTIONS
# ============================================================
def get_or_create_folder(order_code: str):
    """Tạo folder nếu chưa có."""
    query = (
        f"name='{order_code}' and mimeType='application/vnd.google-apps.folder' "
        f"and '{FOLDER_ID}' in parents and trashed=false"
    )
    results = drive_service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get("files", [])

    if items:
        logger.info(f"📁 Folder '{order_code}' đã tồn tại.")
        return items[0]["id"]

    folder_metadata = {
        "name": order_code,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [FOLDER_ID],
    }
    folder = drive_service.files().create(body=folder_metadata, fields="id").execute()
    logger.info(f"🆕 Đã tạo folder mới: {order_code}")
    return folder["id"]


def upload_to_drive(file_path: str, file_name: str, folder_id: str):
    """Upload file lên Drive và trả về link xem."""
    try:
        media = MediaFileUpload(file_path, resumable=True)
        file_metadata = {"name": file_name, "parents": [folder_id]}
        uploaded = drive_service.files().create(
            body=file_metadata, media_body=media, fields="id"
        ).execute()
        file_id = uploaded["id"]
        logger.info(f"✅ Upload thành công: {file_name}")
        return f"https://drive.google.com/file/d/{file_id}/view"
    except Exception as e:
        logger.error(f"❌ Lỗi upload {file_name}: {e}")
        return None


def get_folder_link(folder_id: str):
    return f"https://drive.google.com/drive/folders/{folder_id}"


# ============================================================
# TELEGRAM HANDLER
# ============================================================
async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return

    # --- Xác định nếu là tin nhắn forward ---
    if msg.forward_origin:
        origin = msg.forward_origin
        logger.info(f"📩 Tin nhắn được forward (type={origin.type})")
    else:
        logger.info("💬 Tin nhắn gửi trực tiếp.")

    # --- Lấy mã đơn ---
    text = (msg.caption or msg.text or "").strip()
    match = re.search(r"\b([A-Z0-9]{6,})\b", text)
    if not match:
        logger.warning("⚠️ Không tìm thấy mã đơn trong tin nhắn.")
        return

    order_code = match.group(1)
    logger.info(f"📦 Mã đơn phát hiện: {order_code}")

    folder_id = get_or_create_folder(order_code)
    media_links = []

    # --- ẢNH ---
    if msg.photo:
        logger.info(f"🖼 Có {len(msg.photo)} ảnh, đang xử lý...")
        for i, photo in enumerate(msg.photo):
            file = await photo.get_file()
            file_path = f"{order_code}_{i}.jpg"
            await file.download_to_drive(file_path)
            link = upload_to_drive(file_path, os.path.basename(file_path), folder_id)
            if link:
                media_links.append(link)
            os.remove(file_path)

    # --- VIDEO ---
    elif msg.video:
        logger.info("🎬 Có video, đang xử lý...")
        file = await msg.video.get_file()
        file_path = f"{order_code}.mp4"
        await file.download_to_drive(file_path)
        link = upload_to_drive(file_path, os.path.basename(file_path), folder_id)
        if link:
            media_links.append(link)
        os.remove(file_path)

    # --- FILE ---
    elif msg.document:
        logger.info("📄 Có file, đang xử lý...")
        file = await msg.document.get_file()
        file_path = msg.document.file_name or f"{order_code}.dat"
        await file.download_to_drive(file_path)
        link = upload_to_drive(file_path, file_path, folder_id)
        if link:
            media_links.append(link)
        os.remove(file_path)

    # --- Kết quả ---
    if media_links:
        folder_link = get_folder_link(folder_id)
        await msg.reply_text(
            f"📦 Mã đơn: {order_code}\n"
            f"✅ Đã upload {len(media_links)} file vào thư mục:\n{folder_link}"
        )
        logger.info(f"✅ Upload hoàn tất cho đơn {order_code}")
    else:
        logger.warning("⚠️ Không có media nào được phát hiện.")


# ============================================================
# RUN BOT
# ============================================================
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL, handle_media))
    logger.info("🚀 Bot đang chạy 24/7 trên Railway...")
    app.run_polling()


if __name__ == "__main__":
    main()
