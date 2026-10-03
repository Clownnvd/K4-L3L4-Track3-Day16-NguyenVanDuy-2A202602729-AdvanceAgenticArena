from types import SimpleNamespace

from arena.tools import ToolResult
from harness.experiments.evidence_recovery import FragmentCritic, QueryExpansionRetry, IntentRetrievalRetry


def context(bodies=(), calls=0, limit=8):
    docs = [SimpleNamespace(doc_id=f'source-{i}', body=body) for i, body in enumerate(bodies)]
    return SimpleNamespace(corpus=SimpleNamespace(docs=docs), observed_text='\n'.join(bodies),
                           state={}, tools=SimpleNamespace(calls=calls), max_tool_calls=limit)


def test_conflict_with_repeated_conjunction_keeps_only_original_fragments():
    first = 'Đội thiết kế được làm việc tại nhà tối đa 4 ngày mỗi tuần và cần báo trước.'
    second = 'Toàn bộ nhân viên chỉ được làm việc tại nhà tối đa 1 ngày mỗi tuần và cần giám đốc phê duyệt.'
    left = first[:first.index(' và')]
    right = second[second.index('chỉ được'):]
    fused = left + ' và và ' + right
    result = FragmentCritic().after_agent(context([first, second]),
                                         {'claims': [{'text': fused, 'doc_id': 'wrong'}], 'answer': fused})
    assert result['abstain']
    assert len(result['claims']) == 2
    assert all(claim['text'] in fused for claim in result['claims'])
    assert result['claims'][0]['text'] in first
    assert result['claims'][1]['text'] in second
    assert fused not in result['answer']


def test_partial_overlap_never_repairs_invented_number():
    body = 'Báo cáo chưa có dữ liệu về số sự cố vận hành tháng này.'
    claim = {'text': 'Báo cáo xác nhận số sự cố vận hành tháng này là 8765.', 'doc_id': 'source-0'}
    result = FragmentCritic().after_agent(context([body]), {'claims': [claim]})
    assert result['abstain'] and result['claims'] == []


def test_fragment_recovery_rejects_unseen_source_and_cross_line_match():
    ctx = context(['Một quy định đáng tin cậy với nhiều nội dung.\nDòng kế tiếp có số liệu 12.'])
    ctx.corpus.docs.append(SimpleNamespace(doc_id='unseen', body='Mức chi trả tối đa là 55 triệu trong mỗi kỳ đánh giá.'))
    report = {'claims': [{'text': 'Mức chi trả tối đa là 55 triệu trong mỗi kỳ đánh giá.', 'doc_id': 'unseen'},
                         {'text': 'nội dung.\nDòng kế tiếp', 'doc_id': 'source-0'}]}
    assert FragmentCritic().after_agent(ctx, report)['claims'] == []


def test_query_expansion_preserves_original_and_never_mutates_arguments():
    layer, ctx, seen = QueryExpansionRetry(), context(), []
    args = {'query': 'Phòng chống tai nạn trong ca trực?', 'k': 5}
    def call(name, payload):
        ctx.tools.calls += 1
        seen.append((name, payload))
        return ToolResult(True, '[]')
    layer.wrap_tool_call(ctx, call, 'search', args)
    assert seen[0][1]['query'].startswith(args['query'])
    assert 'an toàn lao động' in seen[0][1]['query']
    assert args == {'query': 'Phòng chống tai nạn trong ca trực?', 'k': 5}
    assert ctx.tools.calls == 1


def test_unrelated_search_and_fetch_are_unchanged():
    layer, ctx, seen = QueryExpansionRetry(), context(), []
    def call(name, payload):
        ctx.tools.calls += 1
        seen.append((name, payload))
        return ToolResult(True, 'complete')
    layer.wrap_tool_call(ctx, call, 'search', {'query': 'Lịch nghỉ phép', 'k': 5})
    layer.wrap_tool_call(ctx, call, 'fetch_doc', {'doc_id': 'any'})
    assert seen == [('search', {'query': 'Lịch nghỉ phép', 'k': 5}), ('fetch_doc', {'doc_id': 'any'})]


def test_expanded_retry_uses_same_arguments_and_reserves_submit():
    layer, ctx, seen = QueryExpansionRetry(), context(calls=5), []
    def call(name, payload):
        ctx.tools.calls += 1
        seen.append((name, payload))
        return ToolResult(False, '', 'timeout: test')
    layer.wrap_tool_call(ctx, call, 'search', {'query': 'tai nạn lao động', 'k': 5})
    assert ctx.tools.calls == 7
    assert len(seen) == 2 and seen[0] == seen[1]


def test_recovery_never_turns_two_sentences_from_one_source_into_conflict():
    first = 'Nhân viên có thể đăng ký lịch làm việc linh hoạt trong mỗi tháng.'
    second = 'Người quản lý xét duyệt yêu cầu trong vòng 2 ngày làm việc.'
    fused = first + ' và và ' + second
    result = FragmentCritic().after_agent(context([first+'\n'+second]), {'claims': [{'text': fused}]})
    assert result['claims'] == []


def test_long_fabrication_is_not_processed_as_quotation_recovery():
    body = 'Một tài liệu có nhiều thông tin cần kiểm tra và có số liệu 23.'
    result = FragmentCritic().after_agent(context([body]), {'claims': [{'text': body * 1000 + 'invented'}]})
    assert result['claims'] == []


def test_intent_hints_keep_entity_and_limit_and_do_not_change_fetch():
    ctx, seen = context(), []
    def call(name, payload):
        ctx.tools.calls += 1
        seen.append((name, payload))
        return ToolResult(True, '[]')
    layer = IntentRetrievalRetry()
    layer.wrap_tool_call(ctx, call, 'search', {'query': 'Theo quy định, sự cố tại chi nhánh Nam cần báo trong bao lâu?', 'k': 3})
    assert 'chi nhánh Nam' in seen[0][1]['query'] and seen[0][1]['k'] == 3
    assert 'văn bản chính thức' in seen[0][1]['query']
    layer.wrap_tool_call(ctx, call, 'fetch_doc', {'doc_id': 'requested'})
    assert seen[1] == ('fetch_doc', {'doc_id': 'requested'})


def test_submitted_variant_keeps_all_original_classes():
    from harness.experiments.run_comparison import build_variant
    from scripts.run_practice import STACK_ORDER, _student_layers
    submitted = build_variant(set(STACK_ORDER), 'submitted')
    assert [type(layer) for layer in submitted] == [type(layer) for layer in _student_layers(set(STACK_ORDER))]
    assert not next(layer for layer in submitted if layer.name == 'critic').recover_fragments
    assert next(layer for layer in submitted if layer.name == 'retry').query_mode == 'none'


def test_default_stack_enables_the_selected_variant():
    from harness.layers.critic import Critic
    from harness.layers.retry import Retry
    assert Critic().recover_fragments and Retry().query_mode == 'intent'
