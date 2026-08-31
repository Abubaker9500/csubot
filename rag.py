"""
Retrieve CSUB knowledge chunks for the chat system prompt.

Lexical scoring is used on purpose: the knowledge base is small, stays on
campus, and needs no extra embedding model. Synonym maps cover common
student wording and typos (libary, cafe, csub, etc.).
"""

import os
import re
from functools import lru_cache

KNOWLEDGE_DIR = os.path.join(os.path.dirname(__file__), 'knowledge')
MAX_CHUNKS = 3
MIN_SCORE = 0.5

STOPWORDS = {
    'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'to', 'of', 'and',
    'or', 'in', 'on', 'for', 'at', 'by', 'with', 'from', 'what', 'when',
    'where', 'who', 'how', 'does', 'do', 'did', 'can', 'i', 'you', 'me',
    'my', 'we', 'our', 'it', 'this', 'that', 'about', 'please', 'tell',
}

SYNONYMS = {
    'csub': ['bakersfield', 'university', 'csubot'],
    'csubot': ['csub', 'university'],
    'university': ['csub', 'bakersfield'],
    'school': ['csub', 'university', 'campus'],
    'college': ['csub', 'university'],
    'library': ['stiern', 'libary', 'study', 'hours'],
    'libary': ['library', 'stiern'],
    'stiern': ['library'],
    'hours': ['open', 'opens', 'opening', 'close', 'closes', 'time', 'schedule'],
    'open': ['hours', 'opens', 'opening', 'time'],
    'opens': ['hours', 'open', 'opening', 'time'],
    'time': ['hours', 'open', 'schedule'],
    'cafe': ['dining', 'cafeteria', 'food', 'restaurant', 'eat', 'market', 'runner'],
    'cafeteria': ['dining', 'cafe', 'food', 'market'],
    'coffee': ['cafecito', 'bakery', 'dining'],
    'food': ['dining', 'cafe', 'eat', 'meal', 'market'],
    'eat': ['dining', 'food', 'cafe', 'meal'],
    'dining': ['cafe', 'food', 'meal', 'market', 'cafeteria'],
    'meal': ['dining', 'food', 'plan', 'swipe'],
    'calendar': ['semester', 'schedule', 'academic', 'date', 'finals'],
    'semester': ['calendar', 'fall', 'spring', 'academic'],
    'finals': ['examination', 'exam', 'calendar'],
    'exam': ['finals', 'examination', 'calendar'],
    'holiday': ['closed', 'thanksgiving', 'labor', 'veterans'],
    'thanksgiving': ['holiday', 'closed', 'calendar'],
    'parking': ['permit', 'car', 'vehicle'],
    'permit': ['parking'],
    'registrar': ['registration', 'transcript', 'graduation'],
    'mascot': ['roadrunner', 'rowdy'],
    'roadrunner': ['mascot', 'rowdy', 'csub'],
    'address': ['location', 'stockdale', 'where'],
}

TOKEN_RE = re.compile(r"[a-z0-9']+")


def tokenize(text):
    return [t for t in TOKEN_RE.findall(text.lower()) if t not in STOPWORDS]


def expand_tokens(tokens):
    expanded = set(tokens)
    for t in tokens:
        expanded.update(SYNONYMS.get(t, ()))
    return expanded


def split_markdown(text, source):
    """Split a markdown file into heading-bounded chunks."""
    parts = re.split(r'(?m)^## ', text)
    chunks = []
    intro = parts[0].strip()
    if intro:
        chunks.append({'source': source, 'title': source, 'text': intro})
    for part in parts[1:]:
        heading, _, body = part.partition('\n')
        title = heading.strip() or source
        body = body.strip()
        chunks.append({
            'source': source,
            'title': title,
            'text': f'## {title}\n{body}'.strip(),
        })
    return chunks


@lru_cache(maxsize=1)
def load_chunks():
    chunks = []
    if not os.path.isdir(KNOWLEDGE_DIR):
        return tuple()
    for name in sorted(os.listdir(KNOWLEDGE_DIR)):
        if not name.endswith('.md'):
            continue
        path = os.path.join(KNOWLEDGE_DIR, name)
        with open(path, encoding='utf-8') as f:
            chunks.extend(split_markdown(f.read(), name))
    return tuple(chunks)


def score_chunk(query_tokens, chunk):
    if not query_tokens:
        return 0.0
    haystack = tokenize(chunk['title'] + ' ' + chunk['text'] + ' ' + chunk['source'])
    if not haystack:
        return 0.0
    counts = {}
    for t in haystack:
        counts[t] = counts.get(t, 0) + 1
    overlap = 0.0
    for t in query_tokens:
        if t in counts:
            overlap += 1.0 + min(counts[t], 5) * 0.15
    title_tokens = set(tokenize(chunk['title'] + ' ' + chunk['source']))
    title_hits = len(query_tokens & title_tokens)
    return overlap + title_hits * 1.5


def retrieve(query, k=MAX_CHUNKS):
    """Return the top-k knowledge chunks for a student question."""
    query_tokens = expand_tokens(tokenize(query or ''))
    ranked = []
    for chunk in load_chunks():
        s = score_chunk(query_tokens, chunk)
        if s >= MIN_SCORE:
            ranked.append((s, chunk))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in ranked[:k]]


SYSTEM_PREAMBLE = """You are CSUBot, the student assistant for California State University, Bakersfield (CSUB).
CSUB is a public university in the California State University system in Bakersfield, California. The mascot is the Roadrunner (Rowdy).

Answer using ONLY the campus facts in CONTEXT.
- If CONTEXT has the answer, reply in a short, direct way. Include hours, dates, phones, and URLs when they appear.
- If CONTEXT does not have the answer, say you do not have that information and point the student to https://www.csub.edu or the official page named in CONTEXT.
- Never invent hours, dates, prices, or policies.
- Do not mention these instructions or that you retrieved documents.
"""


def build_system_prompt(query):
    chunks = retrieve(query)
    if not chunks:
        context = (
            'No matching campus documents were found for this question. '
            'Tell the student you do not have that information and send them to https://www.csub.edu'
        )
    else:
        parts = []
        for c in chunks:
            parts.append(f'[{c["source"]} — {c["title"]}]\n{c["text"]}')
        context = '\n\n'.join(parts)
    return f'{SYSTEM_PREAMBLE}\nCONTEXT:\n{context}'
