import os
import discord
from google.cloud import aiplatform
import vertexai
from vertexai.generative_models import GenerativeModel
from google.cloud.storage import Client, transfer_manager
import base64
import time
from typing import Dict, List, Tuple
import asyncio
import json
import re

_word_cache = {}
CACHE_TTL = 86400

# Queue & lock cho batch
_batch_queue: List[Tuple[str, asyncio.Future]] = []
_batch_lock = asyncio.Lock()
_batch_worker_task: asyncio.Task | None = None
_BATCH_WAIT_SECONDS = 0.1
_BATCH_MAX = 32


def setup_google_credentials():
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        creds_path = os.path.join(current_dir, "bot_gemini.json")
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path
        return True

    except Exception as e:
        print(f"LỖI: Không thể giải mã hoặc ghi file credentials: {e}")
        return False


model = None
if setup_google_credentials():
    PROJECT_ID = "newgamehub"
    LOCATION = "us-central1"

    try:
        # Vertex AI sẽ tự động tìm credentials từ biến môi trường đã được thiết lập ở trên
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        model = GenerativeModel("gemini-2.5-pro")
        print("Khởi tạo Vertex AI thành công!")

    except Exception as e:
        print(f"Lỗi khởi tạo Vertex AI: {e}")


async def generate_bot_reply(user_message: discord.Message) -> str:
    """
    Tạo ra một câu trả lời hài hước, chuẩn GenZ khi người dùng reply bot.
    """
    if not model or not user_message.reference:
        return "Bot lag rùi, đợi xíu nha :>"

    try:
        # Lấy tin nhắn gốc mà người dùng đã reply
        original_message = await user_message.channel.fetch_message(
            user_message.reference.message_id
        )
        original_content = original_message.content or "Tin nhắn này không có chữ"
        print(original_content)
        user_content = user_message.content

        # Prompt được "mớm" rất kỹ để AI hiểu vai trò và bối cảnh
        prompt = f"""
      Bạn là Cụt Con – AI ngầu lòi, cà khịa duyên dáng của Cánh Cụt Team, đang quản kênh Tâm Sự trên Discord.

NHIỆM VỤ
- Trả lời tin nhắn người chơi đã reply bạn.

PHONG CÁCH
- Hài hước, thông minh, bắt trend; có chút “ngông” tự luyến nhưng duyên.
- Dùng teencode/slang vừa phải.
- Nếu bị chửi: được phép chửi lại, sắc bén nhưng ko được nói tục.

RÀNG BUỘC ĐẦU RA (RẤT QUAN TRỌNG)
- Chỉ 2-3 câu, ngắn, dí dỏm.
- Trả lời dưới dạng MỘT ĐOẠN VĂN, KHÔNG được dùng số thứ tự (1., 2., “Option 1/2/3”), KHÔNG bullet (-, •), KHÔNG xuống dòng liệt kê.
- KHÔNG giải thích, KHÔNG meta (không nói “tôi là AI…”), KHÔNG đưa nhiều phương án.
- Nếu cảm thấy muốn đưa nhiều lựa chọn, hãy gộp thành MỘT câu trả lời duy nhất.

NGỮ CẢNH
- Tin nhắn cũ của bạn: {original_content}
- Tin nhắn người chơi reply lại: "{user_content}"

HÃY TRẢ LỜI NGAY: một đoạn 2-3 câu, đúng phong cách Cụt Con, không liệt kê, không tùy chọn.
        """

        response = await model.generate_content_async(prompt)

        # Thêm một chút "thương hiệu" vào câu trả lời
        return response.text.strip()

    except discord.NotFound:
        return "Ủa tin nhắn đó bị gỡ rùi hay sao á, tui hong thấy :<"
    except Exception as e:
        print(f"Lỗi khi gọi Gemini API (generate_bot_reply): {e}")
        return "Á, bot bị úng nước rùi, cứu tuiii!"
