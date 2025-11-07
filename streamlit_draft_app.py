import json
from io import StringIO
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st

# ---------- Helpers ----------
OFF_POS = {"QB","RB","WR","TE"}

STANDARD_COLS = [
    "player_name","team","pos",
    "pass_yds","pass_td","pass_int",
    "rush_yds","rush_td",
    "rec","rec_yds","rec_td",
]

NUMERIC_COLS = [
    "pass_yds","pass_td","pass_int",
    "rush_yds","rush_td",
    "rec","rec_yds","rec_td",
]

AUTO_MAP = {
    "player_name": ["player","name","player name","full_name","fullname","player_name"],
    "team": ["team","nfl team","pro_team","pro team","proteam","tm"],
    "pos": ["pos","position","player position"],
    "pass_yds": ["pass_yds","pass yds","pass yards","passyds","passyards","py","passingyards","yds (pass)","yds"],
    "pass_td": ["pass_td","pass tds","pass touchdowns","pass td","ptd","passingtd","tds (pass)","tds"],
    "pass_int": ["int","ints","interceptions","pass_int","pass int","interception","ints (pass)"],
    "rush_yds": ["rush_yds","rush yds","rush yards","rushyards","ry","rushingyards","yds (rush)","yds.1"],
    "rush_td": ["rush_td","rush tds","rush touchdowns","rtd","rushingtd","tds (rush)","tds.1"],
    "rec": ["rec","receptions","catches","recs"],
    "rec_yds": ["rec_yds","rec yds","rec yards","receivingyards","ryds","receiving yds"],
    "rec_td": ["rec_td","rec tds","receiving touchdowns","rctd","receivingtd"],
}

def guess_mapping(cols):
    mapping = {}
    lower_cols = {c.lower(): c for c in cols}
    used = set()
    for std, variants in AUTO_MAP.items():
        for v in variants:
            if v in lower_cols and lower_cols[v] not in used:
                mapping[lower_cols[v]] = std
                used.add(lower_cols[v])
                break
    return mapping

def coerce_numeric(df: pd.DataFrame, cols):
    df = df.copy()
    for c in cols:
        if c not in df.columns:
            df[c] = 0
        df[c] = (
            df[c].astype(str)
                 .str.replace(",", "", regex=False)
                 .str.strip()
                 .replace({"": "0", "—": "0", "-": "0", "NA": "0", "N/A": "0"})
        )
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    return df

def normalize_pos(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.upper()

def infer_pos(df: pd.DataFrame) -> pd.Series:
    # start with whatever 'pos' exists
    pos = df.get("pos", pd.Series([""]*len(df)))
    pos = pos.fillna("").astype(str).str.strip()
    inferred = normalize_pos(pos)

    # columns we need to test
    cols = ["pass_yds","pass_td","pass_int","rec","rec_yds","rec_td","rush_yds","rush_td"]
    for c in cols:
        if c not in df.columns:
            df[c] = 0

    # coerce numeric locally (no commas, blanks, etc.)
    df_num = df.copy()
    for c in cols:
        df_num[c] = (
            df_num[c]
            .astype(str)
            .str.replace(",", "", regex=False)
            .str.strip()
            .replace({"": "0", "—": "0", "-": "0", "N/A": "0", "NA": "0"})
        )
        df_num[c] = pd.to_numeric(df_num[c], errors="coerce").fillna(0)

    # we only infer for empties / non-offensive
    idx = (inferred.eq("")) | (~inferred.isin(OFF_POS))

    qb_mask = (df_num.loc[idx, "pass_yds"] > 0) | (df_num.loc[idx, "pass_td"] > 0) | (df_num.loc[idx, "pass_int"] > 0)
    wr_mask = (df_num.loc[idx, "rec"] > 0) | (df_num.loc[idx, "rec_yds"] > 0) | (df_num.loc[idx, "rec_td"] > 0)
    rb_mask = (df_num.loc[idx, "rush_yds"] > 0) | (df_num.loc[idx, "rush_td"] > 0)

    inferred = inferred.copy()
    inferred.loc[idx & qb_mask] = "QB"
    inferred.loc[idx & ~qb_mask & wr_mask] = "WR"
    inferred.loc[idx & ~qb_mask & ~wr_mask & rb_mask] = "RB"

    return inferred


def fantasy_points(df: pd.DataFrame, scoring: dict) -> pd.DataFrame:
    df = df.copy()
    df = coerce_numeric(df, NUMERIC_COLS)
    fp = (
        df["pass_yds"]  * float(scoring.get("pass_yards", 0.0)) +
        df["pass_td"]   * float(scoring.get("pass_td", 0.0)) +
        df["pass_int"]  * float(scoring.get("pass_int", 0.0)) +
        df["rush_yds"]  * float(scoring.get("rush_yards", 0.0)) +
        df["rush_td"]   * float(scoring.get("rush_td", 0.0)) +
        df["rec"]       * float(scoring.get("rec", 0.0)) +
        df["rec_yds"]   * float(scoring.get("rec_yards", 0.0)) +
        df["rec_td"]    * float(scoring.get("rec_td", 0.0))
    )
    bonus = 0
    if float(scoring.get("bonus_100_rush_rec_yds", 0)) != 0:
        bonus = (
            (df["rush_yds"] >= 100).astype(int)
            + (df["rec_yds"] >= 100).astype(int)
        ) * float(scoring["bonus_100_rush_rec_yds"])
    if float(scoring.get("bonus_300_pass_yds", 0)) != 0:
        bonus = bonus + (df["pass_yds"] >= 300).astype(int) * float(scoring["bonus_300_pass_yds"])
    df["fantasy_points"] = (fp + bonus).astype(float).round(2)
    return df

def compute_replacement_indices(teams, start_qb, start_rb, start_wr, start_te,
                                qb_rep=None, rb_rep=None, wr_rep=None, te_rep=None):
    default = {
        "QB": int(round(teams * start_qb)),
        "RB": int(round(teams * start_rb)),
        "WR": int(round(teams * start_wr)),
        "TE": int(round(teams * start_te)),
    }
    return {
        "QB": qb_rep if qb_rep is not None else default["QB"],
        "RB": rb_rep if rb_rep is not None else default["RB"],
        "WR": wr_rep if wr_rep is not None else default["WR"],
        "TE": te_rep if te_rep is not None else default["TE"],
    }

def pos_replacement_fp(pos_df: pd.DataFrame, rep_index_1based: int) -> float:
    if pos_df.empty:
        return 0.0
    idx0 = max(0, min(len(pos_df)-1, rep_index_1based-1))
    return float(pos_df.iloc[idx0]["fantasy_points"])

def add_vorp(df_fp: pd.DataFrame, rep_indices: dict) -> pd.DataFrame:
    df = df_fp.copy()
    df["pos"] = normalize_pos(df["pos"])
    df = df[df["pos"].isin(OFF_POS)].copy()
    df = df.sort_values(["pos","fantasy_points"], ascending=[True, False])
    repl = {}
    for p in ["QB","RB","WR","TE"]:
        sub = df[df["pos"]==p]
        repl[p] = pos_replacement_fp(sub, rep_indices[p])
    df["replacement_fp"] = df["pos"].map(repl)
    df["VORP"] = (df["fantasy_points"] - df["replacement_fp"]).round(2)
    return df

def make_tiers(df_vorp: pd.DataFrame, gap: float) -> pd.DataFrame:
    df = df_vorp.copy()
    df["pos"] = normalize_pos(df["pos"])
    df = df[df["pos"].isin(OFF_POS)].copy()
    out = []
    for p in ["QB","RB","WR","TE"]:
        sub = df[df["pos"]==p].sort_values("VORP", ascending=False)
        if sub.empty:
            continue
        tiers, tier, prev = [], 1, None
        for _, row in sub.iterrows():
            v = float(row["VORP"])
            if prev is not None and (prev - v) > gap:
                tier += 1
            tiers.append(tier); prev = v
        sub = sub.copy(); sub["Tier"] = tiers
        out.append(sub)
    if not out:
        return df
    tiers = pd.concat(out, ignore_index=True)
    return tiers.sort_values(["pos","Tier","VORP"], ascending=[True, True, False]).reset_index(drop=True)

def tier_bonus(t):
    return 15 if t==1 else 10 if t==2 else 6 if t==3 else 3 if t==4 else 0

def suggest(df_tiers: pd.DataFrame, have, starters, top_n=10) -> pd.DataFrame:
    df = df_tiers.copy()
    df["Tier"] = pd.to_numeric(df["Tier"], errors="coerce").fillna(999).astype(int)
    df["VORP"] = pd.to_numeric(df["VORP"], errors="coerce").fillna(0.0)

    def need_penalty(pos):
        return -8.0 if have.get(pos,0) >= starters.get(pos,0) else 0.0

    df["TierBonus"] = df["Tier"].map(tier_bonus)
    df["NeedPenalty"] = df["pos"].map(need_penalty)
    df["SuggestScore"] = (df["VORP"] + df["TierBonus"] + df["NeedPenalty"]).round(2)
    return df.sort_values(["SuggestScore","VORP"], ascending=[False, False]).head(top_n)

def download_link(df: pd.DataFrame, filename: str, label: str):
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(label, csv, filename, mime="text/csv")

# ---------- UI ----------
st.set_page_config(page_title="🏈 Fantasy Draft Assistant (Demo)", layout="wide")
st.title("🏈 Fantasy Draft Assistant — Demo App")

# Session state
if "players" not in st.session_state: st.session_state.players = None
if "fp" not in st.session_state: st.session_state.fp = None
if "vorp" not in st.session_state: st.session_state.vorp = None
if "tiers" not in st.session_state: st.session_state.tiers = None
if "board" not in st.session_state: st.session_state.board = None
if "picks_log" not in st.session_state: st.session_state.picks_log = pd.DataFrame()

with st.sidebar:
    st.header("1) Load Projections")
    raw_csv = st.file_uploader("Projections CSV", type=["csv"])
    mapping_json = st.file_uploader("Optional mapping JSON", type=["json"])
    add_pos_qb = st.checkbox("If missing position, treat as QB data", value=False)
    st.caption("Tip: If your file is QB-only with headers like YDS/TDS/INTS, check this.")

    st.header("2) Scoring (PPR default)")
    scoring_default = {
      "pass_yards": 0.04, "pass_td": 4, "pass_int": -2,
      "rush_yards": 0.1, "rush_td": 6,
      "rec": 1, "rec_yards": 0.1, "rec_td": 6,
      "bonus_100_rush_rec_yds": 0, "bonus_300_pass_yds": 0
    }
    scoring_text = st.text_area("scoring.json", json.dumps(scoring_default, indent=2), height=210)

    st.header("3) League & Tiers")
    teams = st.number_input("Teams", 8, 20, 12)
    start_qb = st.number_input("Start QB", 0.0, 3.0, 1.0, step=0.5)
    start_rb = st.number_input("Start RB", 0.0, 5.0, 2.0, step=0.5)
    start_wr = st.number_input("Start WR", 0.0, 5.0, 2.0, step=0.5)
    start_te = st.number_input("Start TE", 0.0, 3.0, 1.0, step=0.5)
    qb_rep = st.number_input("Override QB replacement (optional)", 0, 60, 0)
    rb_rep = st.number_input("Override RB replacement (optional)", 0, 120, 0)
    wr_rep = st.number_input("Override WR replacement (optional)", 0, 120, 0)
    te_rep = st.number_input("Override TE replacement (optional)", 0, 60, 0)
    tier_gap = st.number_input("Tier gap (VORP drop to start new tier)", 2.0, 25.0, 10.0, step=1.0)

    st.header("4) Your Roster (for suggestions)")
    have_qb = st.number_input("Have QB", 0, 5, 0)
    have_rb = st.number_input("Have RB", 0, 10, 0)
    have_wr = st.number_input("Have WR", 0, 10, 0)
    have_te = st.number_input("Have TE", 0, 5, 0)

    st.header("Actions")
    run_pipeline = st.button("Run Pipeline (Import → FP → VORP → Tiers)")
    init_board = st.button("Initialize Draft Board from Tiers")
    suggest_btn = st.button("Suggest Picks from Current Board")

# ---------- Pipeline ----------
if run_pipeline:
    if raw_csv is None:
        st.error("Please upload a projections CSV.")
    else:
        df_raw = pd.read_csv(raw_csv, sep=None, engine="python")
        # Mapping (auto + optional manual)
        mapping = guess_mapping(df_raw.columns)
        if mapping_json is not None:
            user_map = json.loads(mapping_json.read().decode("utf-8"))
            mapping.update(user_map)  # user wins
        df = df_raw.rename(columns=mapping)
        # Ensure all standard columns exist
        for c in STANDARD_COLS:
            if c not in df.columns:
                df[c] = 0

        # coerce numerics BEFORE infer_pos
        df = coerce_numeric(df, NUMERIC_COLS)

        # Position handling
        if add_pos_qb:
            df["pos"] = "QB"
        df["pos"] = infer_pos(df)


        # Filter to offensive positions (if that empties, skip filtering)
        filtered = df[df["pos"].isin(OFF_POS)].copy()
        if filtered.empty:
            st.warning("No offensive positions detected; skipping position filter.")
            filtered = df.copy()

        # Compute FP
        try:
            scoring = json.loads(scoring_text)
        except Exception as e:
            st.error(f"scoring.json is invalid JSON: {e}")
            st.stop()

        fp = fantasy_points(filtered, scoring)
        fp = fp.sort_values("fantasy_points", ascending=False).reset_index(drop=True)

        # VORP
        overrides = {
            "qb": int(qb_rep) if qb_rep > 0 else None,
            "rb": int(rb_rep) if rb_rep > 0 else None,
            "wr": int(wr_rep) if wr_rep > 0 else None,
            "te": int(te_rep) if te_rep > 0 else None,
        }
        rep_indices = compute_replacement_indices(
            int(teams), float(start_qb), float(start_rb), float(start_wr), float(start_te),
            qb_rep=overrides["qb"], rb_rep=overrides["rb"], wr_rep=overrides["wr"], te_rep=overrides["te"]
        )
        vorp = add_vorp(fp, rep_indices)

        # Tiers
        tiers = make_tiers(vorp, float(tier_gap))

        st.session_state.players = filtered
        st.session_state.fp = fp
        st.session_state.vorp = vorp
        st.session_state.tiers = tiers
        st.session_state.board = None  # reset board

        st.success("Pipeline complete! See tabs below.")

# ---------- Tabs ----------
tab1, tab2, tab3, tab4 = st.tabs(["Fantasy Points", "VORP", "Tiers", "Draft Board"])

with tab1:
    st.subheader("Fantasy Points (ranked)")
    if st.session_state.fp is not None:
        st.dataframe(st.session_state.fp[["player_name","team","pos","fantasy_points"]], use_container_width=True)
        download_link(st.session_state.fp, "fp_output.csv", "Download fp_output.csv")
    else:
        st.info("Run the pipeline to see fantasy points.")

with tab2:
    st.subheader("VORP (Value Over Replacement)")
    if st.session_state.vorp is not None:
        st.write("Replacement baselines are derived from league size & starters (or your overrides).")
        st.dataframe(st.session_state.vorp[["player_name","team","pos","fantasy_points","replacement_fp","VORP"]],
                     use_container_width=True)
        download_link(st.session_state.vorp, "vorp_output.csv", "Download vorp_output.csv")
    else:
        st.info("Run the pipeline to see VORP.")

with tab3:
    st.subheader("Per-Position Tiers")
    if st.session_state.tiers is not None:
        st.dataframe(st.session_state.tiers[["player_name","team","pos","VORP","Tier"]],
                     use_container_width=True)
        download_link(st.session_state.tiers, "tiers_output.csv", "Download tiers_output.csv")
    else:
        st.info("Run the pipeline to see tiers.")

with tab4:
    st.subheader("Live Draft Board")
    if init_board and st.session_state.tiers is not None:
        st.session_state.board = st.session_state.tiers.copy()
        st.success("Draft board initialized from tiers.")

    if st.session_state.board is None:
        st.info("Click 'Initialize Draft Board from Tiers' in the sidebar.")
    else:
        # Remove drafted players UI
        st.markdown("**Remove drafted players (select rows and click 'Remove Selected')**")
        st.dataframe(st.session_state.board[["player_name","team","pos","Tier","VORP"]],
                     use_container_width=True, height=380)

        # Text input for names (comma-separated)
        names = st.text_input("Names to remove (comma-separated, case-insensitive)", "")
        remove_btn = st.button("Remove Selected")

        if remove_btn and names.strip():
            df = st.session_state.board.copy()
            norm = df["player_name"].astype(str).str.lower().str.strip()
            targets = [n.strip().lower() for n in names.split(",") if n.strip()]
            mask = norm.isin(targets)
            removed = df[mask].copy()
            st.session_state.board = df[~mask].copy()

            if not removed.empty:
                removed["removed_at"] = datetime.now().isoformat(timespec="seconds")
                st.session_state.picks_log = pd.concat([st.session_state.picks_log, removed], ignore_index=True)
                st.success(f"Removed {len(removed)} player(s).")
            else:
                st.warning("No matching players found. Check spelling.")

        # Suggestions
        st.markdown("---")
        st.markdown("### Suggestions")
        if st.session_state.board is not None:
            starters = {"QB":float(start_qb), "RB":float(start_rb), "WR":float(start_wr), "TE":float(start_te)}
            have = {"QB":int(have_qb), "RB":int(have_rb), "WR":int(have_wr), "TE":int(have_te)}
            sugg = suggest(st.session_state.board, have, starters, top_n=10)
            st.dataframe(sugg[["player_name","team","pos","Tier","VORP","SuggestScore"]],
                         use_container_width=True)
            download_link(sugg, "suggestions.csv", "Download suggestions.csv")

        st.markdown("---")
        st.markdown("### Picks Log")
        if not st.session_state.picks_log.empty:
            st.dataframe(st.session_state.picks_log[["player_name","team","pos","Tier","VORP","removed_at"]],
                         use_container_width=True)
            download_link(st.session_state.picks_log, "picks_log.csv", "Download picks_log.csv")
        else:
            st.caption("No picks removed yet.")
