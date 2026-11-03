"""Read-only SQLite query engine for Antigravity conversation databases.

Connects to ~/.gemini/antigravity-ide/conversations/<cid>.db using read-only URI mode
to safely read trajectory metadata, steps, and generation metadata without locking WAL writes.
Decodes protobuf blobs into structured token and model metrics.
"""

import logging
import os
import sqlite3
from typing import Any, Dict, List, Optional

from antigravity_observer.collector.protobuf_decoder import extract_generation_metadata

logger = logging.getLogger("antigravity_observer.sqlite_reader")


class SqliteReader:
    """Safe read-only access to Antigravity conversation SQLite databases."""

    def __init__(self, db_base_dir: Optional[str] = None):
        if db_base_dir:
            self.db_base_dir = os.path.expanduser(db_base_dir)
        else:
            self.db_base_dir = os.path.expanduser("~/.gemini/antigravity-ide/conversations")

    def get_db_path(self, conversation_id: str) -> Optional[str]:
        """Resolves absolute path to conversation SQLite database file."""
        p = os.path.join(self.db_base_dir, f"{conversation_id}.db")
        return p if os.path.exists(p) else None

    def _get_connection(self, db_path: str) -> sqlite3.Connection:
        """Opens SQLite database with read-only URI to avoid locking active WAL writes."""
        uri = f"file:{os.path.abspath(db_path)}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    def get_trajectory_meta(self, conversation_id: str) -> Dict[str, Any]:
        """Reads trajectory metadata for a conversation."""
        db_path = self.get_db_path(conversation_id)
        if not db_path:
            return {}

        try:
            with self._get_connection(db_path) as conn:
                cur = conn.cursor()
                cur.execute("SELECT * FROM trajectory_meta LIMIT 1")
                row = cur.fetchone()
                if row:
                    return {
                        "trajectory_id": row["trajectory_id"],
                        "cascade_id": row["cascade_id"],
                        "trajectory_type": row["trajectory_type"],
                        "source": row["source"],
                    }
        except Exception as e:
            logger.debug(f"Error reading trajectory_meta for {conversation_id}: {e}")
        return {}

    def get_generations(self, conversation_id: str) -> List[Dict[str, Any]]:
        """Reads and decodes all generation metadata records from gen_metadata table."""
        db_path = self.get_db_path(conversation_id)
        if not db_path:
            return []

        generations = []
        try:
            with self._get_connection(db_path) as conn:
                cur = conn.cursor()
                cur.execute("SELECT idx, size, data FROM gen_metadata ORDER BY idx ASC")
                for row in cur.fetchall():
                    idx = row["idx"]
                    raw_data = row["data"]
                    if raw_data:
                        gen_meta = extract_generation_metadata(raw_data)
                        gen_meta["generation_idx"] = idx
                        generations.append(gen_meta)
        except Exception as e:
            logger.debug(f"Error reading gen_metadata for {conversation_id}: {e}")

        return generations

    def get_generation_by_response_id(self, conversation_id: str, response_id: str) -> Optional[Dict[str, Any]]:
        """Finds generation metadata matching a specific ResponseID."""
        gens = self.get_generations(conversation_id)
        for g in gens:
            if g.get("response_id") == response_id:
                return g
        return None

    def get_aggregate_tokens(self, conversation_id: str) -> Dict[str, Any]:
        """Calculates cumulative token usage across all generations in a conversation."""
        gens = self.get_generations(conversation_id)
        if not gens:
            return {
                "total_generations": 0,
                "prompt_tokens_peak": 0,
                "cumulative_output_tokens": 0,
                "cumulative_thinking_tokens": 0,
                "primary_model": "Unknown",
            }

        peak_prompt = 0
        total_output = 0
        total_thinking = 0
        models = set()

        for g in gens:
            p_tok = g.get("prompt_tokens", 0)
            o_tok = g.get("output_tokens", 0)
            t_tok = g.get("thinking_tokens", 0)
            m_name = g.get("model", "Unknown")

            if p_tok > peak_prompt:
                peak_prompt = p_tok
            total_output += o_tok
            total_thinking += t_tok
            if m_name != "Unknown":
                models.add(m_name)

        return {
            "total_generations": len(gens),
            "prompt_tokens_peak": peak_prompt,
            "cumulative_output_tokens": total_output,
            "cumulative_thinking_tokens": total_thinking,
            "total_tokens_recorded": peak_prompt + total_output,
            "primary_model": list(models)[0] if models else "Gemini 3.8 Flash (High)",
            "models_used": list(models),
        }
