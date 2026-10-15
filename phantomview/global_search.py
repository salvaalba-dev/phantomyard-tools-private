"""Bounded full-text search over KB copies already authorized by the snapshot."""
import re
import threading
import unicodedata


def normalize(value):
    value = ''.join(c for c in unicodedata.normalize('NFD', value.lower()) if not unicodedata.combining(c))
    return re.sub('[^a-z0-9]+', ' ', value).strip()


def excerpt_at_match(content, term):
    letters = {'a':'[aáàäâãå]', 'e':'[eéèëê]', 'i':'[iíìïî]', 'o':'[oóòöôõ]', 'u':'[uúùüû]', 'n':'[nñ]'}
    match = re.search(''.join(letters.get(c, re.escape(c)) for c in term), content, re.I)
    if not match and len(term) >= 5:
        match = next((m for m in re.finditer(r'[^\W\d_]+', content) if distance(normalize(m.group()), term) <= 1), None)
    start = max(0, (match.start() if match else 0)-80)
    return content[start:start+260]


def distance(a, b):
    if abs(len(a) - len(b)) > 1:
        return 2
    row = list(range(len(b) + 1))
    for i, left in enumerate(a):
        following = [i + 1]
        for j, right in enumerate(b):
            following.append(min(following[j] + 1, row[j + 1] + 1, row[j] + (left != right)))
        row = following
    return row[-1]


class KnowledgeIndex:
    def __init__(self):
        self.lock, self.digest, self.rows = threading.Lock(), None, []
        self.partial = False

    def search(self, snapshot, question, read_note):
        if not isinstance(question, str) or not 1 <= len(question.strip()) <= 200:
            raise ValueError('Expected a search query of 1–200 characters')
        terms = normalize(question).split()[:12]
        with self.lock:
            signature = tuple((a.get('key'), a.get('searchable'), tuple((n.get('id'), n.get('searchable')) for n in a.get('knowledge', []))) for a in snapshot.get('actors', []))
            if signature != self.digest:
                self.rows, self.partial, used = [], False, 0
                for actor in snapshot.get('actors', []):
                    if actor.get('searchable') is False:
                        continue
                    for note in actor.get('knowledge', []):
                        if not note.get('id') or note.get('searchable') is False:
                            continue
                        try:
                            payload = read_note(note['id'], snapshot=snapshot)
                            content = payload.get('content', '')
                            if not isinstance(content, str):
                                continue
                            content = re.sub(r'(?i)(?:nsec1[a-z0-9]{20,}|(?:sk-|ghp_|github_pat_|AIza)[a-zA-Z0-9_-]{16,})', '[REDACTED]', content)
                            content = re.sub(r'(?im)((?:api[_ -]?key|password|secret|token|authorization)\s*[:=]\s*)[^\s,;]+', r'\1[REDACTED]', content)
                            used += len(content.encode('utf-8'))
                            if used > 64_000_000:
                                self.partial = True
                                continue
                            self.rows.append({'kind':'knowledge', 'key':note['id'], 'title':note['title'],
                                              'owner':actor['id'], 'org':actor.get('org', ''),
                                              'content':content, 'normalized':normalize(content), 'truncated':payload.get('truncated', False)})
                            self.partial |= payload.get('truncated') is True
                        except (ValueError, OSError, KeyError, TypeError):
                            self.partial = True
                self.digest = signature
            matches = []
            for row in self.rows:
                words, score = None, 0
                for term in terms:
                    if term in row['normalized']:
                        score += 2
                    elif len(term) >= 5:
                        if words is None:
                            words = set(row['normalized'].split())
                        if any(len(w) >= 5 and abs(len(w)-len(term)) <= 1 and distance(term, w) <= 1 for w in words):
                            score += 1
                        else:
                            break
                    else:
                        break
                else:
                    if not terms:
                        continue
                    # Return a bounded excerpt only, never the entire note or its source path.
                    excerpt = excerpt_at_match(row['content'], terms[0])
                    matches.append({k:row[k] for k in ('kind','key','title','owner','org')} | {'text':excerpt, 'score':score})
            return {'results':sorted(matches, key=lambda r:(-r['score'],r['key']))[:100],
                    'partial':self.partial or len(matches)>100, 'scope':'authorized-export'}
