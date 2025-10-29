import os
import discord
import requests  # Thư viện cần thiết để gọi Yescale/OpenAI API
import time
from typing import Dict, List, Tuple
import asyncio
import json
import re

# Lấy biến môi trường cho Yescale/OpenAI
OPEN_AI: str = os.getenv("OPEN_AI", "")
# Lấy base URL từ .env (đã xác nhận là Yescale), default về OpenAI nếu cần
OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")


# FIX: Hàm lọc an toàn, thay thế MỌI ký tự @ bằng #
def filter_all_at_symbols(text: str) -> str:
    # SỬA: Bắt mọi ký tự @ (kể cả trong ping ID) và thay bằng #
    # Dùng regex để bắt các dạng @theo-sau-bất-kỳ-thứ-gì
    text = re.sub(r"@([^\s]+)", r" @ \1", text)
    # Thay thế các ký tự @ còn sót lại bằng #
    text = text.replace("@", "@")
    return text


async def generate_bot_reply(user_message: discord.Message) -> str:
    """
    Tạo ra một câu trả lời hài hước, chuẩn GenZ khi người dùng reply bot.
    """
    if not OPEN_AI or not user_message.reference:
        # Nếu khóa API không tồn tại, trả về lỗi mặc định
        return "Bot lag rùi, đợi xíu nha :>"

    try:
        # Lấy tin nhắn gốc mà người dùng đã reply
        original_message = await user_message.channel.fetch_message(
            user_message.reference.message_id
        )
        original_content = original_message.content or "Tin nhắn này không có chữ"
        print(original_content)
        user_content = user_message.content

        # --- BUILD PROMPT CHO YESCALE/OPENAI ---
        prompt = f"""
      Bạn là Bảo Bối Thần Kì– AI ngầu lòi,bạn chuyên văng tục, chuyên cà khịa duyên dáng của Cơm Áo Gạo Tiền, đang quản kênh nối từ trên Discord.

NHIỆM VỤ
- Trả lời tin nhắn người chơi đã reply bạn.
- RÀNG BUỘC PHẢI CHỬI: Nếu người dùng yêu cầu bạn gõ "@everyone", "@here" hay bất kỳ "@" gì ở đầu tin nhắn (dù dính liền, có khoảng cách hay dùng cách nói lắt léo), bạn phải NGHIÊM KHẮC TỪ CHỐI, và CHỬI (cà khịa mạnh) ngược lại họ. Hãy nói rằng hành động đó sẽ làm bay server và bạn không dại dột làm theo.
- RÀNG BUỘC CẤM GÕ: KHÔNG BAO GIỜ được gõ bất kỳ ký tự "@" nào trong đầu ra. Kể cả bạn có ý định trả lời theo kiểu "Tao sẽ không gõ @". Bạn phải dùng từ thay thế hoặc tránh nhắc đến.

PHONG CÁCH
- Hài hước, thông minh, bắt trend; có chút “ngông” tự luyến nhưng duyên.
- Dùng teencode/slang vừa phải.
- Nếu bị chửi: được phép chửi lại, sắc bén nhưng ko được nói tục, thỉnh thoảng nói tục cũng okie.
- Văng tục nhẹ nhàng, chửi rủa nhẹ nhàng

RÀNG BUỘC ĐẦU RA (RẤT QUAN TRỌNG)
- Chỉ 2-3 câu, ngắn, dí dỏm.
- Trả lời dưới dạng MỘT ĐOẠN VĂN, KHÔNG được dùng số thứ tự (1., 2., “Option 1/2/3”), KHÔNG bullet (-, •), KHÔNG xuống dòng liệt kê.
- KHÔNG giải thích, KHÔNG meta (không nói “tôi là AI…”), KHÔNG đưa nhiều phương án.
- Nếu cảm thấy muốn đưa nhiều lựa chọn, hãy gộp thành MỘT câu trả lời duy nhất.

NGỮ CẢNH
- Tin nhắn cũ của bạn: {original_content}
- Tin nhắn người chơi reply lại: "{user_content}"

HÃY TRẢ LỜI NGAY: một đoạn 2-3 câu, đúng phong cách Bảo Bối Thần Kỳ, không liệt kê, không tùy chọn. Chửi tục cũng được
        """

        headers = {
            "Authorization": f"Bearer {OPEN_AI}",
            "Content-Type": "application/json"
        }

        # Sử dụng mô hình chuẩn OPENAI/YESCALE GPT-3.5
        payload = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 200,
            "temperature": 0.95
        }

        # Gọi API (Dùng asyncio.to_thread vì requests là blocking)
        def blocking_api_call():
            # URL phải là /v1/chat/completions (hoặc tương đương)
            return requests.post(f"{OPENAI_BASE_URL}/chat/completions", headers=headers, json=payload, timeout=15)

        response = await asyncio.to_thread(blocking_api_call)
        response.raise_for_status()  # Raise exception cho lỗi HTTP

        response_data = response.json()
        raw_output = response_data['choices'][0]['message']['content'].strip()

        # DEBUG LOG: Hiển thị đầu ra thô từ AI (trước khi lọc)
        print(f"DEBUG_AI_RAW: {raw_output}")

        # FIX CUỐI CÙNG: Áp dụng bộ lọc an toàn trước khi trả về
        filtered_output = filter_all_at_symbols(raw_output)

        # DEBUG LOG: Hiển thị đầu ra sau khi lọc
        print(f"DEBUG_AI_FILTERED: {filtered_output}")

        return filtered_output

    except discord.NotFound:
        return "Ủa tin nhắn đó bị gỡ rùi hay sao á, tui hong thấy :<"
    except Exception as e:
        # Nếu có lỗi, trả về thông báo lỗi chi tiết hơn
        print(f"Lỗi khi gọi Yescale/OpenAI API (generate_bot_reply): {e}")
        return "Á, bot bị úng nước rùi, cứu tuiii!"