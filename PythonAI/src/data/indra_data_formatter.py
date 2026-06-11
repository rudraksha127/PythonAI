"""
INDRA Data Formatter
====================
Converts raw datasets (text chunks, Q&A pairs) into INDRA-compatible
chat format with domain and language tagging.
"""

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

from src.training.indra_prompt import build_training_system_prompt

logger = logging.getLogger(__name__)

# Basic heuristics if fasttext is not available
HINDI_PATTERN = re.compile(r"[\u0900-\u097F]")


class INDRADataFormatter:
    def __init__(self, output_dir: str = "data/training/formatted"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.seen_hashes: set[str] = set()

    def _get_hash(self, text: str) -> str:
        """MinHash-like simple hashing for deduplication"""
        # simplified dedup by hashing normalized text
        norm = re.sub(r"\s+", " ", text.lower().strip())
        return hashlib.md5(norm.encode("utf-8")).hexdigest()

    def detect_language(self, text: str) -> str:
        """Detect language (en, hi, hinglish, other)"""
        # Simple heuristic without fasttext dependency for now
        hindi_chars = len(HINDI_PATTERN.findall(text))
        if hindi_chars > len(text) * 0.1:
            return "hi"
        if hindi_chars > 0:
            return "hinglish"
        # Naive fallback
        return "en"

    def detect_domain(self, text: str) -> str:
        """Auto-classify into 10 INDRA domains"""
        text_lower = text.lower()
        if any(w in text_lower for w in ["def ", "import ", "class ", "return "]):
            return "engineering"
        if any(w in text_lower for w in ["theorem", "equation", "math", "calculate"]):
            return "math"
        if any(w in text_lower for w in ["india", "scheme", "modi", "gst", "rupee"]):
            return "india"
        if any(w in text_lower for w in ["disease", "patient", "treatment", "medical"]):
            return "medicine"
        return "general"

    def format_pair(self, instruction: str, output: str, source: str = "unknown") -> dict[str, Any] | None:
        """Format a single instruction-output pair into INDRA chat format"""
        if len(instruction) < 10 or len(output) < 30:
            return None

        combo_text = instruction + " " + output
        text_hash = self._get_hash(combo_text)
        if text_hash in self.seen_hashes:
            return None
        self.seen_hashes.add(text_hash)

        lang = self.detect_language(combo_text)
        domain = self.detect_domain(combo_text)

        system_prompt = build_training_system_prompt()

        # Format in standard chat structure
        formatted = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": instruction},
                {"role": "assistant", "content": output},
            ],
            "metadata": {"source": source, "language": lang, "domain": domain},
        }
        return formatted

    def process_file(self, input_path: str, output_name: str) -> str:
        """Process a raw JSON dataset into INDRA format"""
        input_file = Path(input_path)
        if not input_file.exists():
            logger.error(f"Input file not found: {input_path}")
            return ""

        try:
            with open(input_file, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load {input_file}: {e}")
            return ""

        formatted_data = []
        for item in data:
            if isinstance(item, dict):
                instr = item.get("instruction", item.get("prompt", item.get("question", "")))
                out = item.get("output", item.get("response", item.get("answer", "")))
                source = item.get("source", input_file.name)

                if instr and out:
                    fmt = self.format_pair(instr, out, source)
                    if fmt:
                        formatted_data.append(fmt)

        out_path = self.output_dir / f"{output_name}.jsonl"
        with open(out_path, "w", encoding="utf-8") as f:
            for item in formatted_data:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        logger.info(f"Processed {len(formatted_data)} valid examples from {input_file.name}")
        return str(out_path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    formatter = INDRADataFormatter()
    # Simple test
    formatter.process_file("data/training/training_dataset.json", "indra_training_base")
