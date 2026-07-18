import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import uvicorn
from google import genai  # <-- 使用最新版的套件
from dotenv import load_dotenv

# ==========================================
# 1. 初始化環境與最新版 Gemini 客戶端
# ==========================================
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("找不到 GEMINI_API_KEY，請確認 .env 檔案設定。")

# 新版 SDK 的初始化方式
client = genai.Client(api_key=GEMINI_API_KEY)

# ==========================================
# 2. 建立專屬衛教知識庫 (萃取自您的 8 份簡報)
# ==========================================
reference_data_db = {
    "健康數據與報告": {
        "keywords": ["血壓", "血糖", "膽固醇", "紅字", "健檢"],
        "content": "血壓正常值為120/80，超過140/90需追蹤。血糖方面，空腹血糖代表當下，糖化血色素代表三個月平均。膽固醇HDL(好)越高越好，LDL(壞)越低越好。健檢紅字不等於重病，應看長期趨勢並帶歷年報告詢問醫生。"
    },
    "用藥安全": {
        "keywords": ["藥", "藥袋", "吃藥", "停藥", "副作用"],
        "content": "藥袋就是安全說明書，務必看清楚用法。慢性病用藥與抗生素絕對不能因為覺得好多了就自行停藥，若有副作用疑慮請諮詢醫師。"
    },
    "網路謠言與查核": {
        "keywords": ["謠言", "假訊息", "偏方", "群組", "真的假的", "查核"],
        "content": "假訊息常有四特徵：標題農場(驚呆/救命)、假權威、神奇療效(包治百病)、製造恐慌。請記住四撇步過篩：看來源(.gov.tw才是官方)、查作者、對日期、想目的。遇到可疑訊息，可轉傳給 LINE 的「Cofacts 真的假的」或「MyGoPen」機器人幫忙查證。"
    },
    "數位隱私與資安": {
        "keywords": ["隱私", "個資", "詐騙", "藥袋照片", "權限", "165"],
        "content": "健康資料比信用卡還值錢！丟棄藥袋前務必撕碎個資，絕對不要在臉書或 LINE 貼出完整的看診單據或身分證號。對於 App 過度索取權限要保持警覺。若接到自稱健保局的異常電話，請直接掛斷並撥打 165 專線。"
    },
    "數位健康工具": {
        "keywords": ["手錶", "穿戴裝置", "健保快易通", "遠距醫療", "健康存摺", "掛號"],
        "content": "智慧手錶能即時偵測心跳、血氧與跌倒求救。健保快易通 App 裡的「健康存摺」可以查看過去就醫、用藥與抽血紀錄。遠距醫療(視訊看診)適合病情穩定的慢性病回診，若是急症或需要抽血仍須親赴醫院。"
    },
    "行為改變與習慣": {
        "keywords": ["習慣", "運動", "減肥", "堅持", "目標"],
        "content": "改變習慣失敗不是因為沒毅力，而是系統不對！建議設定極度「微小目標」(如每天喝杯水)，善用手機推播當作溫柔的鬧鐘，並告訴家人朋友一起互相督促。就算中間漏了一天也沒關係，重點是看長期的進步趨勢。"
    },
    "AI與醫療決策": {
        "keywords": ["AI", "人工智慧", "ChatGPT", "看病", "取代醫生"],
        "content": "醫療AI是醫師的超級智囊團，負責幫忙看 X 光片、聽寫病歷，但「絕對不會取代醫師」，最終決定權仍在醫師與病患。AI有時會「一本正經地胡說八道」，千萬不能用AI來自我診斷，但可以請AI幫忙把難懂的醫學名詞翻譯成白話文。"
    }
}

def get_reference_data(user_message: str) -> str:
    """檢索知識庫模組"""
    found_contents = []
    for topic, data in reference_data_db.items():
        if any(keyword in user_message for keyword in data["keywords"]):
            found_contents.append(f"【{topic}】：{data['content']}")
    return "\n\n".join(found_contents) if found_contents else ""

# ==========================================
# 3. 初始化 FastAPI 與網頁路由
# ==========================================
app = FastAPI(title="樂齡健康陪伴系統 API")

# 靜態檔案設定 (用於 favicon 等圖片)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

class UserMessage(BaseModel):
    message: str

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("static/favicon.ico")

@app.get("/apple-touch-icon{catchall:path}", include_in_schema=False)
async def apple_touch_icon():
    return FileResponse("static/apple-touch-icon.png")

# ==========================================
# 4. 處理聊天邏輯與新版 AI 串接
# ==========================================
@app.post("/api/chat")
async def chat_endpoint(data: UserMessage):
    user_text = data.message.strip()
    
    # 透過剛剛寫好的函數，抓取簡報知識
    reference_data = get_reference_data(user_text)
    
    # 組合 Prompt 提示詞
    if reference_data:
        prompt = f"""
        你現在是一位溫暖、親切、有耐心的台灣長者健康陪伴員。
        請「嚴格且唯一」根據以下的【參考資料】來回答長者的問題，絕對不可以自己編造未經證實的醫療建議。
        請用白話、溫柔、像是在跟長輩聊天的口吻回答（字數盡量控制在 120 字內）。

        【參考資料】：\n{reference_data}
        \n【長者問題】：{user_text}
        """
    else:
        prompt = f"""
        你現在是一位溫暖、親切、有耐心的台灣長者健康陪伴員。
        長者說了：「{user_text}」。
        請注意：你不能提供任何專業的醫療診斷或用藥建議。
        如果是醫療問題，請溫柔地關心長者，並建議他去大醫院看診或詢問專業醫師。
        如果只是一般閒聊或心情抒發，請給予溫暖的陪伴與傾聽。回覆請控制在 120 字以內，方便長者閱讀。
        """

    try:
        # 使用最新版 SDK 的呼叫方式
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        bot_reply = response.text.strip()
    except Exception as e:
        print(f"Gemini API 發生錯誤: {e}")
        bot_reply = "阿公/阿嬤拍謝，系統剛剛稍微卡住了，可以請您再說一次嗎？"
        
    return {"reply": bot_reply}

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)