# wake_word.py
"""
Wake-word detector for "Cave" and "KV" supporting Brazilian Portuguese and English
phonetic/orthographic variations and configurable sensitivity.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import List, Tuple


@dataclass(frozen=True)
class WakeWordMatch:
    """Result of wake-word inspection on an utterance."""

    detected: bool
    matched_token: str
    remaining_command: str
    confidence: float


class WakeWordDetector:
    """
    Detects 'Cave' and 'KV' at the start of or inside spoken utterances,
    accounting for pt-BR and en-US speech recognition transcriptions,
    accents, capitalization, and sensitivity thresholds.
    """

    # Exact high-confidence phonetic/orthographic transcriptions produced by pt-BR/en-US ASR
    EXACT_SINGLE_VARIANTS = {
        "cave",
        "kv",
        "cavi",
        "kave",
        "kavi",
        "queive",
        "keive",
        "keivi",
        "queivi",
        "cáve",
        "cávi",
        "caive",
        "kayve",
        "k.v.",
        "k-v",
    }

    # Two-token phonetic representations of "KV" / "Cave" in pt-BR ("cá vê", "ka ve", "kei vi")
    EXACT_TWO_WORD_VARIANTS = {
        ("k", "v"),
        ("ka", "ve"),
        ("ca", "ve"),
        ("ca", "vi"),
        ("cá", "vê"),
        ("ca", "vê"),
        ("k", "vê"),
        ("kei", "vi"),
        ("quei", "vi"),
        ("quei", "ve"),
        ("key", "vi"),
        ("kay", "vee"),
    }

    # Polite prefixes allowed before the wake word ("Oi Cave", "Ei KV", "Hey Cave")
    POLITE_PREFIXES = {"oi", "ei", "olá", "ola", "hey", "ok", "okay", "fala"}

    def __init__(self, sensitivity: float = 0.78) -> None:
        self._sensitivity = max(0.5, min(1.0, float(sensitivity)))

    @property
    def sensitivity(self) -> float:
        return self._sensitivity

    @sensitivity.setter
    def sensitivity(self, value: float) -> None:
        self._sensitivity = max(0.5, min(1.0, float(value)))

    @staticmethod
    def _strip_accents(text: str) -> str:
        normalized = unicodedata.normalize("NFD", text)
        return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")

    @classmethod
    def _clean_token(cls, token: str) -> str:
        return re.sub(r"^[^\w]+|[^\w]+$", "", token.lower())

    def detect_and_strip(self, utterance: str) -> WakeWordMatch:
        """
        Inspect an utterance for 'Cave' or 'KV'.
        If found at the start (optionally preceded by a greeting like 'Oi'/'Hey'),
        strip the wake word and any trailing punctuation so the wake word is never
        accidentally typed or executed as part of the command.
        """
        if not utterance or not utterance.strip():
            return WakeWordMatch(False, "", "", 0.0)

        raw = utterance.strip()
        # Split keeping token character spans so we can slice out the exact remainder
        token_matches = list(re.finditer(r"\S+", raw))
        if not token_matches:
            return WakeWordMatch(False, "", "", 0.0)

        idx = 0
        first_clean = self._clean_token(token_matches[0].group(0))
        if first_clean in self.POLITE_PREFIXES and len(token_matches) > 1:
            idx = 1

        # 1. Check two-word phonetic wake words ("cá vê", "k v", "kei vi")
        if idx + 1 < len(token_matches):
            t1_raw = self._clean_token(token_matches[idx].group(0))
            t2_raw = self._clean_token(token_matches[idx + 1].group(0))
            t1_no_acc = self._strip_accents(t1_raw)
            t2_no_acc = self._strip_accents(t2_raw)
            if (t1_raw, t2_raw) in self.EXACT_TWO_WORD_VARIANTS or (
                t1_no_acc,
                t2_no_acc,
            ) in self.EXACT_TWO_WORD_VARIANTS:
                end_pos = token_matches[idx + 1].end()
                remainder = self._clean_remainder(raw[end_pos:])
                matched_str = f"{token_matches[idx].group(0)} {token_matches[idx + 1].group(0)}"
                return WakeWordMatch(True, matched_str, remainder, 1.0)

        # 2. Check single-word exact variants ("cave", "kv", "queive", "cavi")
        target_match = token_matches[idx]
        target_clean = self._clean_token(target_match.group(0))
        target_no_acc = self._strip_accents(target_clean)

        if (
            target_clean in self.EXACT_SINGLE_VARIANTS
            or target_no_acc in self.EXACT_SINGLE_VARIANTS
        ):
            remainder = self._clean_remainder(raw[target_match.end() :])
            return WakeWordMatch(True, target_match.group(0), remainder, 1.0)

        # 3. Fuzzy phonetic similarity check governed by sensitivity setting
        # Higher sensitivity (e.g., 0.85) accepts lower similarity threshold (e.g. "caves", "kavi")
        required_ratio = 1.0 - ((self._sensitivity - 0.5) * 0.45)
        best_ratio = max(
            SequenceMatcher(None, target_no_acc, "cave").ratio(),
            SequenceMatcher(None, target_no_acc, "cavi").ratio(),
            SequenceMatcher(None, target_no_acc, "queive").ratio(),
        )
        if len(target_no_acc) >= 3 and best_ratio >= required_ratio:
            remainder = self._clean_remainder(raw[target_match.end() :])
            return WakeWordMatch(True, target_match.group(0), remainder, best_ratio)

        return WakeWordMatch(False, "", raw, 0.0)

    @staticmethod
    def _clean_remainder(text: str) -> str:
        """Remove leading commas, colons, dashes, or whitespace after the wake word."""
        return re.sub(r"^[\s,.:;\-!?]+", "", text).strip()