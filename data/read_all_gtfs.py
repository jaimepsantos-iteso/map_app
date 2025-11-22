"""Read all GTFS .txt files into pandas DataFrames and provide helpers.

Usage examples:
  python data/read_all_gtfs.py                # prints summary
  python data/read_all_gtfs.py --save outdir  # saves CSVs to `outdir`
"""
from pathlib import Path
import pandas as pd
from typing import Dict


DEFAULT_GTFS_DIR = Path(__file__).parent / "gtfs"


def list_gtfs_files(gtfs_dir: Path = DEFAULT_GTFS_DIR):
    gtfs_dir = Path(gtfs_dir)
    if not gtfs_dir.exists():
        return []
    return sorted([p for p in gtfs_dir.glob("*.txt") if p.is_file()])


def read_gtfs_files(gtfs_dir: Path | str = None) -> Dict[str, pd.DataFrame]:
    """Read every `*.txt` file in `gtfs_dir` into a pandas DataFrame.

    Returns a dict mapping filename stem (e.g. `stops`) -> DataFrame.
    All columns are read as strings to avoid dtype surprises.
    """
    gtfs_dir = Path(gtfs_dir) if gtfs_dir else DEFAULT_GTFS_DIR
    files = list_gtfs_files(gtfs_dir)
    dfs: Dict[str, pd.DataFrame] = {}
    for p in files:
        key = p.stem
        try:
            df = pd.read_csv(p, dtype=str, keep_default_na=False, na_values=[""], low_memory=False)
            dfs[key] = df
        except Exception:
            # fallback: more tolerant reader
            df = pd.read_csv(p, dtype=str, engine="python", low_memory=False, on_bad_lines="skip")
            dfs[key] = df
    return dfs


def summarize_dfs(dfs: Dict[str, pd.DataFrame]):
    """Print a one-line summary for each GTFS table."""
    if not dfs:
        print("No GTFS tables found.")
        return
    for k, df in dfs.items():
        cols_preview = ", ".join(df.columns.tolist()[:10])
        more = "..." if df.shape[1] > 10 else ""
        print(f"{k}: {df.shape[0]} rows x {df.shape[1]} cols; columns: {cols_preview}{more}")


def save_tables(dfs: Dict[str, pd.DataFrame], outdir: Path | str):
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    for k, df in dfs.items():
        csv_path = outdir / f"{k}.csv"
        df.to_csv(csv_path, index=False)
    print(f"Saved {len(dfs)} tables to {outdir}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Read GTFS files into pandas DataFrames")
    parser.add_argument("--gtfs-dir", "-g", default=str(DEFAULT_GTFS_DIR), help="GTFS directory path")
    parser.add_argument("--save", "-s", help="Directory to save CSV outputs")
    args = parser.parse_args()

    dfs = read_gtfs_files(args.gtfs_dir)
    summarize_dfs(dfs)
    if args.save:
        save_tables(dfs, args.save)
