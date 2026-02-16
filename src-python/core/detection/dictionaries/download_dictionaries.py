#!/usr/bin/env python3
"""Download comprehensive dictionaries from Hunspell/LibreOffice sources.

These dictionaries contain 100k-300k words per language including all
conjugations, plurals, and technical/professional vocabulary.

Sources:
- LibreOffice dictionary extensions (hunspell-based)
- SCOWL for English
- Wiktionary word lists
"""

import urllib.request
import zipfile
import io
import re
from pathlib import Path

DICT_DIR = Path(__file__).parent

# URLs for comprehensive dictionary sources
# Using LibreOffice extension repository + GitHub mirrors
DICT_SOURCES = {
    "en": [
        # SCOWL-based comprehensive English (650k+ words)
        "https://raw.githubusercontent.com/dwyl/english-words/master/words_alpha.txt",
    ],
    "fr": [
        # French Hunspell dictionary
        "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/fr_FR/fr.dic",
    ],
    "de": [
        # German Hunspell dictionary  
        "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/de/de_DE_frami.dic",
    ],
    "es": [
        # Spanish Hunspell dictionary
        "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/es/es_ES.dic",
    ],
    "it": [
        # Italian Hunspell dictionary
        "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/it_IT/it_IT.dic",
    ],
    "nl": [
        # Dutch Hunspell dictionary
        "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/nl_NL/nl_NL.dic",
    ],
    "pt": [
        # Portuguese Hunspell dictionary (Brazilian + European)
        "https://raw.githubusercontent.com/LibreOffice/dictionaries/master/pt_BR/pt_BR.dic",
    ],
}


def download_url(url: str) -> str:
    """Download URL content as text."""
    print(f"  Downloading {url}...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as response:
        content = response.read()
        # Try UTF-8 first, then Latin-1
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            return content.decode("latin-1")


def parse_hunspell_dic(content: str) -> set[str]:
    """Parse Hunspell .dic file and extract words.
    
    Hunspell .dic format:
    - First line is word count (optional)
    - Each subsequent line: word[/flags]
    - We extract just the word part (before /)
    """
    words = set()
    lines = content.strip().split("\n")
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Skip word count line (just a number)
        if line.isdigit():
            continue
        # Extract word (before / if present)
        word = line.split("/")[0].strip()
        # Skip empty, too short, or containing digits
        if len(word) < 2:
            continue
        if any(c.isdigit() for c in word):
            continue
        # Normalize to lowercase
        words.add(word.lower())
    
    return words


def parse_wordlist(content: str) -> set[str]:
    """Parse simple word list (one word per line)."""
    words = set()
    for line in content.strip().split("\n"):
        word = line.strip().lower()
        if len(word) >= 2 and not any(c.isdigit() for c in word):
            words.add(word)
    return words


def download_language(lang: str) -> set[str]:
    """Download and merge all dictionary sources for a language."""
    words = set()
    
    for url in DICT_SOURCES.get(lang, []):
        try:
            content = download_url(url)
            if url.endswith(".dic"):
                new_words = parse_hunspell_dic(content)
            else:
                new_words = parse_wordlist(content)
            print(f"    Got {len(new_words):,} words")
            words.update(new_words)
        except Exception as e:
            print(f"    Error: {e}")
    
    return words


def main():
    """Download comprehensive dictionaries for all supported languages."""
    print("Downloading comprehensive dictionaries...\n")
    
    for lang in DICT_SOURCES:
        print(f"\n{lang.upper()}:")
        
        # Load existing dictionary
        existing_path = DICT_DIR / f"{lang}.txt"
        existing_words = set()
        if existing_path.exists():
            with open(existing_path, encoding="utf-8") as f:
                existing_words = {line.strip().lower() for line in f if line.strip()}
            print(f"  Existing: {len(existing_words):,} words")
        
        # Download new words
        new_words = download_language(lang)
        print(f"  Downloaded: {len(new_words):,} words")
        
        # Merge
        merged = existing_words | new_words
        print(f"  Merged: {len(merged):,} words")
        
        # Save
        with open(existing_path, "w", encoding="utf-8") as f:
            for word in sorted(merged):
                f.write(word + "\n")
        
        print(f"  Saved to {existing_path.name}")
    
    print("\nDone!")


if __name__ == "__main__":
    main()
