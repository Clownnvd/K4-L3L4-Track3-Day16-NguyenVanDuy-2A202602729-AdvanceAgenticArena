from types import SimpleNamespace

from arena.corpus import INJECTION_CANARY
from arena.model import FINALIZE_SENTINEL
from arena.tools import ToolResult
from harness.layers.budget_policy import BudgetPolicy
from harness.layers.citation_checker import CitationChecker
from harness.layers.critic import Critic
from harness.layers.injection_guard import BLOCK_END, BLOCK_START, InjectionGuard
from harness.layers.retry import Retry


def context(observed='', docs=(), calls=0, limit=8):
    corpus = SimpleNamespace(docs=list(docs), get=lambda identifier: next((d for d in docs if d.doc_id == identifier), None))
    return SimpleNamespace(observed_text=observed, corpus=corpus, state={}, max_tool_calls=limit,
                           tools=SimpleNamespace(calls=calls))


def document(identifier, body):
    return SimpleNamespace(doc_id=identifier, body=body)


def test_critic_removes_fabrication_without_altering_quotation():
    quote = 'Nội thành giao hàng trong 2 ngày.'
    ctx = context(quote, [document('source', quote)])
    report = {'claims': [{'text': quote, 'doc_id': 'source'}, {'text': 'Mức thu nhập là 99 triệu.', 'doc_id': 'source'}]}
    result = Critic().after_agent(ctx, report)
    assert result['claims'] == [{'text': quote, 'doc_id': 'source'}]
    assert result['citations'] == ['source']


def test_critic_abstains_on_empty_evidence():
    result = Critic().after_agent(context(), {'claims': [{'text': 'Không có nguồn đỡ câu này', 'doc_id': 'x'}]})
    assert result['abstain'] and result['claims'] == []
    assert result['answer'] and result['citations'] == []


def test_critic_splits_only_model_substrings_from_distinct_observed_sources():
    left, right = 'Phòng A cho phép 2 ngày.', 'Phòng B quy định 4 ngày.'
    docs = [document('left', left), document('right', right)]
    text = left + ' và ' + right
    result = Critic().after_agent(context(left+'\n'+right, docs), {'claims': [{'text': text, 'doc_id': 'left'}]})
    assert result['abstain']
    assert [c['text'] for c in result['claims']] == [left, right]
    assert all(c['text'] in text for c in result['claims'])


def test_citation_changes_only_source_and_never_uses_unseen_document():
    quoted = 'Quy trình phải xác nhận trước khi thanh toán.'
    docs = [document('wrong', 'Chính sách khác.'), document('right', quoted)]
    report = {'claims': [{'text': quoted, 'doc_id': 'wrong'}]}
    result = CitationChecker().after_agent(context(quoted, docs), report)
    assert result['claims'][0] == {'text': quoted, 'doc_id': 'right'}
    unobserved = CitationChecker().after_agent(context('', docs), {'claims': [{'text': quoted, 'doc_id': 'wrong'}]})
    assert unobserved['claims'][0]['doc_id'] == 'wrong'


def test_citation_does_not_accept_quote_across_lines():
    docs = [document('first', 'Dòng một của tài liệu.\nDòng hai của tài liệu.')]
    claim = {'text': 'tài liệu.\nDòng hai', 'doc_id': 'bad'}
    result = CitationChecker().after_agent(context(docs[0].body, docs), {'claims': [claim]})
    assert result['claims'][0]['doc_id'] == 'bad'


def test_budget_reserves_submit_and_does_not_mutate_history():
    layer, ctx = BudgetPolicy(), context(calls=7)
    messages = [{'role': 'user', 'content': 'brief'}]
    result = layer.before_model(ctx, messages)
    assert len(messages) == 1 and FINALIZE_SENTINEL in result[-1]['content']
    calls = []
    response = layer.wrap_tool_call(ctx, lambda *a: calls.append(a), 'search', {})
    assert not calls and not response.ok
    assert layer.before_model(context(limit=None), messages) == messages


def test_retry_recovers_degraded_success_but_stops_before_submit():
    ctx, calls = context(calls=5), []
    def call(name, args):
        ctx.tools.calls += 1
        calls.append((name, args))
        return ToolResult(True, '[TRUNCATED: lost text]' if len(calls) == 1 else 'complete')
    result = Retry().wrap_tool_call(ctx, call, 'fetch_doc', {'doc_id': 'x'})
    assert result.content == 'complete' and len(calls) == 2 and calls[0] == calls[1]
    ctx.tools.calls = 6
    calls.clear()
    result = Retry().wrap_tool_call(ctx, call, 'fetch_doc', {'doc_id': 'x'})
    assert ctx.tools.calls == 7 and len(calls) == 1 and 'TRUNCATED' in result.content


def test_injection_removes_complete_multiple_and_open_blocks():
    text = 'safe\n'+BLOCK_START+INJECTION_CANARY+BLOCK_END+'\nnormal\n'+BLOCK_START+INJECTION_CANARY
    result = InjectionGuard().wrap_tool_call(context(), lambda *a: ToolResult(True, text), 'fetch_doc', {})
    assert INJECTION_CANARY not in result.content
    assert 'safe' in result.content and 'normal' in result.content
    assert 'loại bỏ' in result.content


def test_final_injection_sweep_does_not_rewrite_claim_text():
    quote = 'Đây là một dòng trích dẫn hợp lệ.'
    report = {'answer': 'text '+INJECTION_CANARY, 'claims': [{'text': quote, 'doc_id': 'a'}]}
    result = InjectionGuard().after_agent(context(), report)
    assert INJECTION_CANARY not in result['answer']
    assert result['claims'][0]['text'] == quote


def test_critic_removes_a_quote_across_two_lines():
    body = 'Dòng đầu của tài liệu.\nDòng thứ hai có một thông tin khác.'
    claim = {'text': 'tài liệu.\nDòng thứ hai', 'doc_id': 'source'}
    result = Critic().after_agent(context(body, [document('source', body)]), {'claims': [claim]})
    assert result['abstain'] and not result['claims']


def test_injection_canary_in_claim_is_dropped_not_rewritten():
    clean = {'text': 'Một câu có bằng chứng đầy đủ.', 'doc_id': 'clean'}
    poisoned = {'text': 'Quoted ' + INJECTION_CANARY, 'doc_id': 'poisoned'}
    result = InjectionGuard().after_agent(context(), {'answer': 'ok', 'claims': [clean, poisoned],
                                                     'citations': ['clean', 'poisoned']})
    assert result['claims'] == [clean] and result['citations'] == ['clean']
    assert poisoned['text'] == 'Quoted ' + INJECTION_CANARY
