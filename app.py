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
st.set_page_config(page_title="デュエマ イベント運営アプリ", layout="wide")

# ==========================================
# 🛡️ パソコンで動かしている時だけスリープ防止を作動（クラウド上では自動でスキップ）
# ==========================================
def prevent_sleep():
    if os.name == "nt":  # Windowsパソコンで直接動かしている場合のみ実行
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
        "players": {},
        "matches": [],
        "lottery_winners": []
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

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
            for m in d.get("matches", []):
                if "players" not in m:
                    m["players"] = [m.get("p1"), m.get("p2")]
            for pid, p in d.get("players", {}).items():
                if "dmp_id" not in p:
                    p["dmp_id"] = ""
            return d
    else:
        init_data = get_Initial_event_data()
        save_data(init_data)
        return init_data

def save_data(d):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

data = load_data()

# --- 2. 自動マッチング機能（通常2人 ＆ デュエパ4人対応） ---
def auto_match(division_name):
    waiting_ids = [
        pid for pid, p in data["players"].items()
        if p["division"] == division_name and p["status"] == "待機中"
    ]
    
    used_tables = [m["table"] for m in data["matches"] if m["status"] == "対戦中"]
    free_tables = [t for t in range(1, data["total_tables"] + 1) if t not in used_tables]

    # ★ デュエパ部門（4人マッチング・一部重複OK）
    if "デュエパ" in division_name:
        if len(waiting_ids) < 4:
            return 0
            
        random.shuffle(waiting_ids)
        past_groups = [set(m.get("players", [])) for m in data["matches"] if m["division"] == division_name]
        
        matched_count = 0
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
                "status": "対戦中"
            })
            matched_count += 1
            
        if matched_count > 0:
            save_data(data)
        return matched_count

    # ★ 通常部門（2人マッチング・過去対戦者を回避）
    else:
        if len(waiting_ids) < data["min_wait_players"]:
            return 0

        random.shuffle(waiting_ids)
        waiting_ids.sort(key=lambda pid: data["players"][pid]["wins"], reverse=True)

        matched_count = 0
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
                    "status": "対戦中"
                })
                matched_count += 1

        if matched_count > 0:
            save_data(data)
        return matched_count

# --- 3. サイドバーメニュー ---
st.sidebar.title("メニュー切り替え")
st.sidebar.caption(f"現在開催中: **{current_event}**")
if SLEEP_PREVENTED:
    st.sidebar.success("🛡️ PCスリープ防止：作動中")

mode = st.sidebar.radio("画面を選んでください", ["📱 プレイヤー画面", "💻 スタッフ管理画面", "📝 アンケート回答"])

if st.sidebar.button("🔄 画面を最新状態に更新"):
    st.rerun()

# ==========================================
# 📱 プレイヤー画面（スマホ・PC共通）
# ==========================================
if mode == "📱 プレイヤー画面":
    st.title("🐉 デュエマ イベント プレイヤー画面")
    st.caption(f"イベント名: {current_event}")

    st.subheader("1. プレイヤー選択・新規参加")
    player_names = {pid: p["name"] for pid, p in data["players"].items()}
    
    tab1, tab2 = st.tabs(["すでに参加登録済みの方", "新しく参加登録する方"])
    
    with tab2:
        new_name = st.text_input("あなたのプレイヤー名（ハンドルネーム）を入力")
        new_dmp_id = st.text_input("DMPIDを入力（番号）")
        init_div = st.selectbox("最初に参加する部門を選択", data["divisions"])
        if st.button("イベントに参加登録する"):
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
                    "opponents": []
                }
                save_data(data)
                auto_match(init_div)
                st.success(f"登録完了！あなたのIDは「{new_id} ({new_name})」です。「すでに参加登録済みの方」タブから選んでください。")
                st.rerun()
            else:
                st.error("プレイヤー名を入力してください。")

    with tab1:
        if not player_names:
            st.info("まだ参加者がいません。右のタブから参加登録してください。")
        else:
            selected_pid = st.selectbox(
                "自分の名前を選んでください",
                options=list(player_names.keys()),
                format_func=lambda x: f"{x}: {player_names[x]}"
            )
            
            p_info = data["players"][selected_pid]
            st.write(f"**DMPID:** {p_info.get('dmp_id', '未登録')} ｜ **現在の部門:** {p_info['division']} ｜ **状態:** {p_info['status']} ｜ **戦績:** {p_info['wins']}勝 {p_info['losses']}敗")

            if selected_pid in data["lottery_winners"]:
                st.balloons()
                st.success("🎉 おめでとうございます！ランダム賞（抽選）に当選しました！スタッフ席へお越しください！")

            if p_info["status"] == "対戦中":
                current_match = next((m for m in data["matches"] if m["status"] == "対戦中" and selected_pid in m.get("players", [])), None)
                if current_match:
                    m_players = current_match.get("players", [])
                    other_pids = [pid for pid in m_players if pid != selected_pid]
                    other_names = [data["players"].get(pid, {}).get("name", "不明") for pid in other_pids]
                    
                    st.info(f"🔥 **【対戦案内】 第 {current_match['table']} 番卓** へ移動してください！\n\n**対戦相手:** {' さん / '.join(other_names)} さん（{current_match['division']}部門）")
                    
                    if len(m_players) > 2:
                        st.write("--- 対戦が終わったら代表者1名が結果ボタンを押してください（全員が待機中に戻ります） ---")
                        col1, col2 = st.columns(2)
                        if col1.button("👑 自分が勝った（1位）", use_container_width=True):
                            current_match["status"] = "終了"
                            for pid in m_players:
                                if pid in data["players"]:
                                    data["players"][pid]["status"] = "待機中"
                                    if pid == selected_pid:
                                        data["players"][pid]["wins"] += 1
                                    else:
                                        data["players"][pid]["losses"] += 1
                            save_data(data)
                            auto_match(current_match["division"])
                            st.success("対戦終了！4人全員が次のマッチング待機中に戻りました。")
                            st.rerun()
                            
                        if col2.button("🤝 対戦終了（勝敗をつけずに終了）", use_container_width=True):
                            current_match["status"] = "終了"
                            for pid in m_players:
                                if pid in data["players"]:
                                    data["players"][pid]["status"] = "待機中"
                            save_data(data)
                            auto_match(current_match["division"])
                            st.info("対戦終了！4人全員が次のマッチング待機中に戻りました。")
                            st.rerun()

                    else:
                        opp_id = other_pids[0] if other_pids else None
                        st.write("--- 対戦が終わったら結果を報告してください ---")
                        col1, col2 = st.columns(2)
                        if col1.button("⭕ 自分の勝ち", use_container_width=True):
                            current_match["status"] = "終了"
                            data["players"][selected_pid]["wins"] += 1
                            if opp_id and opp_id in data["players"]:
                                data["players"][opp_id]["losses"] += 1
                                data["players"][opp_id]["status"] = "待機中"
                            data["players"][selected_pid]["status"] = "待機中"
                            save_data(data)
                            auto_match(current_match["division"])
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
                            auto_match(current_match["division"])
                            st.info("結果報告を受け付けました！次のマッチングまで待機中になります。")
                            st.rerun()

            else:
                if "デュエパ" in p_info["division"]:
                    st.warning("⏳ 現在、デュエパ部門の対戦メンバー（4人）が揃うのを待っています。しばらくお待ちいただき、上の「🔄 画面を最新状態に更新」を押してください。")
                else:
                    st.warning("⏳ 現在、次の対戦相手を探しています（待機中）。しばらくお待ちいただき、上の「🔄 画面を最新状態に更新」を押してください。")
                
                st.subheader("🔄 部門の変更・休憩")
                div_idx = data["divisions"].index(p_info["division"]) if p_info["division"] in data["divisions"] else 0
                new_div = st.selectbox("変更先の部門を選択", data["divisions"], index=div_idx)
                if st.button("部門を変更する"):
                    data["players"][selected_pid]["division"] = new_div
                    save_data(data)
                    auto_match(new_div)
                    st.success(f"部門を「{new_div}」に変更しました！")
                    st.rerun()

                if p_info["status"] == "待機中":
                    if st.button("☕ 一時休憩する（マッチングを止める）"):
                        data["players"][selected_pid]["status"] = "休憩中"
                        save_data(data)
                        st.rerun()
                elif p_info["status"] == "休憩中":
                    if st.button("⚔️ 待機中に戻る（マッチング再開）"):
                        data["players"][selected_pid]["status"] = "待機中"
                        save_data(data)
                        auto_match(p_info["division"])
                        st.rerun()

# ==========================================
# 💻 スタッフ管理画面（パスワード保護付き）
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

        st.info(f"📁 現在操作中のイベント: **{current_event}**")

        tab_status, tab_csv, tab_manual, tab_lottery, tab_qr, tab_settings = st.tabs([
            "📊 卓状況・待機リスト",
            "📥 CSV出力（参加者・アンケート）",
            "🤝 手動ペアリング・参加者削除",
            "🎁 抽選（1〜18人）",
            "📱 参加者用QRコード",
            "⚙️ イベント・会場設定"
        ])

        # 1. リアルタイム卓状況
        with tab_status:
            st.subheader("現在の対戦中卓リスト")
            active_matches = [m for m in data["matches"] if m["status"] == "対戦中"]
            if active_matches:
                match_rows = []
                for m in active_matches:
                    p_list = m.get("players", [])
                    p_names = [f"{pid}: {data['players'].get(pid, {}).get('name', '削除済')}" for pid in p_list]
                    match_rows.append({
                        "卓番号": f"{m['table']}番卓",
                        "部門": m["division"],
                        "人数": f"{len(p_list)}人卓",
                        "対戦メンバー": " ／ ".join(p_names)
                    })
                st.table(pd.DataFrame(match_rows))
            else:
                st.info("現在、対戦中の卓はありません。")

            st.subheader("部門ごとの待機・参加者リスト")
            for div in data["divisions"]:
                label_note = "（4人1卓で自動ペアリング）" if "デュエパ" in div else "（2人1卓で自動ペアリング）"
                if st.button(f"⚡ 「{div}」部門の待機者を今すぐマッチング実行 {label_note}", key=f"match_{div}"):
                    cnt = auto_match(div)
                    st.success(f"{cnt}卓を作成しました！")
                    st.rerun()
                    
                div_players = [
                    {
                        "ID": pid,
                        "名前": p["name"],
                        "DMPID": p.get("dmp_id", ""),
                        "状態": p["status"],
                        "勝数": p["wins"],
                        "敗数": p["losses"],
                        "延べ対戦人数": len(p["opponents"])
                    }
                    for pid, p in data["players"].items() if p["division"] == div
                ]
                with st.expander(f"【{div}】 参加人数: {len(div_players)}名", expanded=True):
                    if div_players:
                        st.dataframe(pd.DataFrame(div_players), use_container_width=True)
                    else:
                        st.write("参加者なし")

        # 2. CSV出力専用タブ（参加者リスト ＆ アンケート結果の両方に対応）
        with tab_csv:
            st.subheader("📊 1. 参加者リスト（名前・DMPID）のCSVダウンロード")
            if data["players"]:
                player_export_list = [
                    {
                        "受付ID": pid,
                        "プレイヤー名": p["name"],
                        "DMPID": p.get("dmp_id", ""),
                        "現在部門": p["division"],
                        "勝数": p["wins"],
                        "敗数": p["losses"]
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
                st.dataframe(df_export, use_container_width=True)
            else:
                st.info("まだ参加者が登録されていません。")

            st.divider()
            st.subheader("📝 2. アンケート回答結果のCSVダウンロード")
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
                        data["matches"].append({
                            "match_id": f"M_MANUAL_{datetime.now().strftime('%H%M%S')}",
                            "division": data["players"][selected_manual_pids[0]]["division"],
                            "table": table_manual,
                            "players": selected_manual_pids,
                            "status": "対戦中"
                        })
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

        # 5. 参加者用QRコード作成・表示（クラウド固定URLの保存機能つき）
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

        # 6. イベント管理・会場設定・パスワード変更
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
            st.subheader("⚙️ 部門の追加・会場設定")
            new_div_name = st.text_input("新しく追加する部門名（名前に『デュエパ』を入れると4人卓になります）")
            if st.button("部門を追加") and new_div_name:
                if new_div_name not in data["divisions"]:
                    data["divisions"].append(new_div_name)
                    save_data(data)
                    st.success(f"「{new_div_name}」を追加しました！")
                    st.rerun()

            data["total_tables"] = st.number_input("会場の最大卓数", min_value=1, max_value=200, value=data["total_tables"])
            data["min_wait_players"] = st.number_input("通常部門（2人戦）で自動マッチングを開始する待機人数", min_value=2, max_value=20, value=data["min_wait_players"])
            if st.button("会場設定を保存"):
                save_data(data)
                st.success("設定を保存しました！")

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
# 📝 アンケート回答画面（イベントごとにCSV自動保存）
# ==========================================
elif mode == "📝 アンケート回答":
    st.title("📝 イベント参加者アンケート")
    st.caption(f"対象イベント: {current_event}")
    st.write("本日のイベントにご参加いただきありがとうございます！ご意見をお聞かせください。")

    with st.form("survey_form", clear_on_submit=True):
        q_name = st.text_input("お名前")
        q_div = st.multiselect("本日遊んだ部門を教えてください", data["divisions"])
        q_satisfaction = st.radio("イベントの満足度を教えてください", ["5: とても満足", "4: 満足", "3: 普通", "2: やや不満", "1: 不満"])
        q_wait = st.radio("対戦の待ち時間はいかがでしたか？", ["とてもスムーズだった", "ちょうどよかった", "少し待った", "待ち時間が長かった"])
        q_comment = st.text_area("スタッフへのメッセージや、次回やってほしい企画があれば自由に書いてください！")
        q_app_feedback = st.text_area("アプリについて・今後追加してほしい機能など（任意・空欄でもOK）")
        
        submitted = st.form_submit_button("回答を送信する")
        if submitted:
            new_row = pd.DataFrame([{
                "イベント名": current_event,
                "回答日時": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "名前": q_name,
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
            
            st.success("ご回答ありがとうございました！回答データが保存されました。")