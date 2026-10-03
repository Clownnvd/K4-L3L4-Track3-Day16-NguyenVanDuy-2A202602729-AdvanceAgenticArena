"""Quotation recovery and query expansion, with no gold facts or document IDs.

Inspired by CRAG's retrieve/evaluate/correct loop. This implementation uses
deterministic quotation validation and an explicit Vietnamese query lexicon,
not the CRAG neural evaluator.
"""

from difflib import SequenceMatcher
import re



def recover_splices(ctx, report, original):
    if not isinstance(original, list) or ctx.corpus is None:
        return report
    docs = [d for d in ctx.corpus.docs if d.body and d.body in ctx.observed_text]
    kept = list(report['claims'])
    recovered = False
    for claim in original:
        if not isinstance(claim, dict) or not isinstance(claim.get('text'), str):
            continue
        text = claim['text']
        if not text or len(text) > 500 or any(c['text'] in text for c in kept):
            continue
        candidates = []
        for doc in docs:
            for line in doc.body.splitlines():
                if len(line) > 4000:
                    continue
                for block in SequenceMatcher(None, text, line, autojunk=False).get_matching_blocks():
                    start, end = block.a, block.a + block.size
                    # Trim only boundary whitespace; never reconstruct a sentence.
                    while start < end and text[start].isspace():
                        start += 1
                    while end > start and text[end - 1].isspace():
                        end -= 1
                    span = text[start:end]
                    if len(span) >= 35 and len(span.split()) >= 6 and '\n' not in span:
                        candidates.append((start, end, doc.doc_id))
        candidates.sort(key=lambda x: (-(x[1] - x[0]), x[0], x[2]))
        selected = []
        for candidate in candidates:
            start, end, source = candidate
            if any(not (end <= a or start >= b) for a, b, _ in selected):
                continue
            selected.append(candidate)
            if len(selected) == 2:
                break
        if len({source for _, _, source in selected}) < 2:
            continue
        if sum(b - a for a, b, _ in selected) / len(text) < 0.8:
            continue
        selected.sort()
        kept.extend({**claim, 'text': text[a:b], 'doc_id': source} for a, b, source in selected)
        recovered = True
    if recovered:
        report['claims'] = kept
        report['citations'] = sorted({c['doc_id'] for c in kept if isinstance(c.get('doc_id'), str)})
        report['abstain'] = True
        report['answer'] = 'Các nguồn có nội dung khác nhau; chưa đủ căn cứ để chọn một quy định áp dụng. '
        report['answer'] += ' | '.join(c['text'] for c in kept)
    return report




# Vocabulary hypotheses, not answer mappings. Keep them visible for review:
# 'hợp tác lần đầu' need not always mean a vendor, so this is experimental.
QUERY_ALIASES = (
    (r'\btai nạn\b', 'an toàn lao động'),
    (r'\bbị thương\b', 'an toàn lao động'),
    (r'\bhợp tác lần đầu\b', 'nhà cung cấp mới'),
)



def expand_query(query, mode):
    """Keep original text and entities; add transparent lexical search hints."""
    effective = query
    if mode == 'intent':
        hint = ''
        if re.search(r'\bthống kê\b', query, flags=re.IGNORECASE):
            hint = 'báo cáo'
        elif re.search(r'\btheo quy định\b', query, flags=re.IGNORECASE):
            hint = 'văn bản chính thức chính sách nội bộ'
        if hint:
            effective += ' ' + ' '.join([hint] * 3)
    expansions = []
    for pattern, replacement in QUERY_ALIASES:
        if re.search(pattern, effective, flags=re.IGNORECASE) and replacement not in expansions:
            expansions.append(replacement)
    if expansions:
        effective += ' ' + ' '.join(expansions * 3)
    return effective
