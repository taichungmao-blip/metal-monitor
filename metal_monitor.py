import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import requests
import os
from datetime import datetime, timedelta

# ==========================================
# 1. 設定區域 (Configuration)
# ==========================================

# 監控清單
TARGETS = {
    "GC=F": "黃金期貨(美)",
    "SI=F": "白銀期貨(美)",
    "DX-Y.NYB": "美元指數",     # 黃金的對照組
    "00635U.TW": "元大S&P黃金", # 台股 ETF
    "9955.TW": "佳龍"          # 台股 貴金屬回收概念股
}

# 監控天數 (繪圖用)
LOOKBACK_DAYS = 180

# Discord Webhook (從 GitHub Secrets 讀取)
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# ==========================================
# 2. 技術指標計算
# ==========================================

def calculate_rsi(series, period=14):
    """計算 RSI 相對強弱指標"""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def get_market_data():
    """下載數據"""
    start_date = (datetime.now() - timedelta(days=LOOKBACK_DAYS + 30)).strftime('%Y-%m-%d')
    tickers = list(TARGETS.keys())
    print(f"下載數據中... {tickers}")
    
    # 下載並填補空值
    data = yf.download(tickers, start=start_date, progress=False)['Close']
    data = data.ffill()
    return data

# ==========================================
# 3. 策略判讀核心
# ==========================================

def analyze_strategy(df, code):
    """
    針對單一標的進行技術面與趨勢判讀
    """
    try:
        prices = df[code]
        current_price = prices.iloc[-1]
        prev_price = prices.iloc[-2]
        change_pct = ((current_price - prev_price) / prev_price) * 100
        
        # 計算 RSI (近14日)
        rsi_series = calculate_rsi(prices)
        current_rsi = rsi_series.iloc[-1]
        
        # 判斷趨勢與狀態
        status_icon = ""
        status_msg = ""
        
        # A. 漲跌幅判斷
        if change_pct > 2.0: status_icon = "🔥" # 大漲
        elif change_pct < -2.0: status_icon = "❄️" # 大跌
        elif change_pct > 0: status_icon = "📈"
        else: status_icon = "📉"
        
        # B. RSI 策略判讀 (過熱/超賣)
        rsi_note = ""
        if current_rsi > 75:
            rsi_note = " (⚠️過熱 | 勿追高)"
        elif current_rsi > 50:
            rsi_note = " (💪強勢區)"
        elif current_rsi < 30:
            rsi_note = " (✨超賣 | 反彈機會)"
        else:
            rsi_note = " (➡️盤整)"
            
        return {
            "price": current_price,
            "change": change_pct,
            "rsi": current_rsi,
            "icon": status_icon,
            "note": rsi_note
        }
    except Exception as e:
        return None

def send_discord_notify(msg, img_path=None):
    if not DISCORD_WEBHOOK_URL:
        print("⚠️ 未設定 Webhook，跳過發送")
        return
    
    data = {"content": msg}
    files = {}
    if img_path and os.path.exists(img_path):
        files = {"file": (os.path.basename(img_path), open(img_path, "rb"))}
    
    try:
        if files:
            requests.post(DISCORD_WEBHOOK_URL, data=data, files=files)
        else:
            requests.post(DISCORD_WEBHOOK_URL, json=data)
        print("✅ Discord 通知發送成功")
    finally:
        if files: files["file"][1].close()

def plot_chart(df):
    """繪製 黃金 vs 美元 vs 台股黃金ETF"""
    plt.figure(figsize=(12, 6))
    plt.style.use('bmh')
    
    # 正規化 (以第一天為 100)
    norm_df = (df / df.iloc[0]) * 100
    
    # 繪製主線
    plt.plot(norm_df.index, norm_df['GC=F'], label='Gold (Global)', color='gold', linewidth=2.5)
    plt.plot(norm_df.index, norm_df['00635U.TW'], label='TW Gold ETF (00635U)', color='orange', linestyle='--')
    plt.plot(norm_df.index, norm_df['DX-Y.NYB'], label='USD Index (DXY)', color='gray', alpha=0.5)
    
    plt.title(f"Gold vs. Taiwan ETF vs. USD ({LOOKBACK_DAYS} Days)")
    plt.legend()
    plt.grid(True)
    
    img_path = "gold_chart.png"
    plt.savefig(img_path)
    plt.close()
    return img_path

# ==========================================
# 4. 主程式
# ==========================================

def main():
    try:
        df = get_market_data()
        if df.empty: return
        
        # 1. 計算金銀比 (Gold / Silver Ratio)
        gold_price = df['GC=F'].iloc[-1]
        silver_price = df['SI=F'].iloc[-1]
        gs_ratio = gold_price / silver_price
        
        # 金銀比解讀
        gs_status = ""
        if gs_ratio > 85: gs_status = "⚪️ 白銀超跌 (補漲機會大)"
        elif gs_ratio < 60: gs_status = "🟡 黃金強勢"
        else: gs_status = "⚖️ 區間正常"

        # 2. 產生圖表
        img_path = plot_chart(df)
        
        # 3. 組合訊息
        date_str = df.index[-1].strftime('%Y-%m-%d')
        msg = f"**【👑 貴金屬戰情室】**\n📅 `{date_str}`\n"
        msg += f"⚖️ **金銀比**: `{gs_ratio:.1f}` - {gs_status}\n\n"
        
        msg += "**📊 行情掃描 (含 RSI 策略):**\n"
        
        # 依照順序報告
        report_order = ["GC=F", "SI=F", "00635U.TW", "9955.TW", "DX-Y.NYB"]
        
        for code in report_order:
            if code not in df.columns: continue
            
            name = TARGETS.get(code, code)
            result = analyze_strategy(df, code)
            
            if result:
                msg += f"> **{name}** `{result['price']:.2f}`\n"
                msg += f"> {result['icon']} 漲跌: `{result['change']:+.2f}%` | RSI: `{result['rsi']:.1f}`{result['note']}\n\n"

        msg += "💡 *策略筆記：RSI > 75 留意回檔；美元指數(DXY)若強彈，不利金價。*"
        
        send_discord_notify(msg, img_path)

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
