"""
Splits an already-generated simulated-readings CSV into fixed-size chunk
files, for pushing to the remote database incrementally instead of in one
long-running run.

Does NOT regenerate data — it splits the existing, already-documented and
verified dataset (see CODE_WALKTHROUGH.md's "Verified result" section) so
every chunk still contains exactly the same rows and injected scenarios as
the original file, just physically divided.

Usage:
    python split_csv.py --input output/simulated_readings.csv --size 10000
    python split_csv.py --input output/simulated_readings.csv --size 5000 --output-dir output/chunks

Produces files named <input-stem>_part1.csv, <input-stem>_part2.csv, ...
in the output directory (default: same directory as the input file), each
with the same header row as the original so `app.ingestion.ingest` can read
each chunk exactly like any other CSV.
"""

import argparse
import csv
import os


def split_csv(input_path: str, chunk_size: int, output_dir: str) -> list[str]:
    os.makedirs(output_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(input_path))[0]

    written_files = []
    with open(input_path, newline="", encoding="utf-8") as infile:
        reader = csv.reader(infile)
        header = next(reader)

        part_number = 1
        rows_in_current_part = 0
        outfile = None
        writer = None

        def open_new_part():
            nonlocal outfile, writer, part_number, rows_in_current_part
            if outfile is not None:
                outfile.close()
            part_path = os.path.join(output_dir, f"{stem}_part{part_number}.csv")
            outfile = open(part_path, "w", newline="", encoding="utf-8")
            writer = csv.writer(outfile)
            writer.writerow(header)
            written_files.append(part_path)
            rows_in_current_part = 0
            return outfile, writer

        outfile, writer = open_new_part()

        for row in reader:
            if rows_in_current_part == chunk_size:
                part_number += 1
                outfile, writer = open_new_part()
            writer.writerow(row)
            rows_in_current_part += 1

        if outfile is not None:
            outfile.close()

    return written_files


def main():
    parser = argparse.ArgumentParser(description="Split a simulated-readings CSV into fixed-size chunks.")
    parser.add_argument("--input", required=True, help="Path to the full CSV to split, e.g. output/simulated_readings.csv")
    parser.add_argument("--size", type=int, required=True, help="Rows per chunk, e.g. 10000 or 5000")
    parser.add_argument("--output-dir", default=None, help="Directory for chunk files (default: same directory as --input)")
    args = parser.parse_args()

    output_dir = args.output_dir or os.path.dirname(os.path.abspath(args.input))
    files = split_csv(args.input, args.size, output_dir)

    print(f"Split {args.input} into {len(files)} chunk(s) of up to {args.size} rows each:")
    for f in files:
        with open(f, newline="", encoding="utf-8") as chunk_file:
            row_count = sum(1 for _ in chunk_file) - 1  # minus header
        print(f"  {f}  ({row_count} rows)")


if __name__ == "__main__":
    main()
