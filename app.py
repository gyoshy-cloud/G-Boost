import streamlit as st
import google.generativeai as genai
from audio_recorder_streamlit import audio_recorder
import docx2txt
import PyPDF2
import io
import wave
import re
import pandas as pd
from datetime import datetime

# --- 1. スタイル設定（明滅アニメーション） ---
st.set_page_config(page_title="G-Boost", page_icon="🚀")

st.markdown("""
    <style>
    @keyframes blinker {
      50% { opacity: 0; }
    }
    .blink-record {
      animation: blinker 1s linear infinite;
      color: #FF4B4B;
      font-weight: bold;
      font-size: 20px;
    }
    .blink-score {
      animation: blinker 1s linear infinite;
      color: #0083B0;
      font-weight: bold;
      font-size: 20px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 初期設定とセッション管理 ---
if "attempts" not in st.session_state:
    st.session_state.attempts = 0
    st.session_state.total_time = 0.0
    st.session_state.highest_score = 0
    st.session_state.last_processed_audio = None

st.title("🚀 G-Boost")
st.caption("英語音読トレーニング・システム")

# --- 3. サイドバー ---
with st.sidebar:
    st.header("⚙️ 設定")
    student_api_key = st.text_input("Gemini API Key", type="password")
    student_id = st.text_input("生徒番号（4ケタ）", max_chars=4, placeholder="例: 1101")
    
    st.divider()
    st.info("💡 Chromebookでマイクが動かない場合、アドレスバー左の『鍵マーク』をクリックして、マイクの使用が『許可』されているか確認してください。")

if student_api_key:
    genai.configure(api_key=student_api_key)

# --- 4. ファイル読み込み ---
uploaded_file = st.file_uploader("教材ファイル(PDF/Word)を選択", type=["pdf", "docx"])
source_text = ""
base_filename = "課題"

if uploaded_file:
    base_filename = uploaded_file.name.rsplit('.', 1)[0]
    if uploaded_file.type == "application/pdf":
        reader = PyPDF2.PdfReader(uploaded_file)
        for page in reader.pages:
            source_text += page.extract_text()
    elif uploaded_file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        source_text = docx2txt.process(uploaded_file)
    
    st.text_area("📖 英文テキスト:", value=source_text, height=150, disabled=True)

# --- 5. 録音セクション ---
st.subheader("🎙️ 音読録音")
st.write("マイクアイコンをクリックして開始、もう一度押して停止します。")

# audio_recorder自体に「録音中」の文字を表示させる設定
audio_bytes = audio_recorder(
    text="ここをクリックして録音",
    recording_color="#e74c3c",
    neutral_color="#95a5a6",
    icon_name="microphone",
    icon_size="3x"
)

# 録音中の表示（audio_bytesがNoneの時は待機、データが生成されるまで明滅させることは
# ライブラリの仕様上難しいため、録音直後にデータを確認する仕組みにします）
if audio_bytes:
    st.audio(audio_bytes, format="audio/wav")
    
    # 録音時間の計算
    with wave.open(io.BytesIO(audio_bytes), 'rb') as w:
        frames = w.getnframes()
        rate = w.getframerate()
        audio_duration = frames / float(rate)
    
    st.write(f"⏱️ 録音完了: {audio_duration:.1f} 秒")

    # 採点処理
    if audio_bytes != st.session_state.last_processed_audio:
        if st.button("✨ 採点する"):
            # 採点中の明滅表示
            scoring_status = st.empty()
            scoring_status.markdown('<p class="blink-score">🔄 採点中... AIが分析しています</p>', unsafe_allow_html=True)
            
            try:
                # 2026年現在の安定モデル名に修正（404対策）
                model = genai.GenerativeModel('gemini-2.0-flash')
                
                prompt = f"""
                あなたは英語教師です。以下の「元の英文」と「音声」を比較し、採点してください。
                元の英文: {source_text}
                
                【フォーマット】
                【スコア】（0〜100の数字のみ）
                【文字起こし】（聞こえた英文）
                【アドバイス】（日本語で簡潔に）
                """
                
                response = model.generate_content([
                    prompt,
                    {"mime_type": "audio/wav", "data": audio_bytes}
                ])
                
                evaluation = response.text
                
                # スコア抽出
                score_match = re.search(r"【スコア】\s*(\d+)", evaluation)
                current_score = int(score_match.group(1)) if score_match else 0
                
                # 成績更新
                st.session_state.attempts += 1
                st.session_state.total_time += audio_duration
                if current_score > st.session_state.highest_score:
                    st.session_state.highest_score = current_score
                st.session_state.last_processed_audio = audio_bytes
                
                # 採点中メッセージを消して結果を表示
                scoring_status.empty()
                st.success(f"採点完了！ スコア: {current_score}")
                st.markdown(evaluation)
                
            except Exception as e:
                scoring_status.empty()
                st.error(f"エラーが発生しました。APIキーが正しいか確認してください: {e}")
    else:
        st.info("この録音は採点済みです。新しく録音し直してください。")

# --- 6. 集計と提出 ---
if st.session_state.attempts > 0:
    st.divider()
    st.subheader("📊 今回の成績")
    
    avg_time = st.session_state.total_time / st.session_state.attempts
    col1, col2, col3 = st.columns(3)
    col1.metric("練習回数", f"{st.session_state.attempts}回")
    col2.metric("ベストスコア", f"{st.session_state.highest_score}点")
    col3.metric("平均タイム", f"{avg_time:.1f}秒")
    
    df = pd.DataFrame([{
        "提出タイムスタンプ": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "音読回数": st.session_state.attempts,
        "音読平均タイム": round(avg_time, 1),
        "最高得点": st.session_state.highest_score
    }])
    
    csv_data = df.to_csv(index=False).encode('utf-8-sig')
    export_filename = f"{base_filename}_{student_id}.csv"
    
    st.download_button(
        label="CSV形式で成績をダウンロード",
        data=csv_data,
        file_name=export_filename,
        mime="text/csv",
        type="primary"
    )
elif not student_api_key or not student_id:
    st.warning("👈 左側のサイドバーからAPIキーと生徒番号を入力してください。")
