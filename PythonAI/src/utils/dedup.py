"""
MinHash LSH based deduplication for massive text collections.
Helps remove redundant data from Common Crawl and other scrapes.
"""
from typing import List, Set, Iterable
import re
try:
    from datasketch import MinHash, MinHashLSH
except ImportError:
    pass

class Deduplicator:
    def __init__(self, threshold: float = 0.8, num_perm: int = 128):
        self.threshold = threshold
        self.num_perm = num_perm
        # Store LSH index
        try:
            self.lsh = MinHashLSH(threshold=self.threshold, num_perm=self.num_perm)
        except NameError:
            self.lsh = None
        self.doc_store = set()
        # Fallback store for non-datasketch mode: map doc_id -> token set
        self._token_store: dict[str, set[str]] = {}

    def _get_tokens(self, text: str) -> Set[str]:
        # Simple whitespace tokenizer
        return set(re.findall(r'\w+', text.lower()))

    def _get_minhash(self, text: str):
        if not self.lsh:
            raise RuntimeError("datasketch is not installed")
        tokens = self._get_tokens(text)
        m = MinHash(num_perm=self.num_perm)
        for d in tokens:
            m.update(d.encode('utf8'))
        return m

    def is_duplicate(self, text: str, doc_id: str = None) -> bool:
        """
        Check if the text is a near-duplicate of something already seen.
        If it's not a duplicate, add it to the index.
        """
        # If datasketch is available, use LSH
        if self.lsh:
            m = self._get_minhash(text)
            result = self.lsh.query(m)
            if len(result) > 0:
                return True

            # Add to index if doc_id provided
            if doc_id and doc_id not in self.doc_store:
                self.lsh.insert(doc_id, m)
                self.doc_store.add(doc_id)
            return False

        # Fallback: simple Jaccard token overlap against seen documents
        tokens = self._get_tokens(text)
        for other_id, other_tokens in self._token_store.items():
            inter = tokens.intersection(other_tokens)
            union = tokens.union(other_tokens)
            jacc = len(inter) / max(1, len(union))
            if jacc >= self.threshold:
                return True

        # Not duplicate — add to fallback store
        if doc_id is None:
            doc_id = str(hash(text))
        self._token_store[doc_id] = tokens
        self.doc_store.add(doc_id)
        return False
        
    def batch_filter(self, items: Iterable[dict], text_key: str = "text", id_key: str = "url") -> List[dict]:
        """
        Takes a batch of dicts, returns only unique ones, updating index in the process.
        """
        unique_items = []
        for item in items:
            text = item.get(text_key, "")
            doc_id = item.get(id_key, str(hash(text)))
            if not self.is_duplicate(text, doc_id=doc_id):
                unique_items.append(item)
        return unique_items
