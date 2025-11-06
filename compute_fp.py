import pandas as pd
import json
import sys
from pathlib import Path

REQUIRED_COLS = [
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

OFF_POS = {"QB","RB","WR","TE"}
POS_SYNONYMS = {
    "HB":"RB","FB":"RB","TB":"RB",
    "WR/TE":"WR","TE/WR":"WR","WR/RB":"WR","RB/WR":"RB",
    "Qb":"QB","Rb":"RB","Wr":"WR","Te":"TE",
}

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

def normalize_pos(s: pd.Series) -> pd.Series:
    s = s.astype(str).fillna("").str.strip()
    # map synonyms then upper
    s = s.map(lambda x: POS_SYNONYMS.get(x, POS_SYNONYMS.get(x.upper(), x))).str.upper()
    return s

def infer_pos(df: pd.DataFrame) -> pd.Series:
    # crude inference: any passing → QB; else any receptions/rec_yds → WR; else any rush → RB; else TE if rec>0 and low rec_yds? keep WR default.
    pos = df.get("pos", pd.Series([""]*len(df)))
    pos = pos.fillna("").astype(str).str.strip()
    empty = pos.eq("") | pos.eq("UNK") | pos.eq("NA") | pos.eq("N/A")
    inferred = pos.copy()

    # start with existing normalized
    inferred = normalize_pos(inferred)

    # only change empties or non-offensive
    idx = empty | ~inferred.isin(OFF_POS)
    sub = df[idx]

    qb_mask = (sub["pass_yds"]>0) | (sub["pass_td"]>0) | (sub["pass_int"]>0)
    wr_mask = (sub["rec"]>0) | (sub["rec_yds"]>0) | (sub["rec_td"]>0)
    rb_mask = (sub["rush_yds"]>0) | (sub["rush_td"]>0)

    inferred.loc[idx & qb_mask] = "QB"
    inferred.loc[idx & ~qb_mask & wr_mask] = "WR"
    inferred.loc[idx & ~qb_mask & ~wr_mask & rb_mask] = "RB"
    # leave others as-is; they may be K/DST etc.

    return inferred

def load_data(players_csv, scoring_json):
    df = pd.read_csv(players_csv)

    with open(scoring_json, "r") as f:
        scoring = json.load(f)

    # Ensure required columns exist
    for c in REQUIRED_COLS:
        if c not in df.columns:
            df[c] = 0

    # Coerce numerics safely
    df = coerce_numeric(df, NUMERIC_COLS)

    # Normalize / infer positions
    df["pos"] = infer_pos(df)
    # Try filtering to offensive positions, but don't drop everything
    filtered = df[df["pos"].isin(OFF_POS)]
    if len(filtered) == 0:
        # fall back: warn and keep all rows (you can still compute points)
        print("⚠️ No rows matched QB/RB/WR/TE after normalization — skipping position filter.")
        filtered = df

    return filtered, scoring

def compute_points(df, scoring):
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

    out = df.copy()
    out["fantasy_points"] = (fp + bonus).astype(float).round(2)
    return out

def main():
    if len(sys.argv) != 3:
        print("Usage: python compute_fp.py PLAYERS_CSV SCORING_JSON")
        sys.exit(1)

    players_csv = Path(sys.argv[1])
    scoring_json = Path(sys.argv[2])

    df, scoring = load_data(players_csv, scoring_json)
    out = compute_points(df, scoring).sort_values("fantasy_points", ascending=False)

    out_path = players_csv.parent / "fp_output.csv"
    out.to_csv(out_path, index=False)
    print(f"Wrote ranked output to: {out_path}")
    print(out[["player_name","team","pos","fantasy_points"]].head(15).to_string(index=False))

if __name__ == "__main__":
    main()
