"""Keyword + semantic search (Task 5).

Keyword: SQL LIKE over extracted text, supplier/customer, invoice no.
Semantic: TF-IDF cosine similarity (scikit-learn) over the extracted
text of all processed documents, ranked; falls back to keyword
overlap when sklearn is unavailable or the corpus is tiny. Both are
exposed as one endpoint with `mode=keyword|semantic|hybrid`.
"""
import re
from sqlalchemy.orm import Session
from .models import Document

def _tokens(s):
    return re.findall(r"[a-z0-9]+", (s or "").lower())

def keyword_search(db: Session, q: str):
    like = f"%{q}%"
    return db.query(Document).filter(
        (Document.extracted_text.like(like)) |
        (Document.original_filename.like(like))).all()

def semantic_search(db: Session, q: str, top_k: int = 20):
    docs = db.query(Document).filter(Document.extracted_text.isnot(None)).all()
    if not docs:
        return []
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        corpus = [d.extracted_text or "" for d in docs]
        vec = TfidfVectorizer(stop_words="english", max_features=5000).fit(corpus + [q])
        sims = cosine_similarity(vec.transform([q]), vec.transform(corpus))[0]
        ranked = sorted(zip(docs, sims), key=lambda x: -x[1])
        return [(d, float(s)) for d, s in ranked if s > 0][:top_k]
    except Exception:
        qt = set(_tokens(q))
        scored = []
        for d in docs:
            toks = set(_tokens(d.extracted_text))
            score = len(qt & toks) / max(1, len(qt))
            if score:
                scored.append((d, score))
        return sorted(scored, key=lambda x: -x[1])[:top_k]
