import os
import discord
import asyncio
from typing import Dict, List, Tuple
import json
import re
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion

# Lấy cấu hình từ noitu_bot.config
from noitu_bot.config import OPEN_AI, OPENAI_BASE_URL

# START FIX: IMPORTS VÀ FALLBACK CHO MONITORING METRICS
try:
    from noitu_bot.monitoring_server import AI_CALLS_COUNTER
except ImportError:
    # Fallback nếu monitoring server chưa được cài đặt
    print("Warning: Could not import monitoring metrics. Running without Prometheus.")


    class DummyCounter:
        def labels(self, *args, **kwargs):
            return self

        def inc(self):
            pass


    AI_CALLS_COUNTER = DummyCounter()
# END FIX

# Thiết lập Client OpenAI
if OPENAI_BASE_URL:
    print(f"Khởi tạo OpenAI Client với base_url: {OPENAI_BASE_URL}")
    client = AsyncOpenAI(
        api_key=OPEN_AI,
        base_url=OPENAI_BASE_URL
    )
elif OPEN_AI:
    print("Khởi tạo OpenAI Client với base_url mặc định.")
    client = AsyncOpenAI(api_key=OPEN_AI)
else:
    print("LỖI: Thiếu cả OPEN_AI key.")
    client = None

# DÒNG DEBUG ENDPOINT ĐÃ CÓ
if client:
    print(f"DEBUG: W-Lex sử dụng Endpoint API: {client.base_url}")
# KẾT THÚC DÒNG DEBUG

# Mô hình bạn muốn sử dụng (thay thế cho Gemini)
AI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


async def _generate_completion(prompt: str) -> str:
    """Hàm wrapper gọi API completion."""
    if not client:
        return "Bot bị lỗi cấu hình AI. Thiếu key hoặc endpoint."

    try:
        response: ChatCompletion = await client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": "Bạn là Cơm Áo Gạo Tiền – AI ngầu lòi, cà khịa duyên dáng của server Cơm Áo Gạo Tiền."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.6,
            max_tokens=256,
        )

        # LOGIC MỚI: Tăng metric SUCCESS
        AI_CALLS_COUNTER.labels(endpoint_status='success').inc()

        return response.choices[0].message.content.strip()
    except Exception as e:

        # LOGIC MỚI: Tăng metric FAILURE
        AI_CALLS_COUNTER.labels(endpoint_status='failure').inc()

        print(f"Lỗi khi gọi OpenAI API: {e}")
        return "Á, bot bị úng nước rùi, cứu tuiii!"


async def gpt_generate_bot_reply(user_message: discord.Message) -> str:
    """Tạo ra một câu trả lời hài hước, chuẩn GenZ khi người dùng reply bot."""
    if not client or not user_message.reference:
        return "Bot lag rùi, đợi xíu nha :>"

    try:
        original_message = await user_message.channel.fetch_message(
            user_message.reference.message_id
        )
        original_content = original_message.content or "Tin nhắn này không có chữ"
        user_content = user_message.content

        # Prompt gốc đã được tối ưu hóa
        prompt = f"""
      Bạn là Cơm Áo Gạo Tiền AI ngầu lòi, cà khịa duyên dáng của , đang quản kênh nối từ trên Discord.
      [... RÀNG BUỘC PHONG CÁCH GỐC ...]

      NGỮ CẢNH
      - Tin nhắn cũ của bạn: {original_content}
      - Tin nhắn người chơi reply lại: "{user_content}"

      HÃY TRẢ LỜI NGAY: một đoạn 2-3 câu, đúng phong cách bựa vãi lồn, không liệt kê, không tùy chọn.
        """

        return await _generate_completion(prompt)

    except Exception as e:
        print(f"Lỗi khi gọi OpenAI API (generate_bot_reply): {e}")
        return "Á, bot bị úng nước rùi, cứu tuiii!"


async def check_vietnamese_word(word: str) -> str:
    """
    Kiểm tra một từ tiếng Việt có tồn tại hay không (thay thế cho check_vietnamese_word gốc).
    Verdict: 'có' hoặc 'không'
    """
    prompt = f"""
      Bạn là một AI ngôn ngữ cao cấp, chỉ có một nhiệm vụ: xác nhận từ tiếng Việt.
      RÀNG BUỘC ĐẦU RA:
      - Chỉ trả lời MỘT từ duy nhất: "có" nếu từ "{word}" là một từ có nghĩa trong tiếng Việt.
      - Trả lời "không" nếu từ đó vô nghĩa hoặc không tồn tại.
      - KHÔNG giải thích, KHÔNG thêm bất kỳ ký tự nào khác.

      Từ cần kiểm tra: "{word}"
      """

    response_text = await _generate_completion(prompt)
    # Lọc lại để đảm bảo chỉ trả về 'có' hoặc 'không'
    return "có" if "có" in response_text.lower() else "không"