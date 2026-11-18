import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import random
import os
import json
import socket
import io
import qrcode
from datetime import datetime

# 画面の基本設定
st.set_page_config(page_title="デュエマ イベント運営アプリ", layout="wide")

# ==========================================
# 🛡️ パソコンで動かしている時だけスリープ防止を作動
# ==========================================
def prevent_sleep():
    if os.name == "nt":
        try:
            import ctypes
            ES_CONTINUOUS = 0x80000000
            ES_SYSTEM_REQUIRED = 0x00000001
            ES_DISPLAY_REQUIRED = 0x00000002
            ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
            )
            return True
        except Exception:
            return False
    return False

SLEEP_PREVENTED = prevent_sleep()

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"

# データの保存先フォルダ
EVENTS_DIR = "events_data"
CONFIG_FILE = os.path.join(EVENTS_DIR, "config.json")
os.makedirs(EVENTS_DIR, exist_ok=True)

# --- 1. イベント管理＆データの読み込み・保存機能 ---
def get_Initial_event_data():
    return {
        "divisions": ["カジュアル", "ガチ", "デュエパ", "05環境", "08環境"],
        "total_tables": 20,
        "min_wait_players": 2,
        "refresh_sec": 30,
        "players": {},
        "matches": [],
        "lottery_winners": [],
        "last_created_match_ids": []
    }

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            if "admin_password" not in cfg:
                cfg["admin_password"] = "1234"
            if "app_url" not in cfg:
                cfg["app_url"] = ""
            return cfg
    else:
        default_event = datetime.now().strftime("%Y-%m-%d_第1回イベント")
        cfg = {
            "current_event": default_event,
            "events": [default_event],
            "admin_password": "1234",
            "app_url": ""
        }
        save_config(cfg)
        return cfg

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

config = load_config()
current_event = config["current_event"]

DATA_FILE = os.path.join(EVENTS_DIR, f"{current_event}.json")
SURVEY_FILE = os.path.join(EVENTS_DIR, f"{current_event}_アンケート結果.csv")
PLAYERS_CSV_FILE = os.path.join(EVENTS_DIR, f"{current_event}_参加者リスト.csv")

def normalize_event_data(d):
    if "refresh_sec" not in d:
        d["refresh_sec"] = 30
    if "last_created_match_ids" not in d:
        d["last_created_match_ids"] = []
    if "divisions" not in d:
        d["divisions"] = ["カジュアル", "ガチ", "デュエパ", "05環境", "08環境"]
    if "total_tables" not in d:
        d["total_tables"] = 20
    if "min_wait_players" not in d:
        d["min_wait_players"] = 2
    if "players" not in d:
        d["players"] = {}
    if "matches" not in d:
        d["matches"] = []
    if "lottery_winners" not in d:
        d["lottery_winners"] = []

    for m in d.get("matches", []):
        if "players" not in m:
            m["players"] = [m.get("p1"), m.get("p2")]
        if "created_at" not in m:
            m["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for pid, p in d.get("players", {}).items():
        if "dmp_id" not in p:
            p["dmp_id"] = ""
        if "survey_done" not in p:
            p["survey_done"] = False
        if "pass_given" not in p:
            p["pass_given"] = False
    return d

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
            return normalize_event_data(d)
    else:
        init_data = get_Initial_event_data()
        save_data(init_data)
        return init_data

def save_data(d):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

data = load_data()
refresh_sec = data.get("refresh_sec", 30)

# --- 📌 自分の名前（ID）をスマホのURLに記憶・固定する機能 ---
def get_pinned_pid():
    pid = st.query_params.get("pid", None)
    if pid and pid in data["players"]:
        return pid
    return None

def set_pinned_pid(pid):
    if pid:
        st.query_params["pid"] = pid
    else:
        st.query_params.clear()

# --- 経過時間を計算して「🆕新着」かどうか判定する関数 ---
def get_match_age_info(m):
    created_str = m.get("created_at", "")
    try:
        dt = datetime.strptime(created_str, "%Y-%m-%d %H:%M:%S")
        diff_sec = (datetime.now() - dt).total_seconds()
        mins = int(diff_sec // 60)
        time_only = dt.strftime("%H:%M:%S")
        is_new = (diff_sec <= 180) or (m.get("match_id") in data.get("last_created_match_ids", []))
        return is_new, time_only, f"{mins}分前" if mins > 0 else "たった今"
    except Exception:
        return False, "--:--", "-"

# --- 2. マッチング機能 ---
def auto_match(division_name, force=False):
    waiting_ids = [
        pid for pid, p in data["players"].items()
        if p["division"] == division_name and p["status"] == "待機中"
    ]
    
    used_tables = [m["table"] for m in data["matches"] if m["status"] == "対戦中"]
    free_tables = [t for t in range(1, data["total_tables"] + 1) if t not in used_tables]

    new_match_ids = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ★ デュエパ部門（4人マッチング・一部重複OK）
    if "デュエパ" in division_name:
        if len(waiting_ids) < 4:
            return []
            
        random.shuffle(waiting_ids)
        past_groups = [set(m.get("players", [])) for m in data["matches"] if m["division"] == division_name]
        
        while len(waiting_ids) >= 4 and free_tables:
            group = waiting_ids[:4]
            if set(group) in past_groups and len(waiting_ids) > 4:
                for _ in range(5):
                    random.shuffle(waiting_ids)
                    group = waiting_ids[:4]
                    if set(group) not in past_groups:
                        break
                        
            for pid in group:
                waiting_ids.remove(pid)
                
            table_num = free_tables.pop(0)
            for pid in group:
                data["players"][pid]["status"] = "対戦中"
                for other_pid in group:
                    if other_pid != pid:
                        data["players"][pid]["opponents"].append(other_pid)
                        
            match_id = f"M4_{datetime.now().strftime('%H%M%S')}_{table_num}"
            data["matches"].append({
                "match_id": match_id,
                "division": division_name,
                "table": table_num,
                "players": group,
                "status": "対戦中",
                "created_at": now_str
            })
            new_match_ids.append(match_id)
            
        if new_match_ids:
            data["last_created_match_ids"] = new_match_ids
            save_data(data)
        return new_match_ids

    # ★ 通常部門（2人マッチング）
    else:
        required_wait = 2 if force else data["min_wait_players"]
        if len(waiting_ids) < required_wait:
            return []

        random.shuffle(waiting_ids)
        waiting_ids.sort(key=lambda pid: data["players"][pid]["wins"], reverse=True)

        used_players = set()

        for i, p1_id in enumerate(waiting_ids):
            if p1_id in used_players or not free_tables:
                continue
            p1 = data["players"][p1_id]
            
            partner_id = None
            for p2_id in waiting_ids[i+1:]:
                if p2_id in used_players:
                    continue
                if p2_id not in p1["opponents"]:
                    partner_id = p2_id
                    break
            
            if not partner_id and force:
                for p2_id in waiting_ids[i+1:]:
                    if p2_id not in used_players:
                        partner_id = p2_id
                        break
            
            if partner_id:
                table_num = free_tables.pop(0)
                used_players.add(p1_id)
                used_players.add(partner_id)
                
                data["players"][p1_id]["status"] = "対戦中"
                data["players"][partner_id]["status"] = "対戦中"
                data["players"][p1_id]["opponents"].append(partner_id)
                data["players"][partner_id]["opponents"].append(p1_id)
                
                match_id = f"M2_{datetime.now().strftime('%H%M%S')}_{table_num}"
                data["matches"].append({
                    "match_id": match_id,
                    "division": division_name,
                    "table": table_num,
                    "players": [p1_id, partner_id],
                    "status": "対戦中",
                    "created_at": now_str
                })
                new_match_ids.append(match_id)

        if new_match_ids:
            data["last_created_match_ids"] = new_match_ids
            save_data(data)
        return new_match_ids

def auto_match_all_divisions(force=False):
    all_new_ids = []
    for div in data["divisions"]:
        created_ids = auto_match(div, force=force)
        all_new_ids.extend(created_ids)
    if all_new_ids:
        data["last_created_match_ids"] = all_new_ids
        save_data(data)
    return all_new_ids

auto_match_all_divisions(force=False)

# --- 3. サイドバーメニュー ＆ 自動更新設定 ---
st.sidebar.title("メニュー切り替え")
st.sidebar.caption(f"現在開催中: **{current_event}**")

pinned_pid = get_pinned_pid()
if pinned_pid:
    st.sidebar.info(f"📌 固定中: **{pinned_pid}: {data['players'][pinned_pid]['name']}**")

if SLEEP_PREVENTED:
    st.sidebar.success("🛡️ PCスリープ防止：作動中")

mode = st.sidebar.radio("画面を選んでください", ["📱 プレイヤー画面", "💻 スタッフ管理画面", "📝 アンケート回答"])

st.sidebar.divider()
auto_refresh = st.sidebar.checkbox(f"⏱️ {refresh_sec}秒ごとに自動更新＆マッチング", value=True)
if auto_refresh and mode != "📝 アンケート回答":
    st.sidebar.caption(f"※{refresh_sec}秒ごとに自動で画面を更新します（固定した名前は維持されます）。")
    components.html(
        f"""
        <script>
            setTimeout(function(){{
                window.parent.location.reload();
            }}, {refresh_sec * 1000});
        </script>
        """,
        height=0
    )
elif mode == "📝 アンケート回答":
    st.sidebar.caption("※アンケート入力中は文字が消えないよう自動更新を一時停止しています。")

if st.sidebar.button("🔄 今すぐ画面を最新状態に更新"):
    st.rerun()

# ==========================================
# 📱 プレイヤー画面（自分の名前固定機能つき）
# ==========================================
if mode == "📱 プレイヤー画面":
    st.title("🐉 デュエマ イベント プレイヤー画面")
    st.caption(f"イベント名: {current_event}")

    pinned_pid = get_pinned_pid()

    if not pinned_pid:
        st.subheader("1. 参加登録 または 自分の名前を画面に固定する")
        st.write("一度登録・固定すると、次回からリストで探さなくても常にあなたの専用画面が一番上に表示されます！")
        
        tab_new, tab_select = st.tabs(["✨ 新しくイベントに参加登録する", "🔍 登録済みの自分の名前を選んで固定する"])
        
        with tab_new:
            new_name = st.text_input("あなたのプレイヤー名（ハンドルネーム）を入力")
            new_dmp_id = st.text_input("DMPIDを入力（番号）")
            init_div = st.selectbox("最初に参加する部門を選択", data["divisions"])
            if st.button("🚀 イベントに参加登録して自分の画面を固定する", type="primary"):
                if new_name:
                    existing_nums = [int(pid[1:]) for pid in data["players"].keys() if pid[1:].isdigit()]
                    next_num = max(existing_nums, default=0) + 1
                    new_id = f"P{next_num:03d}"
                    
                    data["players"][new_id] = {
                        "name": new_name,
                        "dmp_id": new_dmp_id,
                        "division": init_div,
                        "status": "待機中",
                        "wins": 0,
                        "losses": 0,
                        "opponents": [],
                        "survey_done": False,
                        "pass_given": False
                    }
                    save_data(data)
                    auto_match(init_div, force=False)
                    set_pinned_pid(new_id)
                    st.success(f"登録完了！あなたのID「{new_id} ({new_name})」をこの画面に固定しました！")
                    st.rerun()
                else:
                    st.error("プレイヤー名を入力してください。")

        with tab_select:
            player_names = {pid: p["name"] for pid, p in data["players"].items()}
            if not player_names:
                st.info("まだ参加者がいません。左のタブから新規登録してください。")
            else:
                select_pid = st.selectbox(
                    "リストから自分の名前を選んでください（文字を入力すると絞り込み検索もできます）",
                    options=list(player_names.keys()),
                    format_func=lambda x: f"{x}: {player_names[x]} （{data['players'][x]['division']}）"
                )
                if st.button("📌 この名前を自分のスマホ画面に固定する", type="primary"):
                    set_pinned_pid(select_pid)
                    st.rerun()

    else:
        selected_pid = pinned_pid
        p_info = data["players"][selected_pid]
        
        col_title, col_unpin = st.columns([3, 1])
        with col_title:
            st.success(f"📌 **あなたの専用画面： {selected_pid} : {p_info['name']} さん**")
        with col_unpin:
            if st.button("🔄 別の人に切り替える"):
                set_pinned_pid(None)
                st.rerun()

        survey_badge = "✅回答済" if p_info.get("survey_done") else "❌未回答"
        pass_badge = "🎫受取済" if p_info.get("pass_given") else "未受取"
        
        st.write(f"**DMPID:** {p_info.get('dmp_id', '未登録')} ｜ **現在の部門:** {p_info['division']} ｜ **状態:** {p_info['status']} ｜ **戦績:** {p_info['wins']}勝 {p_info['losses']}敗")
        st.caption(f"アンケート状態: **{survey_badge}** ｜ 参加証: **{pass_badge}**")

        if selected_pid in data["lottery_winners"]:
            st.balloons()
            st.success("🎉 おめでとうございます！ランダム賞（抽選）に当選しました！スタッフ席へお越しください！")

        st.divider()

        if p_info["status"] == "対戦中":
            current_match = next((m for m in data["matches"] if m["status"] == "対戦中" and selected_pid in m.get("players", [])), None)
            if current_match:
                m_players = current_match.get("players", [])
                other_pids = [pid for pid in m_players if pid != selected_pid]
                other_names = [data["players"].get(pid, {}).get("name", "不明") for pid in other_pids]
                is_new, time_str, ago_str = get_match_age_info(current_match)
                new_label = "🆕【新着マッチング！】 " if is_new else ""
                
                st.info(f"🔥 **{new_label}【対戦案内】 第 {current_match['table']} 番卓** へ移動してください！（開始: {time_str}）\n\n**対戦相手:** {' さん / '.join(other_names)} さん（{current_match['division']}部門）")
                
                if len(m_players) > 2:
                    st.write("### 👇 対戦が終わったら代表者1名が結果ボタンを押してください")
                    col1, col2 = st.columns(2)
                    if col1.button("👑 自分が勝った（1位）", use_container_width=True, type="primary"):
                        current_match["status"] = "終了"
                        for pid in m_players:
                            if pid in data["players"]:
                                data["players"][pid]["status"] = "待機中"
                                if pid == selected_pid:
                                    data["players"][pid]["wins"] += 1
                                else:
                                    data["players"][pid]["losses"] += 1
                        save_data(data)
                        auto_match(current_match["division"], force=False)
                        st.success("対戦終了！4人全員が次のマッチング待機中に戻りました。")
                        st.rerun()
                        
                    if col2.button("🤝 対戦終了（勝敗をつけずに終了）", use_container_width=True):
                        current_match["status"] = "終了"
                        for pid in m_players:
                            if pid in data["players"]:
                                data["players"][pid]["status"] = "待機中"
                        save_data(data)
                        auto_match(current_match["division"], force=False)
                        st.info("対戦終了！4人全員が次のマッチング待機中に戻りました。")
                        st.rerun()

                else:
                    opp_id = other_pids[0] if other_pids else None
                    st.write("### 👇 対戦が終わったら結果を報告してください")
                    col1, col2 = st.columns(2)
                    if col1.button("⭕ 自分の勝ち", use_container_width=True, type="primary"):
                        current_match["status"] = "終了"
                        data["players"][selected_pid]["wins"] += 1
                        if opp_id and opp_id in data["players"]:
                            data["players"][opp_id]["losses"] += 1
                            data["players"][opp_id]["status"] = "待機中"
                        data["players"][selected_pid]["status"] = "待機中"
                        save_data(data)
                        auto_match(current_match["division"], force=False)
                        st.success("勝利報告を受け付けました！次のマッチングまで待機中になります。")
                        st.rerun()
                        
                    if col2.button("❌ 自分の負け", use_container_width=True):
                        current_match["status"] = "終了"
                        if opp_id and opp_id in data["players"]:
                            data["players"][opp_id]["wins"] += 1
                            data["players"][opp_id]["status"] = "待機中"
                        data["players"][selected_pid]["losses"] += 1
                        data["players"][selected_pid]["status"] = "待機中"
                        save_data(data)
                        auto_match(current_match["division"], force=False)
                        st.info("結果報告を受け付けました！次のマッチングまで待機中になります。")
                        st.rerun()

        else:
            if p_info["status"] == "待機中":
                if "デュエパ" in p_info["division"]:
                    st.warning(f"⏳ 現在、デュエパ部門の対戦メンバー（4人）が揃うのを待っています（{refresh_sec}秒ごとに自動更新されます）。")
                else:
                    st.warning(f"⏳ 現在、次の対戦相手を探しています（{refresh_sec}秒ごとに自動更新されます）。")
            else:
                st.info("☕ 現在「休憩中」です。マッチングを再開するには下の「⚔️ 待機中に戻る」を押してください。")
            
            st.subheader("🔄 部門の変更・休憩")
            div_idx = data["divisions"].index(p_info["division"]) if p_info["division"] in data["divisions"] else 0
            new_div = st.selectbox("変更先の部門を選択", data["divisions"], index=div_idx)
            if st.button("部門を変更する"):
                data["players"][selected_pid]["division"] = new_div
                save_data(data)
                auto_match(new_div, force=False)
                st.success(f"部門を「{new_div}」に変更しました！")
                st.rerun()

            if p_info["status"] == "待機中":
                if st.button("☕ 一時休憩する（マッチングを止める）"):
                    data["players"][selected_pid]["status"] = "休憩中"
                    save_data(data)
                    st.rerun()
            elif p_info["status"] == "休憩中":
                if st.button("⚔️ 待機中に戻る（マッチング再開）", type="primary"):
                    data["players"][selected_pid]["status"] = "待機中"
                    save_data(data)
                    auto_match(p_info["division"], force=False)
                    st.rerun()

# ==========================================
# 💻 スタッフ管理画面（バックアップ保存・復元機能つき）
# ==========================================
elif mode == "💻 スタッフ管理画面":
    st.title("💻 イベント運営・スタッフ管理画面")

    if "is_admin" not in st.session_state:
        st.session_state.is_admin = False

    if not st.session_state.is_admin:
        st.warning("🔒 この画面はスタッフ専用です。操作するにはパスワードを入力してください。")
        pwd_input = st.text_input("スタッフ用パスワード", type="password")
        if st.button("ログイン"):
            if pwd_input == config.get("admin_password", "1234"):
                st.session_state.is_admin = True
                st.success("認証に成功しました！")
                st.rerun()
            else:
                st.error("パスワードが違います。")
    else:
        if st.sidebar.button("🔒 スタッフ画面をロック（ログアウト）"):
            st.session_state.is_admin = False
            st.rerun()

        st.info(f"📁 現在操作中のイベント: **{current_event}** （⏱️現在 **{refresh_sec}秒** ごとに自動で待機者のマッチングが実行されます）")

        tab_status, tab_csv, tab_manual, tab_lottery, tab_qr, tab_settings = st.tabs([
            "📊 卓状況・強制マッチング",
            "🎫 参加証・CSV・バックアップ",
            "🤝 手動ペアリング・参加者削除",
            "🎁 抽選（1〜18人）",
            "📱 参加者用QRコード",
            "⚙️ イベント・会場設定"
        ])

        # 1. リアルタイム卓状況 ＆ 強制マッチング ＆ スタッフ代理結果入力
        with tab_status:
            st.subheader("⚡ スタッフ操作：設定人数に関係なく今すぐマッチングを生成")
            if st.button("🚀 全部門の待機者で今すぐ強制マッチングを一括実行する（設定人数を無視）", type="primary", use_container_width=True):
                created_all = auto_match_all_divisions(force=True)
                if created_all:
                    st.success(f"🎉 新しく {len(created_all)} 卓のマッチングを生成しました！")
                else:
                    st.warning("マッチングできる待機人数（通常2人以上・デュエパ4人以上）が揃っている部門がありませんでした。")
                st.rerun()

            active_matches = [m for m in data["matches"] if m["status"] == "対戦中"]
            
            new_matches = [m for m in active_matches if get_match_age_info(m)[0]]
            if new_matches:
                st.subheader("🆕 新しく成立したマッチング（新着・3分以内）")
                for nm in new_matches:
                    _, time_str, ago_str = get_match_age_info(nm)
                    p_list = nm.get("players", [])
                    p_names = [f"**{data['players'].get(pid, {}).get('name', '削除済')}** ({pid})" for pid in p_list]
                    st.success(f"🔔 **【第 {nm['table']} 番卓】 {nm['division']}部門** （{time_str} 開始 / {ago_str}）\n\n👉 対戦メンバー: {' 🆚 '.join(p_names)}")
                if st.button("✅ 新着ハイライト表示をクリア（確認済みにする）"):
                    data["last_created_match_ids"] = []
                    save_data(data)
                    st.rerun()

            st.divider()
            st.subheader("現在の対戦中卓リスト ＆ スタッフ代理結果入力")
            if active_matches:
                match_rows = []
                for m in reversed(active_matches):
                    is_new, time_str, ago_str = get_match_age_info(m)
                    p_list = m.get("players", [])
                    p_names = [f"{pid}: {data['players'].get(pid, {}).get('name', '削除済')}" for pid in p_list]
                    match_rows.append({
                        "状態": f"🆕新着 ({ago_str})" if is_new else f"進行中 ({ago_str})",
                        "開始時刻": time_str,
                        "卓番号": f"{m['table']}番卓",
                        "部門": m["division"],
                        "人数": f"{len(p_list)}人卓",
                        "対戦メンバー": " ／ ".join(p_names)
                    })
                st.table(pd.DataFrame(match_rows))

                with st.expander("🛠️ スタッフが代理で勝敗を入力・卓を強制終了する（スマホ未報告の対応）"):
                    match_options = {
                        m["match_id"]: f"第{m['table']}番卓 ({m['division']}) - " + " vs ".join([data['players'].get(pid, {}).get('name', pid) for pid in m.get("players", [])])
                        for m in active_matches
                    }
                    target_mid = st.selectbox("操作する卓を選んでください", options=list(match_options.keys()), format_func=lambda x: match_options[x])
                    target_m = next((m for m in active_matches if m["match_id"] == target_mid), None)
                    
                    if target_m:
                        m_pids = target_m.get("players", [])
                        winner_options = ["勝敗なし（全員そのまま待機中に戻す）"] + m_pids
                        winner_choice = st.radio(
                            "勝者を選んでください",
                            options=winner_options,
                            format_func=lambda x: x if x.startswith("勝敗なし") else f"⭕ {x}: {data['players'].get(x, {}).get('name', '不明')} の勝ち"
                        )
                        if st.button("✅ この内容で対戦を終了し、メンバーを待機中に戻す"):
                            target_m["status"] = "終了"
                            for pid in m_pids:
                                if pid in data["players"]:
                                    data["players"][pid]["status"] = "待機中"
                                    if not winner_choice.startswith("勝敗なし"):
                                        if pid == winner_choice:
                                            data["players"][pid]["wins"] += 1
                                        else:
                                            data["players"][pid]["losses"] += 1
                            save_data(data)
                            auto_match(target_m["division"], force=False)
                            st.success("対戦を終了し、メンバーを待機中に戻しました！")
                            st.rerun()
            else:
                st.info("現在、対戦中の卓はありません。")

            st.divider()
            st.subheader("部門ごとの待機リスト ＆ 部門別の強制マッチング")
            for div in data["divisions"]:
                label_note = "（4人揃っていれば即ペアリング）" if "デュエパ" in div else "（設定人数を無視して2人以上いれば即ペアリング）"
                if st.button(f"⚡ 「{div}」部門の待機者を今すぐ強制マッチング {label_note}", key=f"match_{div}"):
                    created_ids = auto_match(div, force=True)
                    if created_ids:
                        st.success(f"🎉 「{div}」部門で新しく {len(created_ids)} 卓を作成しました！")
                    else:
                        st.warning(f"「{div}」部門にペアを組める待機人数（通常2人・デュエパ4人）がいません。")
                    st.rerun()
                    
                div_players = [
                    {
                        "ID": pid,
                        "名前": p["name"],
                        "DMPID": p.get("dmp_id", ""),
                        "状態": p["status"],
                        "勝数": p["wins"],
                        "敗数": p["losses"],
                        "アンケート": "✅済" if p.get("survey_done") else "❌未",
                        "参加証": "🎫配布済" if p.get("pass_given") else "未配布"
                    }
                    for pid, p in data["players"].items() if p["division"] == div
                ]
                with st.expander(f"【{div}】 参加人数: {len(div_players)}名", expanded=True):
                    if div_players:
                        st.dataframe(pd.DataFrame(div_players), use_container_width=True)
                    else:
                        st.write("参加者なし")

        # 2. 参加証チェック ＆ CSV出力 ＆ イベント全体のバックアップ保存・復元タブ
        with tab_csv:
            st.subheader("🎫 1. アンケート回答確認 ＆ 参加証の配布チェック")
            st.write("参加者がアンケートを送信すると「アンケート回答」が自動的に **✅回答済** になります。参加証を渡したら右端の「参加証配布済」にチェックを入れて保存してください。")
            
            if data["players"]:
                check_rows = []
                for pid, p in data["players"].items():
                    check_rows.append({
                        "受付ID": pid,
                        "プレイヤー名": p["name"],
                        "DMPID": p.get("dmp_id", ""),
                        "現在部門": p["division"],
                        "アンケート回答": "✅ 回答済" if p.get("survey_done", False) else "❌ 未回答",
                        "参加証配布済": p.get("pass_given", False)
                    })
                df_check = pd.DataFrame(check_rows)
                
                edited_df = st.data_editor(
                    df_check,
                    disabled=["受付ID", "プレイヤー名", "DMPID", "現在部門", "アンケート回答"],
                    hide_index=True,
                    use_container_width=True,
                    key="pass_editor"
                )
                
                if st.button("💾 参加証の配布チェック状態を保存する", type="primary"):
                    for _, row in edited_df.iterrows():
                        pid = row["受付ID"]
                        if pid in data["players"]:
                            data["players"][pid]["pass_given"] = bool(row["参加証配布済"])
                    save_data(data)
                    st.success("参加証の配布状態を保存しました！")
                    st.rerun()

                st.divider()
                st.subheader("📊 2. 参加者リスト（名前・DMPID・参加証状態）のCSVダウンロード")
                player_export_list = [
                    {
                        "受付ID": pid,
                        "プレイヤー名": p["name"],
                        "DMPID": p.get("dmp_id", ""),
                        "現在部門": p["division"],
                        "勝数": p["wins"],
                        "敗数": p["losses"],
                        "アンケート回答": "回答済" if p.get("survey_done") else "未回答",
                        "参加証配布": "配布済" if p.get("pass_given") else "未配布"
                    }
                    for pid, p in data["players"].items()
                ]
                df_export = pd.DataFrame(player_export_list)
                df_export.to_csv(PLAYERS_CSV_FILE, index=False, encoding="utf-8-sig")
                csv_bytes = df_export.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
                
                st.download_button(
                    label="📥 参加者リスト（名前・DMPID）をCSVで保存する",
                    data=csv_bytes,
                    file_name=f"{current_event}_参加者リスト.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            else:
                st.info("まだ参加者が登録されていません。")

            st.divider()
            st.subheader("📝 3. アンケート回答結果のCSVダウンロード")
            if os.path.exists(SURVEY_FILE):
                df_survey = pd.read_csv(SURVEY_FILE, encoding="utf-8-sig")
                survey_bytes = df_survey.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
                
                st.download_button(
                    label="📥 アンケート回答結果をCSVで保存する",
                    data=survey_bytes,
                    file_name=f"{current_event}_アンケート結果.csv",
                    mime="text/csv",
                    use_container_width=True
                )
                st.write(f"現在の回答件数: **{len(df_survey)}件**")
                st.dataframe(df_survey, use_container_width=True)
            else:
                st.info("まだアンケートの回答はありません。")

            st.divider()
            st.subheader("🛡️ 4. イベント全体の丸ごとバックアップ保存・復元（クラウド再起動対策）")
            st.write("参加者リスト・戦績・現在の卓状況・アンケート回答内容まですべて含んだバックアップファイル（`.json`）を端末に保存したり、保存したファイルから一瞬で元通りに復元できます。")
            
            col_bk1, col_bk2 = st.columns(2)
            with col_bk1:
                st.markdown("#### 💾 現在の状態をバックアップ保存")
                # アンケートCSVの中身もバックアップJSONの中に一緒に同梱する
                survey_records = []
                if os.path.exists(SURVEY_FILE):
                    try:
                        survey_records = pd.read_csv(SURVEY_FILE, encoding="utf-8-sig").to_dict(orient="records")
                    except Exception:
                        survey_records = []
                
                full_backup_obj = {
                    "event_name": current_event,
                    "backup_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "event_data": data,
                    "survey_records": survey_records
                }
                backup_json_bytes = json.dumps(full_backup_obj, ensure_ascii=False, indent=2).encode("utf-8")
                
                st.download_button(
                    label="📦 イベント全体のバックアップデータ（JSON）を端末に保存する",
                    data=backup_json_bytes,
                    file_name=f"{current_event}_backup_{datetime.now().strftime('%H%M')}.json",
                    mime="application/json",
                    use_container_width=True,
                    type="primary"
                )

            with col_bk2:
                st.markdown("#### 📂 バックアップから完全復元")
                uploaded_bk = st.file_uploader("保存したバックアップファイル（.json）を選択してください", type=["json"])
                if uploaded_bk is not None:
                    if st.button("🔄 このファイルからイベント状態を完全に復元する", use_container_width=True):
                        try:
                            loaded_obj = json.loads(uploaded_bk.getvalue().decode("utf-8"))
                            # パターンA: フルバックアップ形式（event_data + survey_records）
                            if "event_data" in loaded_obj:
                                restored_data = normalize_event_data(loaded_obj["event_data"])
                                save_data(restored_data)
                                if "survey_records" in loaded_obj and loaded_obj["survey_records"]:
                                    pd.DataFrame(loaded_obj["survey_records"]).to_csv(SURVEY_FILE, index=False, encoding="utf-8-sig")
                            # パターンB: 単体のイベントデータ形式
                            else:
                                restored_data = normalize_event_data(loaded_obj)
                                save_data(restored_data)
                                
                            st.success("🎉 バックアップからの完全復元に成功しました！画面を更新します。")
                            st.rerun()
                        except Exception as e:
                            st.error(f"ファイルの読み込みに失敗しました。正しいバックアップJSONファイルか確認してください。（詳細: {e}）")

        # 3. 手動調整（2人・4人対応） ＆ 参加者削除
        with tab_manual:
            st.subheader("🤝 手動でペアリング（2人卓 または 4人卓の作成）")
            waiting_list = {pid: f"{pid}: {p['name']} ({p['division']})" for pid, p in data["players"].items() if p["status"] == "待機中"}
            
            match_type = st.radio("作成する卓の人数", ["2人対戦（通常）", "4人対戦（デュエパ）"], horizontal=True)
            req_num = 4 if "4人" in match_type else 2
            
            if len(waiting_list) >= req_num:
                selected_manual_pids = st.multiselect(
                    f"対戦させるプレイヤーを {req_num} 人選んでください",
                    options=list(waiting_list.keys()),
                    format_func=lambda x: waiting_list[x],
                    max_selections=req_num
                )
                table_manual = st.number_input("割り当てる卓番号", min_value=1, max_value=data["total_tables"], value=1)
                
                if st.button("選んだメンバーで対戦開始にする"):
                    if len(selected_manual_pids) != req_num:
                        st.error(f"プレイヤーをちょうど {req_num} 人選んでください。")
                    else:
                        for pid in selected_manual_pids:
                            data["players"][pid]["status"] = "対戦中"
                            for other_pid in selected_manual_pids:
                                if other_pid != pid:
                                    data["players"][pid]["opponents"].append(other_pid)
                        new_mid = f"M_MANUAL_{datetime.now().strftime('%H%M%S')}"
                        data["matches"].append({
                            "match_id": new_mid,
                            "division": data["players"][selected_manual_pids[0]]["division"],
                            "table": table_manual,
                            "players": selected_manual_pids,
                            "status": "対戦中",
                            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        })
                        data["last_created_match_ids"] = [new_mid]
                        save_data(data)
                        st.success("手動で卓を作成しました！")
                        st.rerun()
            else:
                st.info(f"待機中のプレイヤーが{req_num}人以上いると手動ペアリングができます。")

            st.divider()
            st.subheader("🗑️ 参加者の削除（登録ミス・途中帰宅の対応）")
            if data["players"]:
                all_players = {pid: f"{pid}: {p['name']} [DMPID:{p.get('dmp_id', '')}] （{p['division']} / {p['status']}）" for pid, p in data["players"].items()}
                del_pid = st.selectbox("削除するプレイヤーを選んでください", list(all_players.keys()), format_func=lambda x: all_players[x])
                
                if st.button("🚨 選択したプレイヤーを削除する"):
                    for m in data["matches"]:
                        if m["status"] == "対戦中" and del_pid in m.get("players", []):
                            m["status"] = "終了"
                            for other_pid in m.get("players", []):
                                if other_pid != del_pid and other_pid in data["players"]:
                                    data["players"][other_pid]["status"] = "待機中"
                    
                    if del_pid in data["lottery_winners"]:
                        data["lottery_winners"].remove(del_pid)
                    
                    del_name = data["players"][del_pid]["name"]
                    del data["players"][del_pid]
                    save_data(data)
                    st.success(f"プレイヤー「{del_pid}: {del_name}」を削除しました。")
                    st.rerun()
            else:
                st.info("現在登録されている参加者はいません。")

        # 4. 抽選機能（1〜18人）
        with tab_lottery:
            st.subheader("🎁 景品のランダム抽選機能（1〜18人）")
            num_winners = st.slider("当選させる人数を選んでください（1〜18人）", min_value=1, max_value=18, value=1)
            exclude_prev = st.checkbox("すでに当選した人は除外する", value=True)
            
            candidates = [
                pid for pid in data["players"].keys()
                if not (exclude_prev and pid in data["lottery_winners"])
            ]
            st.write(f"現在の抽選対象人数: **{len(candidates)}名** （全参加者: {len(data['players'])}名）")

            if st.button("🎲 抽選スタート！"):
                if len(candidates) == 0:
                    st.error("抽選できる対象者がいません。")
                else:
                    actual_draw = min(num_winners, len(candidates))
                    winners = random.sample(candidates, actual_draw)
                    data["lottery_winners"].extend(winners)
                    save_data(data)
                    st.balloons()
                    if actual_draw < num_winners:
                        st.warning(f"対象者が{len(candidates)}名だったため、{actual_draw}名を当選としました！")
                    else:
                        st.success(f"{actual_draw}名の当選者が決定しました！（プレイヤーのスマホ画面にも当選通知が出ます）")

            if data["lottery_winners"]:
                st.write("### 🏆 これまでの当選者リスト")
                for wid in data["lottery_winners"]:
                    if wid in data["players"]:
                        p_win = data["players"][wid]
                        st.write(f"- **{wid}: {p_win['name']}** さん [DMPID: {p_win.get('dmp_id', '')}]（{p_win['division']}）")
                if st.button("当選履歴をリセット"):
                    data["lottery_winners"] = []
                    save_data(data)
                    st.rerun()

        # 5. 参加者用QRコード作成・表示
        with tab_qr:
            st.subheader("📱 参加者スマホ読み取り用 QRコード")
            st.write("クラウド公開したURL（`https://xxxx.streamlit.app`）を一度入力して保存しておくと、いつでも同じQRコードを表示・印刷できます。")
            
            saved_url = config.get("app_url", "")
            default_qr_url = saved_url if saved_url else f"http://{get_local_ip()}:8501"
            
            qr_url = st.text_input("アプリのURLを入力してください", value=default_qr_url)
            if st.button("💾 このURLを初期値として保存する"):
                config["app_url"] = qr_url
                save_config(config)
                st.success("URLを保存しました！")
            
            if qr_url:
                qr = qrcode.QRCode(version=1, box_size=8, border=2)
                qr.add_data(qr_url)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                byte_im = buf.getvalue()
                
                st.image(byte_im, caption=f"読み取りURL: {qr_url}", width=300)
                st.download_button(
                    label="📥 QRコード画像を保存する（印刷用）",
                    data=byte_im,
                    file_name="event_qr.png",
                    mime="image/png"
                )

        # 6. イベント管理・会場設定・自動更新秒数の変更
        with tab_settings:
            st.subheader("📅 イベントの新規作成・切り替え")
            col_ev1, col_ev2 = st.columns(2)
            with col_ev1:
                new_event_name = st.text_input("新規イベント名（例：2026-11-20_第2回交流会）")
                if st.button("✨ 新規イベントを作成して切り替え"):
                    if new_event_name:
                        if new_event_name not in config["events"]:
                            config["events"].append(new_event_name)
                        config["current_event"] = new_event_name
                        save_config(config)
                        st.success(f"新規イベント「{new_event_name}」を作成し、切り替えました！")
                        st.rerun()
                    else:
                        st.error("イベント名を入力してください。")

            with col_ev2:
                selected_ev = st.selectbox(
                    "過去・既存のイベントに切り替える",
                    options=config["events"],
                    index=config["events"].index(current_event)
                )
                if st.button("📂 選択したイベントに切り替える"):
                    config["current_event"] = selected_ev
                    save_config(config)
                    st.success(f"「{selected_ev}」に切り替えました！")
                    st.rerun()

            st.divider()
            st.subheader("⚙️ 部門の追加・会場設定・自動更新の秒数変更")
            new_div_name = st.text_input("新しく追加する部門名（名前に『デュエパ』を入れると4人卓になります）")
            if st.button("部門を追加") and new_div_name:
                if new_div_name not in data["divisions"]:
                    data["divisions"].append(new_div_name)
                    save_data(data)
                    st.success(f"「{new_div_name}」を追加しました！")
                    st.rerun()

            data["total_tables"] = st.number_input("会場の最大卓数", min_value=1, max_value=200, value=data["total_tables"])
            data["min_wait_players"] = st.number_input("通常部門（2人戦）で自動マッチングを開始する待機人数", min_value=2, max_value=20, value=data["min_wait_players"])
            data["refresh_sec"] = st.number_input(
                "⏱️ 自動画面更新＆自動マッチングの間隔（秒） ※10秒〜300秒で設定可能",
                min_value=10,
                max_value=300,
                value=int(data.get("refresh_sec", 30)),
                step=5
            )
            if st.button("💾 会場・秒数設定を保存"):
                save_data(data)
                st.success(f"設定を保存しました！（自動更新間隔: {data['refresh_sec']}秒）")
                st.rerun()

            st.divider()
            st.subheader("🔑 スタッフ画面のパスワード変更")
            new_pwd = st.text_input("新しいパスワードを入力", value=config.get("admin_password", "1234"))
            if st.button("パスワードを変更する"):
                if new_pwd:
                    config["admin_password"] = new_pwd
                    save_config(config)
                    st.success("パスワードを変更しました！")
                else:
                    st.error("空欄にはできません。")

# ==========================================
# 📝 アンケート回答画面（固定された名前を自動で一番上にセット）
# ==========================================
elif mode == "📝 アンケート回答":
    st.title("📝 イベント参加者アンケート")
    st.caption(f"対象イベント: {current_event}")
    st.write("アンケートに回答すると、参加証の受け取りができるようになります！")

    player_names = {pid: f"{pid}: {p['name']} (DMPID: {p.get('dmp_id', '未登録')})" for pid, p in data["players"].items()}

    if not player_names:
        st.warning("まだイベント参加者が登録されていません。先に「📱 プレイヤー画面」から参加登録を行ってください。")
    else:
        pinned_pid = get_pinned_pid()
        pid_list = list(player_names.keys())
        default_idx = pid_list.index(pinned_pid) if pinned_pid in pid_list else 0

        selected_survey_pid = st.selectbox(
            "あなたのお名前（固定中の名前が自動選択されています）",
            options=pid_list,
            index=default_idx,
            format_func=lambda x: player_names[x]
        )
        p_survey_info = data["players"][selected_survey_pid]

        if p_survey_info.get("survey_done"):
            st.success(f"✅ **{p_survey_info['name']} さん、アンケート回答済みです！**\n\nこの画面をスタッフに見せて参加証を受け取ってください。（参加証受取状態: **{'🎫受取済' if p_survey_info.get('pass_given') else '未受取'}**）")

        with st.form("survey_form", clear_on_submit=False):
            q_div = st.multiselect("本日遊んだ部門を教えてください", data["divisions"], default=[p_survey_info["division"]] if p_survey_info["division"] in data["divisions"] else [])
            q_satisfaction = st.radio("イベントの満足度を教えてください", ["5: とても満足", "4: 満足", "3: 普通", "2: やや不満", "1: 不満"])
            q_wait = st.radio("対戦の待ち時間はいかがでしたか？", ["とてもスムーズだった", "ちょうどよかった", "少し待った", "待ち時間が長かった"])
            q_comment = st.text_area("スタッフへのメッセージや、次回やってほしい企画があれば自由に書いてください！")
            q_app_feedback = st.text_area("アプリについて・今後追加してほしい機能など（任意・空欄でもOK）")
            
            submitted = st.form_submit_button("回答を送信する")
            if submitted:
                new_row = pd.DataFrame([{
                    "イベント名": current_event,
                    "回答日時": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "受付ID": selected_survey_pid,
                    "名前": p_survey_info["name"],
                    "DMPID": p_survey_info.get("dmp_id", ""),
                    "参加部門": " / ".join(q_div),
                    "満足度": q_satisfaction,
                    "待ち時間評価": q_wait,
                    "自由記述": q_comment,
                    "アプリへの要望": q_app_feedback
                }])
                if os.path.exists(SURVEY_FILE):
                    new_row.to_csv(SURVEY_FILE, mode="a", header=False, index=False, encoding="utf-8-sig")
                else:
                    new_row.to_csv(SURVEY_FILE, mode="w", header=True, index=False, encoding="utf-8-sig")
                
                data["players"][selected_survey_pid]["survey_done"] = True
                save_data(data)
                st.balloons()
                st.success("ご回答ありがとうございました！スタッフ席で参加証をお受け取りください！")
                st.rerun()