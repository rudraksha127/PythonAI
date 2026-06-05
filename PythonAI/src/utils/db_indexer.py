import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Any
from loguru import logger

class SQLiteIndexer:
    """
    Indexes collected metadata (JSONL) into a fast SQLite database
    for instant querying and retrieval.
    """
    def __init__(self, db_path: str = "python_brain_godmode/metadata_index.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._init_db()
        
    def _init_db(self):
        c = self.conn.cursor()
        # Create a generic metadata table
        c.execute('''
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                source TEXT,
                title TEXT,
                content_preview TEXT,
                url TEXT,
                metadata JSON
            )
        ''')
        # Create indexes for fast lookup
        c.execute('CREATE INDEX IF NOT EXISTS idx_source ON documents(source)')
        self.conn.commit()

    def index_batch(self, documents: List[Dict[str, Any]]):
        """
        Inserts a batch of documents into the SQLite index.
        """
        c = self.conn.cursor()
        rows = []
        for doc in documents:
            doc_id = doc.get('id') or doc.get('url') or str(hash(json.dumps(doc, sort_keys=True)))
            source = doc.get('source', 'unknown')
            title = doc.get('title', '')
            preview = (doc.get('abstract') or doc.get('text') or '')[:500]
            url = doc.get('pdf_url') or doc.get('open_access_url') or doc.get('url') or ''
            
            rows.append((doc_id, source, title, preview, url, json.dumps(doc)))
            
        try:
            c.executemany('''
                INSERT OR REPLACE INTO documents (id, source, title, content_preview, url, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', rows)
            self.conn.commit()
            logger.info(f"Indexed {len(rows)} documents to SQLite")
        except Exception as e:
            logger.error(f"Failed to index batch to SQLite: {e}")

    def search(self, query: str, limit: int = 10) -> List[Dict]:
        c = self.conn.cursor()
        c.execute('''
            SELECT id, source, title, content_preview, url 
            FROM documents 
            WHERE title LIKE ? OR content_preview LIKE ?
            LIMIT ?
        ''', (f"%{query}%", f"%{query}%", limit))
        
        results = []
        for row in c.fetchall():
            results.append({
                "id": row[0],
                "source": row[1],
                "title": row[2],
                "preview": row[3],
                "url": row[4]
            })
        return results

    def close(self):
        self.conn.close()
