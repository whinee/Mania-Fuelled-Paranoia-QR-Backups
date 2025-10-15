from bs4 import BeautifulSoup
import json
import os

from alltheutils.utils import parent_dir_nth_times

INPUT_HTML_FILE = os.path.join(parent_dir_nth_times(__file__), "raw.html")
OUTPUT_JSON_FILE = "output.json"
PREFIX_TO_STRIP = "https://en.wiktionary.org/wiki/"
SUFFIX_TO_STRIP = "#Japanese"

def extract_links(html_file, prefix_to_strip=None, suffix_to_strip=None,):
    with open(html_file, encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    links_dict = {}

    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        href = a["href"]
        if prefix_to_strip and href.startswith(prefix_to_strip):
            href = href[len(prefix_to_strip):]

        if suffix_to_strip and href.endswith(suffix_to_strip):
            href = href[:-len(suffix_to_strip)]

        if text:  # avoid empty link texts
            links_dict[text] = href

    return links_dict
if __name__ == "__main__":
    data = extract_links(INPUT_HTML_FILE, PREFIX_TO_STRIP, SUFFIX_TO_STRIP)
    with open(OUTPUT_JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Done! Saved {len(data)} links to '{OUTPUT_JSON_FILE}'")