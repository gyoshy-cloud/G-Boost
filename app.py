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

# --- 1. 画面表示の設定とCSS（明滅アニメーション） ---
st.set_page_config(page_title="G-Boost", page_icon="🚀")

# 文字を明滅させるためのスタイル設定
st.markdown("""
    <style>
    @keyframes blinker {
      50% { opacity: 0; }
    }
    .blink-score {
      animation: blinker 1s linear infinite;
      color: #0083B0;
      font-weight: bold;
      font-size: 24px;
      margin: 10px 0;
    }
    .instruction {
      background-color: #f0f2f6;
      padding: 15px;
      border-radius: 10px;
      border-left: 5px solid #ff4b4b;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. データの記録（セッション管理） ---
if "attempts" not in st.session_state:
    st.session_state.attempts = 0
    st.session_state.total_time = 0.0
    st.session_state.highest_score = 0
    st.session_state.last_processed_audio = None

st.title("🚀 G-Boost")
st.caption("AI英語音読トレーニング・システム")

# --- 3. サイドバー（設定） ---
with st.sidebar:
    st.header("⚙️ 設定")
    student_api_key = st.text_input("Gemini API Key", type="password")
    student_id = st.text_input("生徒番号（4ケタ）", max_chars=4, placeholder="例: 1101")
    
    st.divider()
    st.write("📖 **使い方**")
    st.write("1. APIキーと生徒番号を入力")
    st.write("2. 先生からのPDF/Wordを読み込む")
    st.write("3. マイクボタンで音読を録音")
    st.write("4. 採点してCSVをClassroomに提出")

# --- 4. ファイル読み込みセクション ---
uploaded_file = st.file_uploader("課題ファイルを選択 (PDFまたはWord)", type=["pdf", "docx"])
source_text = ""
base_filename = "assignment"

if uploaded_file:
    # 拡張子を除いたファイル名を取得
    base_filename = uploaded_file.name.rsplit('.', 1)[0]
    
    if uploaded_file.type == "application/pdf":
        reader = PyPDF2.PdfReader(uploaded_file)
        for page in reader.pages:
            source_text += page.extract_text()
    elif uploaded_file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        source_text = docx2txt.process(uploaded_file)
    
    st.text_area("📖 課題の英文:", value=source_text, height=150, disabled=True)

# --- 5. 録音セクション ---
st.subheader("🎙️ 音読を録音する")

# マイクが反応しない生徒向けのアドバイス
with st.expander("マイクが反応しない場合はこちら"):
    st.info("ブラウザのアドレスバー左側にある『鍵マーク』をクリックして、マイクが『許可』されているか確認してください。")

# 録音コンポーネント
audio_bytes = audio_recorder(
    text="ボタンを押して録音開始 / 停止",
    recording_color="#e74c3c",
    neutral_color="#95a5a6",
    icon_size="3x"
)

if audio_bytes:
    st.audio(audio_bytes, format="audio/wav")
    
    # 録音時間の計算
    with wave.open(io.BytesIO(audio_bytes), 'rb') as w:
        frames = w.getnframes()
        rate = w.getframerate()
        audio_duration = frames / float(rate)
    
    st.write(f"⏱️ 録音時間: {audio_duration:.1f} 秒")

    # --- 6. 採点セクション ---
    if student_api_key and student_id and source_text:
        if audio_bytes != st.session_state.last_processed_audio:
            if st.button("✨ 採点する", type="primary"):
                # 採点中の明滅表示を開始
                placeholder = st.empty()
                placeholder.markdown('<p class="blink-score">🔄 採点中... AIが分析しています</p>', unsafe_allow_html=True)
                
                try:
                    # APIの初期化
                    genai.configure(api_key=student_api_key)
                    
                    # 【自動モデル検知】今使える最適なモデルを探す
                    available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                    
                    # 優先順位（3-flash -> 2.0-flash -> 1.5-flash）
                    target_model = None
                    for m_name in ['models/gemini-3-flash', 'models/gemini-2.0-flash', 'models/gemini-1.5-flash']:
                        if m_name in available_models:
                            target_model = m_name
                            break
                    
                    if not target_model:
                        target_model = available_models[0] # 見つからなければリストの先頭を使用

                    model = genai.GenerativeModel(target_model)
                    
                    prompt = f"""
                    あなたは英語教師です。以下の「元の英文」と提供された「音声データ」を比較し、採点してください。
                    元の英文: {source_text}
                    
                    【出力形式】
                    【スコア】（0〜100の数値のみ）
                    【文字起こし】（聞こえた英文をそのまま書き出す）
                    【アドバイス】（日本語で改善点を簡潔に）
                    """
                    
                    response = model.generate_content([
                        prompt,
                        {"mime_type": "audio/wav", "data": audio_bytes}
                    ])
                    
                    # 明滅表示を消去
                    placeholder.empty()
                    
                    result_text = response.text
                    
                    # スコアを数字だけ抽出
                    score_match = re.search(r"【スコア】\s*(\d+)", result_text)
                    current_score = int(score_match.group(1)) if score_match else 0
                    
                    # データの記録更新
                    st.session_state.attempts += 1
                    st.session_state.total_time += audio_duration
                    if current_score > st.session_state.highest_score:
                        st.session_state.highest_score = current_score
                    st.session_state.last_processed_audio = audio_bytes
                    
                    # 結果表示
                    st.success(f"採点完了！ (使用モデル: {target_model})")
                    st.markdown(f"### 🎯 今回のスコア: {current_score}点")
                    st.markdown(result_text)
                    
                except Exception as e:
                    placeholder.empty()
                    st.error(f"エラーが発生しました: {e}")
                    st.info("※ 429エラーの場合は、1分待ってから再度ボタンを押してください。")
        else:
            st.info("この録音は採点済みです。もう一度練習する場合は、新しく録音してください。")
    elif not student_id:
        st.warning("生徒番号（4ケタ）を入力してください。")
    elif not student_api_key:
        st.warning("APIキーを入力してください。")

# --- 7. 成績集計とCSV書き出し ---
if st.session_state.attempts > 0:
    st.divider()
    st.subheader("📊 今回の学習記録")
    
    avg_time = st.session_state.total_time / st.session_state.attempts
    
    c1, c2, c3 = st.columns(3)
    c1.metric("音読回数", f"{st.session_state.attempts} 回")
    c2.metric("最高得点", f"{st.session_state.highest_score} 点")
    c3.metric("平均タイム", f"{avg_time:.1f} 秒")
    
    # CSVデータの準備
    submit_data = pd.DataFrame([{
        "提出タイムスタンプ": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "音読回数": st.session_state.attempts,
        "音読平均タイム": round(avg_time, 1),
        "最高得点": st.session_state.highest_score
    }])
    
    # Excel文字化け対策 (utf-8-sig)
    csv = submit_data.to_csv(index=False).encode('utf-8-sig')
    
    # ファイル名: 元のファイル名 + 生徒番号
    filename = f"{base_filename}_{student_id}.csv"
    
    st.download_button(
        label=f"成績をCSVでダウンロード ({filename})",
        data=csv,
        file_name=filename,
        mime="text/csv",
        type="primary"
    )
