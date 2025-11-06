
import argparse
import json
import sys
from pathlib import Path
import pandas as pd

STANDARD = ["player_name","team","pos","pass_yds","pass_td","pass_int","rush_yds","rush_td","rec","rec_yds","rec_td"]

# Common variants seen in projection/stat CSVs (lowercased for matching)
AUTO_MAP = {
    "player_name": ["player","name","player name","full_name","fullname","player_name"],
    "team": ["team","nfl team","pro_team","pro team","proteam","tm"],
    "pos": ["pos","position","player position"],
    "pass_yds": ["pass_yds","pass yds","pass yards","passyds","passyards","passyards_g","py","pyards","passingyards"],
    "pass_td": ["pass_td","pass tds","pass touchdowns","pass td","ptd","passingtd","pass_td_proj","pass_tds_proj"],
    "pass_int": ["int","ints","interceptions","pass_int","pass int","interception"],
    "rush_yds": ["rush_yds","rush yds","rush yards","rushyards","ry","rushingyards"],
    "rush_td": ["rush_td","rush tds","rush touchdowns","rtd","rushingtd","rush td"],
    "rec": ["rec","receptions","catches","recs"],
    "rec_yds": ["rec_yds","rec yds","rec yards","receivingyards","ryds","receiving yds"],
    "rec_td": ["rec_td","rec tds","receiving touchdowns","rctd","receivingtd","rec td"],
}

def guess_mapping(cols):
    """
    Return a mapping dict {source_col -> standard_col} using AUTO_MAP.
    """
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

def main():
    ap = argparse.ArgumentParser(description="Map any projections CSV to standard schema for fantasy calculator.")
    ap.add_argument("input_csv", help="Path to your raw projections CSV")
    ap.add_argument("--mapping_json", help="Optional JSON file with {source_col: standard_col} renames", default=None)
    ap.add_argument("--out_csv", help="Output path (default players_auto.csv next to input)", default=None)
    args = ap.parse_args()

    inp = Path(args.input_csv)
    if not inp.exists():
        print(f"ERROR: {inp} does not exist.")
        sys.exit(1)

    df = pd.read_csv(inp)

    # Start with auto-guess
    auto_map = guess_mapping(df.columns)

    # Merge with user mapping if provided (user mapping wins)
    user_map = {}
    if args.mapping_json:
        with open(args.mapping_json, "r") as f:
            user_map = json.load(f)

    # Build final rename mapping: source_col -> standard_col
    rename_map = {}
    # Apply user-provided first where possible
    for src, dest in user_map.items():
        if src in df.columns and dest in STANDARD:
            rename_map[src] = dest

    # Fill gaps with auto mapping
    for src, dest in auto_map.items():
        if src not in rename_map:
            rename_map[src] = dest

    # Apply renames
    df2 = df.rename(columns=rename_map)

    # Ensure all standard columns exist
    for c in STANDARD:
        if c not in df2.columns:
            df2[c] = 0

    # Keep only standard columns and filter to fantasy positions
    df2 = df2[STANDARD].fillna(0)
    df2 = df2[df2["pos"].astype(str).str.upper().isin(["QB","RB","WR","TE"])]

    out = args.out_csv or (inp.parent / "players_auto.csv")
    df2.to_csv(out, index=False)
    print(f"✅ Wrote standardized CSV to: {out}")
    print("Top rows:")
    print(df2.head(10).to_string(index=False))

if __name__ == "__main__":
    main()
