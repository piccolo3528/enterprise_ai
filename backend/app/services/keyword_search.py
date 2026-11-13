"""Keyword (lexical) search over chunk text with PostgreSQL full-text search (ARCHITECTURE §4.3).

`chunks.search_vector` is `to_tsvector('english', text)`: the chunk's words, lower-cased, stemmed
("carrying" -> "carri") and without stop words ("the", "of"), kept up to date by PostgreSQL and
indexed with GIN.

How a query matches (D55, measured on the user's 74 HR chunks in M10):
- The query is turned into the same kind of lexemes, and a chunk matches if it contains ANY of
  them. `websearch_to_tsquery` (the original plan) requires ALL of them: fine for
  "carry forward leave", but it found nothing for every full question we tried ("How many days
  of annual leave can I carry forward to next year?" -> 0 rows), because questions contain
  words like "how", "many", "next" that the answer passage doesn't.
- Ranking: first by how many of the query's distinct lexemes the chunk contains, then by
  `ts_rank_cd` (cover density: how often and how close together they occur). PostgreSQL's rank
  has no IDF (it doesn't know "leave" is in almost every chunk of a leave policy), so on its own
  it put "Leave Year and Leave Types" first for "carry forward leave"; counting matched words
  first put both carry-forward sections on top. Real BM25 would weigh rare words higher: noted
  as a limitation, with Qdrant sparse vectors as the alternative.
- Score: `matched + rank / (1 + rank)`. The whole part is the number of matched words, the
  fraction is the rank squeezed into 0..1 (ts_rank_cd normalization 32), so sorting by the score
  is exactly the order above, and the UI can show "3 of 3 words".

Only chunks of `ready` documents in a knowledge base the caller owns are searched.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

# The query's lexemes, each quoted as a tsquery term by hand ('...' with ' and \ escaped) and
# cast with ::tsquery, which takes the lexeme as it is: it was already stemmed by
# to_tsvector('english', ...), so parsing it again (to_tsquery) could split or re-stem it
# ("nx-hr-002" would become several terms).
_TERMS = r"""
WITH terms AS (
    SELECT ('''' || replace(replace(lexeme, '\', '\\'), '''', '''''') || '''')::tsquery AS term
    FROM unnest(tsvector_to_array(to_tsvector('english', :query))) AS lexeme
),
q AS (
    SELECT (SELECT string_agg(term::text, ' | ') FROM terms)::tsquery AS any_term,
           (SELECT count(*) FROM terms) AS term_count
)
"""

_SEARCH = (
    _TERMS
    + """
SELECT c.id,
       (SELECT count(*) FROM terms WHERE c.search_vector @@ terms.term) AS matched,
       ts_rank_cd(c.search_vector, q.any_term, 32) AS rank
FROM q, chunks c
JOIN documents d ON d.id = c.document_id
JOIN knowledge_bases kb ON kb.id = c.kb_id
WHERE c.kb_id = :kb_id
  AND kb.owner_id = :owner_id
  AND d.status = 'ready'
  AND c.search_vector @@ q.any_term
  {document_filter}
ORDER BY matched DESC, rank DESC, c.id
LIMIT :limit
"""
)

_COUNT_TERMS = _TERMS + "SELECT term_count FROM q"


@dataclass(frozen=True)
class KeywordHit:
    chunk_id: uuid.UUID
    matched: int  # how many of the query's distinct words the chunk contains
    rank: float  # ts_rank_cd, normalized to 0..1

    @property
    def score(self) -> float:
        return self.matched + self.rank


def count_terms(db: Session, query: str) -> int:
    """How many searchable words the query has (stop words and punctuation don't count)."""
    return db.execute(text(_COUNT_TERMS), {"query": query}).scalar_one()


def keyword_search(
    db: Session,
    *,
    owner_id: uuid.UUID,
    kb_id: uuid.UUID,
    query: str,
    limit: int,
    document_id: uuid.UUID | None = None,
) -> list[KeywordHit]:
    """Best keyword matches first. A query of only stop words ("the of") matches nothing."""
    params = {"query": query, "owner_id": owner_id, "kb_id": kb_id, "limit": limit}
    document_filter = ""
    if document_id is not None:
        document_filter = "AND c.document_id = :document_id"
        params["document_id"] = document_id
    rows = db.execute(text(_SEARCH.format(document_filter=document_filter)), params).all()
    return [KeywordHit(chunk_id=row.id, matched=row.matched, rank=row.rank) for row in rows]
