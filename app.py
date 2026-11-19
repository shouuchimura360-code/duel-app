import streamlit as st
import pandas as pd
import random
import os
import json
import socket
import io
import qrcode
from datetime import datetime

# 画面の基本設定
st.set_page_config(page_title="ティーチャーファンイベント", layout="wide")

# ==========================================
# ボタンを大きく・見やすくするカスタムデザイン（CSS）
# ==========================================
st.markdown(
    """
    <style>
    /* 通常のボタンを大きく押しやすくする */
    div.stButton > button {
        min-height: 3.4rem;
        font-size: 1.15rem !important;
        font-weight: bold !important;
        border-radius: 10px !important;
    }
    /* メインボタン（次のマッチングに向かう等）はさらに特大にする */
    div.stButton > button[kind="primary"] {
        min-height: 4.5rem;
        font-size: 1.4rem !important;
        font-weight: 900 !important;
        border-radius: 12px !important;
        box-shadow: 0 4px 10px rgba(0,0,0,0.15);
    }
    /* 卓番号と対戦相手の特大表示カード */
    .match-card {
        background-color: #fff8e1;
        border: 4px solid #ff6f00;
        border-radius: 16px;
        padding: 20px;
        text-align: center;
        margin-bottom: 20px;
    }
    .table-number {
        font-size: 3.2rem;
        font-weight: 900;
        color: #d84315;
        line-height: 1.2;
        margin: 10px 0;
    }
    .opponent-name {
        font-size: 2.0rem;
        font-weight: 800;
        color: #1a237e;
        margin: 12px 0;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# ==========================================
# パソコンで動かしている時だけスリープ防止を作動
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
def get_default_prize_plan():
    return [
        {"prize": "目玉景品（プレイマット・BOX等）", "count": 1},
        {"prize": "デッキケース・スリーブ賞", "count": 3},
        {"prize": "ランダム賞（プロモパック）", "count": 5}
    ]

def get_Initial_event_data():
    return {
        "divisions": ["カジュアル", "ガチ", "デュエパ", "05環境", "08環境"],
        "total_tables": 20,
        "min_wait_players": 2,
        "refresh_sec": 60,
        "players": {},
        "matches": [],
        "lottery_winners": [],
        "prize_plan": get_default_prize_plan(),
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
        d["refresh_sec"] = 60
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
    if "prize_plan" not in d or not isinstance(d["prize_plan"], list):
        d["prize_plan"] = get_default_prize_plan()

    normalized_winners = []
    for item in d["lottery_winners"]:
        if isinstance(item, str):
            normalized_winners.append({"pid": item, "prize": "ランダム賞", "time": ""})
        elif isinstance(item, dict):
            normalized_winners.append(item)
    d["lottery_winners"] = normalized_winners

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
        if "opponents" not in p:
            p["opponents"] = []
        if "last_opponents" not in p:
            p["last_opponents"] = []
        if "match_count" not in p:
            p["match_count"] = p.get("wins", 0) + p.get("losses", 0)
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
refresh_sec = data.get("refresh_sec", 60)

# --- 自分の名前（ID）や現在開いている画面をURLに記憶する機能 ---
def get_pinned_pid():
    pid = st.query_params.get("pid", None)
    if pid and pid in data["players"]:
        return pid
    return None

def set_pinned_pid(pid):
    if pid:
        st.query_params["pid"] = pid
    else:
        if "pid" in st.query_params:
            del st.query_params["pid"]

def get_winner_prizes(pid):
    return [w.get("prize", "景品") for w in data["lottery_winners"] if w.get("pid") == pid]

# --- 経過時間を計算して「新着」かどうか判定する関数 ---
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

# --- 2. マッチング機能（同じ人と連続で当たらない制御つき） ---
def auto_match(division_name, force=False):
    waiting_ids = [
        pid for pid, p in data["players"].items()
        if p["division"] == division_name and p["status"] == "待機中"
    ]
    
    used_tables = [m["table"] for m in data["matches"] if m["status"] == "対戦中"]
    free_tables = [t for t in range(1, data["total_tables"] + 1) if t not in used_tables]

    new_match_ids = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # デュエパ部門（4人マッチング・直前と全く同じメンバーや連続同卓を回避）
    if "デュエパ" in division_name:
        if len(waiting_ids) < 4:
            return []
            
        random.shuffle(waiting_ids)
        past_groups = [set(m.get("players", [])) for m in data["matches"] if m["division"] == division_name]
        
        while len(waiting_ids) >= 4 and free_tables:
            best_group = waiting_ids[:4]
            if len(waiting_ids) > 4:
                best_score = 999
                for _ in range(15):
                    random.shuffle(waiting_ids)
                    candidate = waiting_ids[:4]
                    if set(candidate) in past_groups:
                        continue
                    consec_overlap = sum(
                        1 for pid in candidate
                        for other in candidate
                        if other != pid and other in data["players"][pid].get("last_opponents", [])
                    )
                    if consec_overlap < best_score:
                        best_score = consec_overlap
                        best_group = list(candidate)
                    if best_score == 0:
                        break
                        
            for pid in best_group:
                waiting_ids.remove(pid)
                
            table_num = free_tables.pop(0)
            for pid in best_group:
                data["players"][pid]["status"] = "対戦中"
                others = [o for o in best_group if o != pid]
                data["players"][pid]["opponents"].extend(others)
                data["players"][pid]["last_opponents"] = others
                        
            match_id = f"M4_{datetime.now().strftime('%H%M%S')}_{table_num}"
            data["matches"].append({
                "match_id": match_id,
                "division": division_name,
                "table": table_num,
                "players": best_group,
                "status": "対戦中",
                "created_at": now_str
            })
            new_match_ids.append(match_id)
            
        if new_match_ids:
            data["last_created_match_ids"] = new_match_ids
            save_data(data)
        return new_match_ids

    # 通常部門（2人マッチング・過去未対戦を最優先＆直前の相手とは連続で当たらない）
    else:
        required_wait = 2 if force else data["min_wait_players"]
        if len(waiting_ids) < required_wait:
            return []

        random.shuffle(waiting_ids)
        used_players = set()

        for i, p1_id in enumerate(waiting_ids):
            if p1_id in used_players or not free_tables:
                continue
            p1 = data["players"][p1_id]
            p1_last = p1.get("last_opponents", [])
            
            partner_id = None
            for p2_id in waiting_ids[i+1:]:
                if p2_id in used_players:
                    continue
                if p2_id not in p1["opponents"] and p2_id not in p1_last:
                    partner_id = p2_id
                    break
            
            if not partner_id:
                for p2_id in waiting_ids[i+1:]:
                    if p2_id in used_players:
                        continue
                    if p2_id not in p1_last:
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
                data["players"][p1_id]["last_opponents"] = [partner_id]
                data["players"][partner_id]["last_opponents"] = [p1_id]
                
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

# --- 3. サイドバーメニュー ---
st.sidebar.title("メニュー切り替え")
st.sidebar.caption(f"現在開催中: **{current_event}**")

pinned_pid = get_pinned_pid()
if pinned_pid:
    st.sidebar.info(f"固定中: **{pinned_pid}: {data['players'][pinned_pid]['name']}**")

if SLEEP_PREVENTED:
    st.sidebar.success("PCスリープ防止：作動中")

mode_list = ["プレイヤー画面", "スタッフ管理画面", "アンケート回答"]
mode_codes = {"player": 0, "admin": 1, "survey": 2}
code_by_mode = {"プレイヤー画面": "player", "スタッフ管理画面": "admin", "アンケート回答": "survey"}

current_mode_code = st.query_params.get("mode", "player")
default_mode_idx = mode_codes.get(current_mode_code, 0)

mode = st.sidebar.radio("画面を選んでください", mode_list, index=default_mode_idx)

selected_code = code_by_mode[mode]
if st.query_params.get("mode") != selected_code:
    st.query_params["mode"] = selected_code

st.sidebar.divider()
if st.sidebar.button("画面を最新状態に更新"):
    st.rerun()

# ==========================================
# プレイヤー画面（スマホ・PC共通）
# ==========================================
if mode == "プレイヤー画面":
    st.title("ファンイベントプレイヤー画面")
    st.caption(f"イベント名: {current_event}")

    pinned_pid = get_pinned_pid()

    if not pinned_pid:
        st.subheader("1. 参加登録 または 自分の名前を画面に固定する")
        st.write("一度登録・固定すると、次回からリストで探さなくても常にあなたの専用画面が一番上に表示されます！")
        
        tab_new, tab_select = st.tabs(["新しくイベントに参加登録する", "登録済みの自分の名前を選んで固定する"])
        
        with tab_new:
            new_name = st.text_input("あなたのプレイヤー名（ハンドルネーム）を入力")
            new_dmp_id = st.text_input("DMPIDを入力（番号）")
            init_div = st.selectbox("最初に参加する部門を選択", data["divisions"])
            if st.button("イベントに参加登録して自分の画面を固定する", type="primary"):
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
                        "match_count": 0,
                        "opponents": [],
                        "last_opponents": [],
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
                if st.button("この名前を自分のスマホ画面に固定する", type="primary"):
                    set_pinned_pid(select_pid)
                    st.rerun()

    else:
        selected_pid = pinned_pid
        p_info = data["players"][selected_pid]
        
        col_title, col_unpin = st.columns([3, 1])
        with col_title:
            st.success(f"**あなたの専用画面： {selected_pid} : {p_info['name']} さん**")
        with col_unpin:
            if st.button("別の人に切替"):
                set_pinned_pid(None)
                st.rerun()

        survey_badge = "回答済" if p_info.get("survey_done") else "未回答"
        pass_badge = "受取済" if p_info.get("pass_given") else "未受取"
        
        st.write(f"**DMPID:** {p_info.get('dmp_id', '未登録')} ｜ **現在の部門:** {p_info['division']} ｜ **状態:** {p_info['status']} ｜ **本日の対戦数:** {p_info.get('match_count', 0)}戦")
        st.caption(f"アンケート状態: **{survey_badge}** ｜ 参加証: **{pass_badge}**")

        my_prizes = get_winner_prizes(selected_pid)
        if my_prizes:
            st.balloons()
            st.success(f"**おめでとうございます！抽選に当選しました！**\n\n**当選景品： {' ／ '.join(my_prizes)}**\n\nスタッフ席へお越しください！")

        st.divider()

        if p_info["status"] == "対戦中":
            current_match = next((m for m in data["matches"] if m["status"] == "対戦中" and selected_pid in m.get("players", [])), None)
            if current_match:
                m_players = current_match.get("players", [])
                other_pids = [pid for pid in m_players if pid != selected_pid]
                other_names = [data["players"].get(pid, {}).get("name", "不明") for pid in other_pids]
                is_new, time_str, ago_str = get_match_age_info(current_match)
                new_badge_html = "<div style='color:#d84315; font-weight:bold; font-size:1.2rem;'>【新着マッチング】</div>" if is_new else ""
                
                st.markdown(
                    f"""
                    <div class="match-card">
                        {new_badge_html}
                        <div style="font-size:1.2rem; font-weight:bold; color:#555;">【{current_match['division']}部門】 案内テーブル（開始 {time_str}）</div>
                        <div class="table-number">第 {current_match['table']} 番卓</div>
                        <div style="font-size:1.1rem; color:#333;">対戦相手</div>
                        <div class="opponent-name">{' さん ／ '.join(other_names)} さん</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                
                st.write("### 対戦が終わったら下のボタンを押してください（対戦相手のどちらか1人が押せば全員次に進みます）")
                if st.button("対戦終了！次のマッチングに向かう", use_container_width=True, type="primary"):
                    latest_data = load_data()
                    latest_match = next((m for m in latest_data["matches"] if m["match_id"] == current_match["match_id"]), None)
                    
                    if latest_match and latest_match["status"] == "対戦中":
                        latest_match["status"] = "終了"
                        for pid in m_players:
                            if pid in latest_data["players"]:
                                latest_data["players"][pid]["status"] = "待機中"
                                latest_data["players"][pid]["match_count"] = latest_data["players"][pid].get("match_count", 0) + 1
                        save_data(latest_data)
                        data = latest_data
                        auto_match(current_match["division"], force=False)
                        st.success("お疲れ様でした！対戦を終了し、次のマッチング待機に入りました！")
                        st.rerun()
                    else:
                        st.info("すでに対戦相手が終了ボタンを押したため、次のマッチング待機に入っています！")
                        st.rerun()
            else:
                data["players"][selected_pid]["status"] = "待機中"
                save_data(data)
                st.rerun()

        else:
            if p_info["status"] == "待機中":
                if "デュエパ" in p_info["division"]:
                    st.warning("現在、デュエパ部門の対戦メンバー（4人）が揃うのを待っています。しばらくお待ちいただき、下の更新ボタンを押して卓番を確認してください。")
                else:
                    st.warning("現在、次の対戦相手を探しています（待機中）。しばらくお待ちいただき、下の更新ボタンを押して卓番を確認してください。")
                
                if st.button("最新のマッチング状況を確認する", type="primary", use_container_width=True):
                    st.rerun()
            else:
                st.error("現在「休憩中（マッチング停止中）」です。対戦を再開するには下の「待機中に戻る（マッチング再開）」を押してください。")
            
            st.subheader("部門の変更")
            div_idx = data["divisions"].index(p_info["division"]) if p_info["division"] in data["divisions"] else 0
            new_div = st.selectbox("変更先の部門を選択", data["divisions"], index=div_idx)
            if st.button("部門を変更する", use_container_width=True):
                data["players"][selected_pid]["division"] = new_div
                save_data(data)
                auto_match(new_div, force=False)
                st.success(f"部門を「{new_div}」に変更しました！")
                st.rerun()

            if p_info["status"] == "休憩中":
                st.subheader("マッチングへの復帰")
                if st.button("待機中に戻る（マッチング再開）", type="primary", use_container_width=True):
                    data["players"][selected_pid]["status"] = "待機中"
                    save_data(data)
                    auto_match(p_info["division"], force=False)
                    st.rerun()
            elif p_info["status"] == "待機中":
                st.write("")
                with st.expander("一時休憩（マッチング停止）はこちら ※小さく収納しています"):
                    st.warning("**【注意】** 休憩中に切り替えると、あなたが「待機中に戻る」ボタンを押すまで**次の対戦マッチングから除外**されます。本当に休憩しますか？")
                    confirm_break = st.checkbox("注意を確認しました（休憩中に切り替える）")
                    if confirm_break:
                        if st.button("休憩中に切り替える"):
                            data["players"][selected_pid]["status"] = "休憩中"
                            save_data(data)
                            st.rerun()

# ==========================================
# スタッフ管理画面（複数景品の一括抽選機能つき）
# ==========================================
elif mode == "スタッフ管理画面":
    st.title("イベント運営・スタッフ管理画面")

    if "is_admin" not in st.session_state:
        st.session_state.is_admin = (st.query_params.get("auth") == "1")

    if not st.session_state.is_admin:
        st.warning("この画面はスタッフ専用です。操作するにはパスワードを入力してください。")
        pwd_input = st.text_input("スタッフ用パスワード", type="password")
        if st.button("ログイン", type="primary"):
            if pwd_input == config.get("admin_password", "1234"):
                st.session_state.is_admin = True
                st.query_params["mode"] = "admin"
                st.query_params["auth"] = "1"
                st.success("認証に成功しました！")
                st.rerun()
            else:
                st.error("パスワードが違います。")
    else:
        if st.sidebar.button("スタッフ画面をロック（ログアウト）"):
            st.session_state.is_admin = False
            if "auth" in st.query_params:
                del st.query_params["auth"]
            st.rerun()

        tab_status, tab_csv, tab_manual, tab_lottery, tab_qr, tab_settings = st.tabs([
            "卓状況・強制マッチング",
            "参加証・CSV・バックアップ",
            "手動ペアリング・参加者削除",
            "複数景品の一括抽選",
            "参加者用QRコード",
            "イベント・会場設定"
        ])

        # 1. リアルタイム卓状況
        with tab_status:
            col_info, col_pause = st.columns([2, 1])
            with col_pause:
                pause_auto = st.toggle("自動更新を一時停止する", value=False)
            with col_info:
                if pause_auto:
                    st.warning("現在、自動更新・自動マッチングを一時停止しています（じっくり操作できます）。")
                else:
                    st.info(f"イベント: **{current_event}** （画面をチカチカさせず **{refresh_sec}秒** ごとに卓状況のみ静かに自動更新します）")

            run_interval = None if pause_auto else f"{refresh_sec}s"

            @st.fragment(run_every=run_interval)
            def render_live_match_board():
                global data
                data = load_data()
                if not pause_auto:
                    auto_match_all_divisions(force=False)

                st.subheader("スタッフ操作：設定人数に関係なく今すぐマッチングを生成")
                if st.button("全部門の待機者で今すぐ強制マッチングを一括実行する（設定人数を無視）", type="primary", use_container_width=True):
                    created_all = auto_match_all_divisions(force=True)
                    if created_all:
                        st.success(f"新しく {len(created_all)} 卓のマッチングを生成しました！")
                    else:
                        st.warning("マッチングできる待機人数（通常2人以上・デュエパ4人以上）が揃っている部門がありませんでした。")
                    st.rerun()

                active_matches = [m for m in data["matches"] if m["status"] == "対戦中"]
                
                new_matches = [m for m in active_matches if get_match_age_info(m)[0]]
                if new_matches:
                    st.subheader("【新着】新しく成立したマッチング（3分以内）")
                    for nm in new_matches:
                        _, time_str, ago_str = get_match_age_info(nm)
                        p_list = nm.get("players", [])
                        p_names = [f"**{data['players'].get(pid, {}).get('name', '削除済')}** ({pid})" for pid in p_list]
                        st.success(f"**【第 {nm['table']} 番卓】 {nm['division']}部門** （{time_str} 開始 / {ago_str}）\n\n対戦メンバー: {' vs '.join(p_names)}")
                    if st.button("新着ハイライト表示をクリア（確認済みにする）"):
                        data["last_created_match_ids"] = []
                        save_data(data)
                        st.rerun()

                st.divider()
                st.subheader("現在の対戦中卓リスト ＆ スタッフ代理終了")
                if active_matches:
                    match_rows = []
                    for m in reversed(active_matches):
                        is_new, time_str, ago_str = get_match_age_info(m)
                        p_list = m.get("players", [])
                        p_names = [f"{pid}: {data['players'].get(pid, {}).get('name', '削除済')}" for pid in p_list]
                        match_rows.append({
                            "状態": f"【新着】({ago_str})" if is_new else f"進行中 ({ago_str})",
                            "開始時刻": time_str,
                            "卓番号": f"{m['table']}番卓",
                            "部門": m["division"],
                            "人数": f"{len(p_list)}人卓",
                            "対戦メンバー": " ／ ".join(p_names)
                        })
                    st.table(pd.DataFrame(match_rows))

                    with st.expander("スタッフが代理で卓を終了して待機中に戻す（スマホ押し忘れ対応）"):
                        match_options = {
                            m["match_id"]: f"第{m['table']}番卓 ({m['division']}) - " + " vs ".join([data['players'].get(pid, {}).get('name', pid) for pid in m.get("players", [])])
                            for m in active_matches
                        }
                        target_mid = st.selectbox("終了させる卓を選んでください", options=list(match_options.keys()), format_func=lambda x: match_options[x])
                        target_m = next((m for m in active_matches if m["match_id"] == target_mid), None)
                        
                        if target_m:
                            if st.button("この卓の対戦を終了し、メンバー全員を待機中に戻す"):
                                target_m["status"] = "終了"
                                for pid in target_m.get("players", []):
                                    if pid in data["players"]:
                                        data["players"][pid]["status"] = "待機中"
                                        data["players"][pid]["match_count"] = data["players"][pid].get("match_count", 0) + 1
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
                    if st.button(f"「{div}」部門の待機者を今すぐ強制マッチング {label_note}", key=f"match_{div}"):
                        created_ids = auto_match(div, force=True)
                        if created_ids:
                            st.success(f"「{div}」部門で新しく {len(created_ids)} 卓を作成しました！")
                        else:
                            st.warning(f"「{div}」部門にペアを組める待機人数（通常2人・デュエパ4人）がいません。")
                        st.rerun()
                        
                    div_players = [
                        {
                            "ID": pid,
                            "名前": p["name"],
                            "DMPID": p.get("dmp_id", ""),
                            "状態": p["status"],
                            "対戦数": p.get("match_count", 0),
                            "直前の相手": ", ".join([data["players"].get(op, {}).get("name", op) for op in p.get("last_opponents", [])]),
                            "アンケート": "済" if p.get("survey_done") else "未",
                            "参加証": "配布済" if p.get("pass_given") else "未配布"
                        }
                        for pid, p in data["players"].items() if p["division"] == div
                    ]
                    with st.expander(f"【{div}】 参加人数: {len(div_players)}名", expanded=True):
                        if div_players:
                            st.dataframe(pd.DataFrame(div_players), use_container_width=True)
                        else:
                            st.write("参加者なし")

            render_live_match_board()

        # 2. 参加証チェック ＆ CSV出力 ＆ イベント全体のバックアップ保存・復元タブ
        with tab_csv:
            st.subheader("1. アンケート回答確認 ＆ 参加証の配布チェック")
            st.write("参加者がアンケートを送信すると「アンケート回答」が自動的に **回答済** になります。参加証を渡したら右端の「参加証配布済」にチェックを入れて保存してください。")
            
            if data["players"]:
                check_rows = []
                for pid, p in data["players"].items():
                    check_rows.append({
                        "受付ID": pid,
                        "プレイヤー名": p["name"],
                        "DMPID": p.get("dmp_id", ""),
                        "現在部門": p["division"],
                        "アンケート回答": "回答済" if p.get("survey_done", False) else "未回答",
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
                
                if st.button("参加証の配布チェック状態を保存する", type="primary"):
                    for _, row in edited_df.iterrows():
                        pid = row["受付ID"]
                        if pid in data["players"]:
                            data["players"][pid]["pass_given"] = bool(row["参加証配布済"])
                    save_data(data)
                    st.success("参加証の配布状態を保存しました！")
                    st.rerun()

                st.divider()
                st.subheader("2. 参加者リスト（名前・DMPID・参加証状態）のCSVダウンロード")
                player_export_list = [
                    {
                        "受付ID": pid,
                        "プレイヤー名": p["name"],
                        "DMPID": p.get("dmp_id", ""),
                        "現在部門": p["division"],
                        "対戦数": p.get("match_count", 0),
                        "アンケート回答": "回答済" if p.get("survey_done") else "未回答",
                        "参加証配布": "配布済" if p.get("pass_given") else "未配布",
                        "当選景品": " / ".join(get_winner_prizes(pid))
                    }
                    for pid, p in data["players"].items()
                ]
                df_export = pd.DataFrame(player_export_list)
                df_export.to_csv(PLAYERS_CSV_FILE, index=False, encoding="utf-8-sig")
                csv_bytes = df_export.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
                
                st.download_button(
                    label="参加者リスト（名前・DMPID）をCSVで保存する",
                    data=csv_bytes,
                    file_name=f"{current_event}_参加者リスト.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            else:
                st.info("まだ参加者が登録されていません。")

            st.divider()
            st.subheader("3. アンケート回答結果のCSVダウンロード")
            if os.path.exists(SURVEY_FILE):
                df_survey = pd.read_csv(SURVEY_FILE, encoding="utf-8-sig")
                survey_bytes = df_survey.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
                
                st.download_button(
                    label="アンケート回答結果をCSVで保存する",
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
            st.subheader("4. イベント全体の丸ごとバックアップ保存・復元（クラウド再起動対策）")
            col_bk1, col_bk2 = st.columns(2)
            with col_bk1:
                st.markdown("#### 現在の状態をバックアップ保存")
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
                    label="イベント全体のバックアップデータ（JSON）を端末に保存する",
                    data=backup_json_bytes,
                    file_name=f"{current_event}_backup_{datetime.now().strftime('%H%M')}.json",
                    mime="application/json",
                    use_container_width=True,
                    type="primary"
                )

            with col_bk2:
                st.markdown("#### バックアップから完全復元")
                uploaded_bk = st.file_uploader("保存したバックアップファイル（.json）を選択してください", type=["json"])
                if uploaded_bk is not None:
                    if st.button("このファイルからイベント状態を完全に復元する", use_container_width=True):
                        try:
                            loaded_obj = json.loads(uploaded_bk.getvalue().decode("utf-8"))
                            if "event_data" in loaded_obj:
                                restored_data = normalize_event_data(loaded_obj["event_data"])
                                save_data(restored_data)
                                if "survey_records" in loaded_obj and loaded_obj["survey_records"]:
                                    pd.DataFrame(loaded_obj["survey_records"]).to_csv(SURVEY_FILE, index=False, encoding="utf-8-sig")
                            else:
                                restored_data = normalize_event_data(loaded_obj)
                                save_data(restored_data)
                                
                            st.success("バックアップからの完全復元に成功しました！画面を更新します。")
                            st.rerun()
                        except Exception as e:
                            st.error(f"ファイルの読み込みに失敗しました。（詳細: {e}）")

        # 3. 手動調整（2人・4人対応） ＆ 参加者削除
        with tab_manual:
            st.subheader("手動でペアリング（2人卓 または 4人卓の作成）")
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
                
                if st.button("選んだメンバーで対戦開始にする", type="primary"):
                    if len(selected_manual_pids) != req_num:
                        st.error(f"プレイヤーをちょうど {req_num} 人選んでください。")
                    else:
                        for pid in selected_manual_pids:
                            data["players"][pid]["status"] = "対戦中"
                            others = [o for o in selected_manual_pids if o != pid]
                            data["players"][pid]["opponents"].extend(others)
                            data["players"][pid]["last_opponents"] = others
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
            st.subheader("参加者の削除（登録ミス・途中帰宅の対応）")
            if data["players"]:
                all_players = {pid: f"{pid}: {p['name']} [DMPID:{p.get('dmp_id', '')}] （{p['division']} / {p['status']}）" for pid, p in data["players"].items()}
                del_pid = st.selectbox("削除するプレイヤーを選んでください", list(all_players.keys()), format_func=lambda x: all_players[x])
                
                if st.button("選択したプレイヤーを削除する"):
                    for m in data["matches"]:
                        if m["status"] == "対戦中" and del_pid in m.get("players", []):
                            m["status"] = "終了"
                            for other_pid in m.get("players", []):
                                if other_pid != del_pid and other_pid in data["players"]:
                                    data["players"][other_pid]["status"] = "待機中"
                    
                    data["lottery_winners"] = [w for w in data["lottery_winners"] if w.get("pid") != del_pid]
                    
                    del_name = data["players"][del_pid]["name"]
                    del data["players"][del_pid]
                    save_data(data)
                    st.success(f"プレイヤー「{del_pid}: {del_name}」を削除しました。")
                    st.rerun()
            else:
                st.info("現在登録されている参加者はいません。")

        # 4. 複数景品の一括抽選機能
        with tab_lottery:
            st.subheader("複数景品の一括ランダム抽選（景品ごとの個数指定）")
            st.write("下の表に**「景品名」と「当選個数（人数）」**を入力してください。一番下の行をクリックすると新しい景品を何個でも追加できます（行を選んでDeleteキーで削除も可能です）。")
            
            df_prize_plan = pd.DataFrame(data.get("prize_plan", get_default_prize_plan()))
            if df_prize_plan.empty:
                df_prize_plan = pd.DataFrame([{"prize": "ランダム賞", "count": 1}])

            edited_prizes = st.data_editor(
                df_prize_plan,
                num_rows="dynamic",
                use_container_width=True,
                hide_index=True,
                column_config={
                    "prize": st.column_config.TextColumn("景品名（商品名）", required=True),
                    "count": st.column_config.NumberColumn("当選個数（人数）", min_value=1, max_value=100, default=1, step=1, required=True)
                },
                key="prize_plan_editor"
            )

            valid_prize_list = []
            total_needed = 0
            for _, row in edited_prizes.iterrows():
                p_name = str(row.get("prize", "")).strip()
                p_cnt = row.get("count", 0)
                if p_name and p_name != "None" and pd.notna(p_cnt) and int(p_cnt) > 0:
                    cnt_int = int(p_cnt)
                    valid_prize_list.append({"prize": p_name, "count": cnt_int})
                    total_needed += cnt_int

            col_save_plan, col_exclude = st.columns([1, 1])
            with col_save_plan:
                if st.button("この景品リストを保存しておく"):
                    data["prize_plan"] = valid_prize_list
                    save_data(data)
                    st.success("景品リストを保存しました！")
            with col_exclude:
                exclude_prev = st.checkbox("すでに何かが当選した人は除外する（1人1個まで）", value=True)
            
            already_won_pids = {w.get("pid") for w in data["lottery_winners"]}
            candidates = [
                pid for pid in data["players"].keys()
                if not (exclude_prev and pid in already_won_pids)
            ]
            
            st.info(f"**今回の抽選予定： 合計 {total_needed} 個（{len(valid_prize_list)} 種類）** ｜ 現在の抽選対象プレイヤー： **{len(candidates)} 名** （全参加者: {len(data['players'])}名）")

            if st.button(f"リストの全景品（合計 {total_needed} 個）を一気に抽選スタート！", type="primary", use_container_width=True):
                if not valid_prize_list or total_needed == 0:
                    st.error("景品名と個数（1個以上）を入力してください。")
                elif len(candidates) == 0:
                    st.error("抽選できる対象プレイヤーがいません。")
                else:
                    data["prize_plan"] = valid_prize_list
                    
                    prize_tickets = []
                    for item in valid_prize_list:
                        prize_tickets.extend([item["prize"]] * item["count"])
                    
                    actual_draw = min(len(prize_tickets), len(candidates))
                    winners = random.sample(candidates, actual_draw)
                    now_hm = datetime.now().strftime("%H:%M:%S")
                    
                    for wid, prz in zip(winners, prize_tickets[:actual_draw]):
                        data["lottery_winners"].append({
                            "pid": wid,
                            "prize": prz,
                            "time": now_hm
                        })
                    save_data(data)
                    st.balloons()
                    if actual_draw < len(prize_tickets):
                        st.warning(f"対象プレイヤーが {len(candidates)}名 だったため、上から {actual_draw}個 分の景品を抽選しました！")
                    else:
                        st.success(f"全 {actual_draw} 個の景品の当選者が一気に決定しました！（各プレイヤーのスマホ画面にも当たった景品名が表示されます）")
                    st.rerun()

            if data["lottery_winners"]:
                st.divider()
                st.subheader(f"当選者 ＆ 当たった景品リスト（合計 {len(data['lottery_winners'])} 名）")
                
                prize_summary = {}
                for w in data["lottery_winners"]:
                    prz = w.get("prize", "景品")
                    prize_summary[prz] = prize_summary.get(prz, 0) + 1
                summary_text = " ／ ".join([f"**{k}**: {v}名" for k, v in prize_summary.items()])
                st.caption(f"内訳: {summary_text}")

                winner_rows = []
                for idx, w in enumerate(data["lottery_winners"], 1):
                    wid = w.get("pid")
                    if wid in data["players"]:
                        p_win = data["players"][wid]
                        winner_rows.append({
                            "No.": idx,
                            "景品（当たった物）": w.get("prize", "景品"),
                            "受付ID": wid,
                            "当選プレイヤー名": p_win["name"],
                            "DMPID": p_win.get("dmp_id", ""),
                            "所属部門": p_win["division"],
                            "抽選時刻": w.get("time", "-")
                        })
                if winner_rows:
                    st.table(pd.DataFrame(winner_rows))
                
                if st.button("当選履歴をすべてリセット（やり直す）"):
                    data["lottery_winners"] = []
                    save_data(data)
                    st.rerun()

        # 5. 参加者用QRコード作成・表示
        with tab_qr:
            st.subheader("参加者スマホ読み取り用 QRコード")
            st.write("クラウド公開したURL（`https://xxxx.streamlit.app`）を一度入力して保存しておくと、いつでも同じQRコードを表示・印刷できます。")
            
            saved_url = config.get("app_url", "")
            default_qr_url = saved_url if saved_url else f"http://{get_local_ip()}:8501"
            
            qr_url = st.text_input("アプリのURLを入力してください", value=default_qr_url)
            if st.button("このURLを初期値として保存する"):
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
                    label="QRコード画像を保存する（印刷用）",
                    data=byte_im,
                    file_name="event_qr.png",
                    mime="image/png"
                )

        # 6. イベント管理・会場設定・自動更新秒数の変更
        with tab_settings:
            st.subheader("イベントの新規作成・切り替え")
            col_ev1, col_ev2 = st.columns(2)
            with col_ev1:
                new_event_name = st.text_input("新規イベント名（例：2026-11-20_第2回交流会）")
                if st.button("新規イベントを作成して切り替え"):
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
                if st.button("選択したイベントに切り替える"):
                    config["current_event"] = selected_ev
                    save_config(config)
                    st.success(f"「{selected_ev}」に切り替えました！")
                    st.rerun()

            st.divider()
            st.subheader("部門の追加・会場設定・スタッフ画面の自動マッチング秒数変更")
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
                "卓状況タブの静かな自動更新＆マッチング間隔（秒） ※15秒〜600秒で設定可能",
                min_value=15,
                max_value=600,
                value=int(data.get("refresh_sec", 60)),
                step=15
            )
            if st.button("会場・秒数設定を保存", type="primary"):
                save_data(data)
                st.success(f"設定を保存しました！（自動マッチング間隔: {data['refresh_sec']}秒）")
                st.rerun()

            st.divider()
            st.subheader("スタッフ画面のパスワード変更")
            new_pwd = st.text_input("新しいパスワードを入力", value=config.get("admin_password", "1234"))
            if st.button("パスワードを変更する"):
                if new_pwd:
                    config["admin_password"] = new_pwd
                    save_config(config)
                    st.success("パスワードを変更しました！")
                else:
                    st.error("空欄にはできません。")

# ==========================================
# アンケート回答画面
# ==========================================
elif mode == "プレイヤーアンケート":
    st.title("イベント参加者アンケート")
    st.caption(f"対象イベント: {current_event}")
    st.write("アンケートに回答すると、参加賞の受け取りができるようになります！")

    player_names = {pid: f"{pid}: {p['name']} (DMPID: {p.get('dmp_id', '未登録')})" for pid, p in data["players"].items()}

    if not player_names:
        st.warning("まだイベント参加者が登録されていません。先に「プレイヤー画面」から参加登録を行ってください。")
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
            st.success(f"**{p_survey_info['name']} さん、アンケート回答済みです！**\n\nこの画面をスタッフに見せて参加賞を受け取ってください。（参加証受取状態: **{'受取済' if p_survey_info.get('pass_given') else '未受取'}**）")

        with st.form("survey_form", clear_on_submit=False):
            q_div = st.multiselect("本日遊んだ部門を教えてください", data["divisions"], default=[p_survey_info["division"]] if p_survey_info["division"] in data["divisions"] else [])
            q_satisfaction = st.radio("イベントの満足度を教えてください", ["5: とても満足", "4: 満足", "3: 普通", "2: やや不満", "1: 不満"])
            q_wait = st.radio("対戦の待ち時間はいかがでしたか？", ["とてもスムーズだった", "ちょうどよかった", "少し待った", "待ち時間が長かった"])
            q_comment = st.text_area("参加してみて、ここが良かったなーとか勉強になったなーってポイントを教えてください")
            q_app_feedback = st.text_area("アプリについて・今後追加してほしい機能など（任意・空欄でもOK）")
            
            submitted = st.form_submit_button("回答を送信する", type="primary", use_container_width=True)
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
                    "良かった・勉強になったポイント": q_comment,
                    "アプリへの要望": q_app_feedback
                }])
                if os.path.exists(SURVEY_FILE):
                    new_row.to_csv(SURVEY_FILE, mode="a", header=False, index=False, encoding="utf-8-sig")
                else:
                    new_row.to_csv(SURVEY_FILE, mode="w", header=True, index=False, encoding="utf-8-sig")
                
                data["players"][selected_survey_pid]["survey_done"] = True
                save_data(data)
                st.balloons()
                st.success("ご回答ありがとうございました！スタッフ席で参加賞をお受け取りください！")
                st.rerun()