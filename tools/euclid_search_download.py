#!/usr/bin/env python3
"""Search Project Euclid and download PDFs using journal abbreviation + urlId as filename.

Usage:
    python3 euclid_search_download.py "Peter Gärdefors"
    python3 euclid_search_download.py "Peter Gärdefors" --download
    python3 euclid_search_download.py "Peter Gärdefors" --download --output /home/wkolbe/pdfdrill-library
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

BASE = "https://projecteuclid.org"
HEADERS = {"User-Agent": "euclid-download/1.0 (personal research downloader)"}

# Journal name -> WoS-style abbreviation
JOURNAL_ABBREV = {
    "Notre_Dame_Journal_of_Formal_Logic": "Notre-Dame-J-Formal-Logic",
    "Annals_of_Mathematics": "Annals-of-Math",
    "Bulletin_of_the_American_Mathematical_Society": "Bull-AMS",
    "Transactions_of_the_American_Mathematical_Society": "Trans-AMS",
    "Proceedings_of_the_National_Academy_of_Sciences": "PNAS",
    "Journal_of_Functional_Analysis": "J-Functional-Analysis",
    "Mathematical_Annalen": "Math-Annalen",
    "Inventiones_Mathematicae": "Inventiones-Math",
    "Acta_Mathematica": "Acta-Math",
    "Duke_Mathematical_Journal": "Duke-Math-J",
    "Communications_on_Pure_and_Applied_Mathematics": "CPAM",
    "SIAM_Journal_on_Algebraic_and_Discrete_Methods": "SIAM-Alg-Discrete",
    "Journal_of_Algebra": "J-Algebra",
    "Algebra_universalis": "Algebra-Universalis",
    "Journal_of_Symbolic_Logic": "J-Symbolic-Logic",
    "Annals_of_Mathematical_Logic": "Annals-Math-Logic",
    "Zeitschrift_für_Mathematische_Logik_Grundlagen_der_Mathematik": "ZML-Math-Logic",
    "The_Journal_of_Symbolic_Logic": "J-Symbolic-Logic",
    "Logic_Journal_of_the_IMGPL": "Logic-IGPL",
    "Studia_Logica": "Studia-Logica",
}


def journal_abbrev(journal_name):
    """Get WoS-style abbreviation for a journal name."""
    return JOURNAL_ABBREV.get(journal_name, journal_name.replace("_", "-"))


def search(session, term, timeout=30):
    """Search Project Euclid and return results."""
    url = BASE + "/search"
    params = {"term": term}
    response = session.get(url, params=params, headers=HEADERS, timeout=timeout)
    response.raise_for_status()

    # Find DisplayResults([...]) in the HTML
    soup = BeautifulSoup(response.text, "html.parser")
    for script in soup.find_all("script"):
        if script.string and "DisplayResults" in script.string:
            text = script.string
            match = re.search(r'DisplayResults\(\[({.*})\]\)', text, re.DOTALL)
            if match:
                data = json.loads(match.group(1))
                return data

    # Fallback: regex on raw HTML
    match = re.search(r'DisplayResults\(\[({.*})\]\)', response.text, re.DOTALL)
    if match:
        data = json.loads(match.group(1))
        return data

    return {"ResultsCount": 0, "Items": []}


def download_pdf(session, url_id, target, timeout=60):
    """Download a PDF from Project Euclid."""
    url = BASE + "/journalArticle/Download?urlId=" + quote(url_id, safe="")
    temp = target.with_name(target.name + ".part")
    try:
        with session.get(url, stream=True, timeout=timeout) as r:
            r.raise_for_status()
            content_type = r.headers.get("Content-Type", "").lower()
            first = b""
            for chunk in r.iter_content(chunk_size=65536):
                first += chunk
                if len(first) >= 1024:
                    break
            if not first.lstrip(b"\xef\xbb\xbf\x00\t\r\n ").startswith(b"%PDF-"):
                raise ValueError(f"not a PDF (Content-Type: {content_type}; URL: {r.url})")
            with temp.open("wb") as f:
                f.write(first)
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
        temp.replace(target)
        return True
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description="Search Project Euclid and download PDFs")
    parser.add_argument("term", help="Search term")
    parser.add_argument("--download", action="store_true", help="Download PDFs after showing results")
    parser.add_argument("--output", type=Path, default=Path("/home/wkolbe/pdfdrill-library"), help="Output directory")
    parser.add_argument("--timeout", type=int, default=30, help="Request timeout")
    args = parser.parse_args()

    with requests.Session() as session:
        session.headers.update(HEADERS)

        # Search
        print(f"Searching Project Euclid for: '{args.term}'")
        data = search(session, args.term, args.timeout)
        count = data.get("ResultsCount", 0)
        items = data.get("Items", [])

        print(f"Results: {count}")
        if count == 0:
            print("No results found.")
            return 1

        # Show results
        for i, item in enumerate(items):
            url_id = item.get("UrlId", "")
            title = item.get("Title", "")
            journal = item.get("JournalName", "")
            doi = item.get("DOI", "")
            date = item.get("PublicationDisplayDate", "")
            authors = item.get("AuthorEditorLinks", "")
            abbrev = journal_abbrev(journal)

            # Parse url_id to get code and number
            parts = url_id.split("/")
            code = parts[0] if len(parts) > 0 else ""
            num = parts[-1] if parts else ""

            filename = f"{abbrev}_{code}-{num}.pdf"

            print(f"\n--- Result {i+1} ---")
            print(f"  Title:    {title}")
            print(f"  Authors:  {authors.replace('|', ', ').strip()}")
            print(f"  Journal:  {journal} -> {abbrev}")
            print(f"  urlId:    {url_id}")
            print(f"  DOI:      {doi}")
            print(f"  Date:     {date}")
            print(f"  Filename: {filename}")

        if not args.download:
            print(f"\nUse --download to download these {count} PDF(s).")
            return 0

        # Confirm download
        print(f"\nDownload {count} PDF(s) to {args.output}? [y/N] ", end="")
        sys.stdout.flush()
        answer = input().strip().lower()
        if answer not in ("y", "yes"):
            print("Cancelled.")
            return 0

        # Download
        args.output.mkdir(parents=True, exist_ok=True)
        manifest = args.output / "manifest.csv"
        failures = 0
        downloaded = 0

        with manifest.open("a", newline="", encoding="utf-8") as mf:
            writer = csv.DictWriter(mf, fieldnames=["urlId", "filename", "title", "journal", "doi", "date"])
            if mf.tell() == 0:
                writer.writeheader()

            for item in items:
                url_id = item.get("UrlId", "")
                title = item.get("Title", "")
                journal = item.get("JournalName", "")
                doi = item.get("DOI", "")
                date = item.get("PublicationDisplayDate", "")
                abbrev = journal_abbrev(journal)

                parts = url_id.split("/")
                code = parts[0] if len(parts) > 0 else ""
                num = parts[-1] if parts else ""
                filename = f"{abbrev}_{code}-{num}.pdf"
                target = args.output / filename

                if target.exists():
                    print(f"exists: {target}")
                    continue

                try:
                    download_pdf(session, url_id, target, args.timeout)
                    writer.writerow({"urlId": url_id, "filename": filename, "title": title,
                                     "journal": journal, "doi": doi, "date": date})
                    mf.flush()
                    print(f"downloaded: {target}")
                    downloaded += 1
                except Exception as exc:
                    failures += 1
                    print(f"failed: {url_id}: {exc}", file=sys.stderr)

        print(f"\nDone: {downloaded} downloaded, {failures} failed.")
        return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())