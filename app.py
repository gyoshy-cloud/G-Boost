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

# --- 初期設定とセッション管理 ---
st.set_page_config(page_title="G-Boost", page_icon="🚀")

# 挑戦ごとのデータを保存する箱（セッションステート）を準備
if "attempts" not in st.session_state:
    st.session_state.attempts = 0
    st.session_state.total_time = 0.0
    st.session_state.highest_score = 0
    st.session_state.last_processed_audio = None

st.title("🚀 G-Boost: 英語音読トレーニング")
st.caption("音読を重ねてスコアをBoostしよう！")

# --- 1. サイドバー（設定・情報入力） ---
with st.sidebar:
    st.header("⚙️ 設定")
    student_api_key = st.text_input("Gemini API Key", type="password")
    
    st.header("👤 あなたの情報")
    student_id = st.text_input("生徒番号（4ケタ）", max_chars=4, placeholder="例: 1101")
    
if student_api_key:
    genai.configure(api_key=student_api_key)

# --- 2. ファイルの読み込み ---
uploaded_file = st.file_uploader("先生から配布された課題(PDF/Word)を選択", type=["pdf", "docx"])
source_text = ""
base_filename = "課題" # デフォルトのファイル名

if uploaded_file:
    # 拡張子を除いた元のファイル名を取得
    base_filename = uploaded_file.name.rsplit('.', 1)[0]
    
    if uploaded_file.type == "application/pdf":
        reader = PyPDF2.PdfReader(uploaded_file)
        for page in reader.pages:
            source_text += page.extract_text()
    elif uploaded_file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        source_text = docx2txt.process(uploaded_file)
    
    st.text_area("📖 課題の英文:", value=source_text, height=150, disabled=True)

# --- 3. 録音と音声処理 ---
st.subheader("🎙️ 音読をスタート")
audio_bytes = audio_recorder(text="クリックして録音開始 / 停止", pause_threshold=2.0, sample_rate=41_000)

if audio_bytes and source_text and student_api_key and student_id:
    st.audio(audio_bytes, format="audio/wav")
    
    # 録音時間（秒）を計算
    with wave.open(io.BytesIO(audio_bytes), 'rb') as w:
        frames = w.getnframes()
        rate = w.getframerate()
        audio_duration = frames / float(rate)
    
    st.write(f"⏱️ 録音時間: {audio_duration:.1f} 秒")

    # 同じ音声を何度も採点しないようにチェック
    if audio_bytes != st.session_state.last_processed_audio:
        if st.button("✨ この録音を採点する"):
            with st.spinner("AIが発音を分析中..."):
                try:
                    model = genai.GenerativeModel('gemini-3-flash')
                    
                    # AIへの指示（確実に点数を抽出できるようにフォーマットを固定）
                    prompt = f"""
                    あなたは英語教師です。以下の「元の英文」と「音声データ」を比較してください。
                    元の英文: {source_text}
                    
                    タスク:
                    1. 音声を文字起こしする。
                    2. 元の文と比較し、100点満点で採点する。
                    3. 発音のアドバイスを日本語で簡潔に行う。
                    
                    【重要】必ず以下のフォーマットで出力してください。
                    【スコア】〇〇
                    【文字起こし】...
                    【アドバイス】...
                    """
                    
                    response = model.generate_content([
                        prompt,
                        {"mime_type": "audio/wav", "data": audio_bytes}
                    ])
                    evaluation = response.text
                    
                    # 正規表現でスコアを抽出
                    score_match = re.search(r"【スコア】\s*(\d+)", evaluation)
                    current_score = int(score_match.group(1)) if score_match else 0
                    
                    # データの更新
                    st.session_state.attempts += 1
                    st.session_state.total_time += audio_duration
                    if current_score > st.session_state.highest_score:
                        st.session_state.highest_score = current_score
                    st.session_state.last_processed_audio = audio_bytes
                    
                    st.success(f"今回のスコア: {current_score}点！")
                    st.markdown("### 📝 フィードバック")
                    st.write(evaluation)
                    
                except Exception as e:
                    st.error(f"エラーが発生しました: {e}")
    else:
        st.info("この録音は採点済みです。もう一度録音し直すと、再度採点できます。")

# --- 4. データの集計と提出（CSVダウンロード） ---
if st.session_state.attempts > 0:
    st.divider()
    st.subheader("📊 あなたの成績データ")
    
    avg_time = st.session_state.total_time / st.session_state.attempts
    
    col1, col2, col3 = st.columns(3)
    col1.metric("音読回数", f"{st.session_state.attempts} 回")
    col2.metric("最高得点", f"{st.session_state.highest_score} 点")
    col3.metric("平均タイム", f"{avg_time:.1f} 秒")
    
    # CSVデータの作成
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # DataFrameを作成
    df = pd.DataFrame([{
        "提出タイムスタンプ": timestamp,
        "音読回数": st.session_state.attempts,
        "音読平均タイム": round(avg_time, 1),
        "最高得点": st.session_state.highest_score
    }])
    
    # CSVに変換 (utf-8-sigにすることでExcelでの文字化けを防ぐ)
    csv_data = df.to_csv(index=False).encode('utf-8-sig')
    
    # ファイル名の生成（例：HW_Unit1_1101.csv）
    export_filename = f"{base_filename}_{student_id}.csv"
    
    st.markdown("### 📤 Classroomへ提出")
    st.download_button(
        label=f"成績データ ({export_filename}) をダウンロード",
        data=csv_data,
        file_name=export_filename,
        mime="text/csv",
        type="primary"
    )

elif not student_api_key or not student_id:
    st.warning("👈 左側のメニューから、APIキーと生徒番号を入力してください。")
