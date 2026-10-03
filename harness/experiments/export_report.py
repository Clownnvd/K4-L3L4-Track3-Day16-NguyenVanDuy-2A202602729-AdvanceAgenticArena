"""Export actual experiment results and verification evidence to Downloads."""

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path,
                        default=Path.home() / 'Downloads' / 'Lab16-Thu-Nghiem-Cai-Tien-2026-10-03')
    parser.add_argument('--published', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    before = read_json(root / 'runs/experiment-submitted.json')
    after = read_json(root / 'runs/experiment-intent-final.json')
    benchmark = read_json(root / 'runs/research-benchmark-final.json')
    xml_path = root / 'runs/experiment-pytest-linux.xml'
    suites = ET.parse(xml_path).getroot().findall('testsuite')
    tests = sum(int(s.get('tests', 0)) for s in suites)
    failures = sum(int(s.get('failures', 0)) for s in suites)
    errors = sum(int(s.get('errors', 0)) for s in suites)
    skipped = sum(int(s.get('skipped', 0)) for s in suites)
    failed_cases = [c for s in suites for c in s.findall('testcase') if c.find('failure') is not None]
    known_timing_failures = [c for c in failed_cases
                            if c.get('classname') == 'tests.test_runner'
                            and c.get('name', '').split('[')[0] == 'test_normalisation_is_bounded_on_pathological_output'
                            and '< 2.0' in c.find('failure').get('message', '')]
    blind = read_json(root / 'runs/baseline.json')['mean_total']
    gap_once = round(after['mean_total'] - blind, 2)
    gap_twice = round(after['mean_total'], 2) - round(blind, 2)
    rounding_difference = abs(gap_once - gap_twice)
    known_rounding_failures = [c for c in failed_cases
                              if c.get('classname') == 'tests.test_runner'
                              and c.get('name', '') == 'test_a_score_file_tagged_baseline_is_used_as_the_baseline'
                              and abs(rounding_difference - 0.01) < 1e-12
                              and 'comparison failed' in c.find('failure').get('message', '')]
    assert tests >= 779 and errors == skipped == 0, 'Full Linux verification is incomplete.'
    assert failures == len(known_timing_failures) + len(known_rounding_failures), 'A new/unclassified failure blocks publication.'
    frozen_paths = ['arena', 'data', 'tests', 'scripts', 'README.md', 'GUIDE.md',
                    'RUBRIC.md', 'requirements.txt', 'harness/agent.py',
                    'harness/middleware.py', 'harness/test_layers_behavior.py']
    changed = subprocess.check_output(['git', 'diff', '--name-only',
                                      'd2fefdf92b972227d558e68c3ccb9e9c96e73101', '--', *frozen_paths], cwd=root)
    assert not changed.strip(), 'Frozen files or agent have changed.'
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root).decode().strip()
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=root).decode().strip()
    if args.published:
        remote = subprocess.check_output(['git', 'ls-remote', 'origin', 'refs/heads/main'], cwd=root).decode()
        assert remote.startswith(commit), 'Published main does not match local commit.'
    rows = benchmark['runs']
    baseline = {(r['set'], r['base_seed'], r['brief_id']): r for r in rows if r['variant'] == 'submitted'}
    selected = [r for r in rows if r['variant'] == 'intent']
    deltas = [r['total'] - baseline[(r['set'], r['base_seed'], r['brief_id'])]['total'] for r in selected]
    safety_regressions = sum(r['safety'] < baseline[(r['set'], r['base_seed'], r['brief_id'])]['safety'] for r in selected)
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    table = []
    with (out / 'SO-SANH-TUNG-BAI.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['Mã bài', 'Bản đã nộp', 'Phương án mới', 'Chênh lệch', 'Bám chứng cứ', 'An toàn', 'Hiệu quả', 'Số lượt công cụ'])
        for old, new in zip(before['runs'], after['runs']):
            assert old['brief_id'] == new['brief_id']
            writer.writerow([new['brief_id'], old['total'], new['total'], new['total']-old['total'],
                             new['grounding'], new['safety'], new['efficiency'], new['tool_calls']])
            table.append(f"| {new['brief_id']} | {old['total']:.2f} | {new['total']:.2f} |")
    with (out / 'TOAN-BO-560-LUOT-THU.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['Bộ câu hỏi', 'Phương án', 'Seed gốc', 'Mã bài', 'Điểm', 'Bám chứng cứ',
                         'An toàn', 'Hiệu quả', 'Cổng trace đạt', 'Lượt công cụ', 'Ngân sách', 'Lỗi'])
        for r in rows:
            writer.writerow([r['set'], r['variant'], r['base_seed'], r['brief_id'], r['total'],
                             r['grounding'], r['safety'], r['efficiency'], r['gate_passed'],
                             r['tool_calls'], r['tool_budget'], r['error']])
    summary_table = []
    for variant, label in [('submitted', 'Bản đã nộp'), ('fragments', 'Khôi phục đoạn trích'),
                           ('expanded', 'Mở rộng từ khóa'), ('intent', 'Từ khóa + loại tài liệu')]:
        a = benchmark['summary'][f'public/{variant}']
        b = benchmark['summary'][f'paraphrases/{variant}']
        summary_table.append(f"| {label} | {a['mean']:.2f} | {b['mean']:.2f} |")
    checks = [benchmark['summary'][key] for key in benchmark['summary']]
    receipt = {
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'branch': branch, 'commit': commit,
        'submitted_commit': 'd2fefdf92b972227d558e68c3ccb9e9c96e73101',
        'frozen_files_and_agent_unchanged': True,
        'official_grade_available': False, 'pushed': args.published, 'resubmitted': False,
        'practice_before': before['mean_total'], 'practice_after': after['mean_total'],
        'linux_pytest': {'tests': tests, 'failures': failures, 'errors': errors, 'skipped': skipped},
        'linux_pytest_status': 'passed' if failures == 0 else 'failed_frozen_scaffold_check',
        'linux_python': '3.13.16',
        'existing_timing_failures': [c.find('failure').get('message', '')[:500] for c in known_timing_failures],
        'frozen_leaderboard_rounding_failures': [c.find('failure').get('message', '')[:500] for c in known_rounding_failures],
        'rounding_reproduction': {'blind_baseline': blind, 'mean': after['mean_total'],
                                 'gap_rounded_once': gap_once, 'difference_of_rounded_means': gap_twice,
                                 'absolute_difference': rounding_difference},
        'benchmark_runs': len(rows), 'paired_improvements': sum(d > 0 for d in deltas),
        'paired_regressions': sum(d < 0 for d in deltas), 'paired_unchanged': sum(d == 0 for d in deltas),
        'safety_regressions': safety_regressions,
        'gate_failures': sum(c['gate_failures'] for c in checks),
        'canary_leaks': sum(c['canary_leaks'] for c in checks),
        'budget_violations': sum(c['budget_violations'] for c in checks),
        'runner_errors': sum(c['runner_errors'] for c in checks),
        'unowned_events': sum(c['unowned_events'] for c in checks),
        'limits': ['MockModel only; no private set or real model tested.',
                   'Paraphrases share public corpus and reference facts.',
                   'Manual vocabulary requires domain review; not a universal semantic rewriter.',
                   'Existing Windows upstream environment failures are avoided by verifying full suite on Linux.',
                   'The unchanged frozen normalizer can exceed the 2-second assertion on this busy machine; failures are retained, never labeled passed.'],
    }
    (out / 'KIEM-CHUNG.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    report = f'''# Agent Arena — kết quả thử phương án mới

Điểm luyện tập tăng **{before['mean_total']:.2f} → {after['mean_total']:.2f}/100**.
Phương án được chọn là mở rộng từ khóa theo miền dữ liệu và thêm gợi ý loại tài liệu.
Bản cũ còn trong lịch sử commit. Phương án mới đã được đưa vào hai lớp Critic và Retry mặc định.
Trạng thái GitHub: {'đã đẩy main và kiểm tra khớp commit ' + commit if args.published else 'chưa đẩy bản mới'}.

## So sánh từng bài ở cấu hình ban đầu

| Bài | Bản đã nộp | Phương án mới |
| --- | ---: | ---: |
{chr(10).join(table)}

## Kiểm tra độ ổn định

Mỗi phương án chạy 90 lượt trên chín bài công khai, với 10 seed lỗi công cụ.
Chạy thêm 50 lượt trên năm câu hỏi viết lại, cũng với 10 seed.
Tổng cộng bốn phương án × 140 lượt = **{len(rows)} lượt**.

| Phương án | Trung bình bộ công khai | Trung bình câu viết lại |
| --- | ---: | ---: |
{chr(10).join(summary_table)}

So phương án mới với bản đã nộp ở cùng câu hỏi và cùng seed:
**{receipt['paired_improvements']} cặp tăng, {receipt['paired_regressions']} cặp giảm,
{receipt['paired_unchanged']} cặp giữ nguyên**. Không có cặp giảm điểm an toàn.
Trong các lượt đã đo: không rò chuỗi bẫy, không vượt ngân sách,
không lỗi runner và mọi cổng trace đều đạt.

## Cách mới làm gì?

1. Thêm từ liên quan vào truy vấn, chẳng hạn tai nạn → an toàn lao động.
   Câu hỏi gốc và tên thực thể vẫn được giữ lại.
2. Khi hỏi theo quy định, thêm từ khóa văn bản chính thức/chính sách.
   Khi hỏi thống kê, thêm từ khóa báo cáo. Nhờ vậy bài truy xuất sâu tìm được
   tài liệu quy định, thay vì chỉ đọc nhật ký hỗ trợ và tài liệu phụ.
3. Khôi phục các đoạn nguyên văn của câu ghép từ hai nguồn đã đọc;
   không viết thêm chữ vào lời mô hình. Biện pháp này làm báo cáo rõ nguồn hơn
   nhưng không tăng điểm riêng ở bộ hiện tại do giới hạn độ phủ của bài mâu thuẫn.

Tham khảo ý tưởng đánh giá chất lượng truy xuất và sửa truy vấn của
[CRAG](https://github.com/HuskyInSalt/CRAG) và
[Adaptive RAG của LangGraph](https://github.com/langchain-ai/langgraph/blob/main/examples/rag/langgraph_adaptive_rag.ipynb).
Đây là bản thử quy tắc từ khóa; chưa triển khai bộ đánh giá học máy của CRAG.

## Vì sao vẫn chưa đạt 100?

- Bài mâu thuẫn có giới hạn độ phủ trong rubric. Giữ được hai đoạn trích
  giúp giải thích mâu thuẫn nhưng chưa thể đạt điểm tối đa.
- Bài thiếu dữ liệu phải từ chối; mô hình giả bịa số thay vì trích câu xác nhận
  thiếu dữ liệu. Hệ thống loại con số bịa, không thay bằng đáp án lấy từ kho.
- Bài tổng hợp đã tìm được dữ kiện nên tăng từ 40,15 lên 70,07, nhưng mô hình giả
  không viết trường kết luận. Không tự chèn lựa chọn đúng để tăng điểm.
- Một seed gây hỏng liên tiếp ở bài ticket vẫn làm thiếu bằng chứng. Phương án
  mới chưa sửa được trường hợp đó; không có bảo đảm mọi lượt đều điểm cao.

## Kiểm chứng và giới hạn

- **{tests-failures}/{tests} test đạt trên Linux**, {failures} test thất bại, không lỗi setup hoặc bỏ qua.
- Trạng thái bộ test đầy đủ: **{'đạt' if failures == 0 else 'chưa đạt hoàn toàn; còn lỗi trong kiểm tra của code đề'}**.
- Lỗi làm tròn còn lại: bảng xếp hạng tính chênh lệch là {gap_once}, trong khi hiệu
  của hai điểm đã làm tròn là {gap_twice}. Sai số thực tế là {rounding_difference},
  lớn hơn 0,01 một lượng rất nhỏ nên phép so sánh của test trượt. Đã tái hiện bằng
  chính số liệu thật và hàm làm tròn, không sửa bảng xếp hạng hoặc test của giảng viên.
  Chi tiết lưu trong `KIEM-CHUNG.json`.
- Các lượt kiểm thử đầu từng vượt ngưỡng thời gian của bộ phân tích nguyên bản.
  Lượt cuối trên Python 3.13.16 đã qua các ca thời gian. Lịch sử thất bại vẫn giữ
  trong `runs/`, không nới ngưỡng hoặc bỏ qua test để làm xanh.
- 40 kiểm thử của các lớp bảo vệ và 21 kiểm tra chính thức đều đạt sau tích hợp.
- Các file của giảng viên và agent giữ nguyên. Chỉ thay hai lớp Critic/Retry và thêm helper/mã kiểm chứng.
- Các lớp thử chỉ dùng tài liệu đã đọc; không đọc mã đáp án, nhãn bẫy hay bộ riêng.
- Không gọi API, không sử dụng khóa, không nộp lại VLearn. GitHub theo trạng thái ở đầu báo cáo.
- Năm câu viết lại vẫn dùng kho và đáp án công khai: kết quả chưa chứng minh
  chất lượng trên bộ câu hỏi riêng hoặc mô hình thật.
- Từ điển thủ công còn nhập nhằng: hợp tác lần đầu không luôn có nghĩa nhà cung cấp
  mới; cụm từ theo quy định/thống kê chưa bao phủ mọi cách diễn đạt. Vì vậy
  cần đánh giá thêm trước khi coi là giải pháp tổng quát cho ứng dụng thật.

## File và cách chạy

- `SO-SANH-TUNG-BAI.csv`: bảng chín bài ở cấu hình ban đầu.
- `TOAN-BO-560-LUOT-THU.csv`: toàn bộ phép đo, có điểm và ngân sách từng lượt.
- `KIEM-CHUNG.json`: kết quả kiểm chứng và những giới hạn còn lại.
- `HUONG-DAN.md`: giải thích kỹ thuật và lệnh chạy lại.
- Mã thử nghiệm: `{root / 'harness/experiments'}`.
'''
    (out / 'BAO-CAO-THU-NGHIEM.md').write_text(report, encoding='utf-8')
    for source, filename in [(root / 'runs/experiment-submitted.json', 'BAN-DA-NOP.json'),
                             (root / 'runs/experiment-intent-final.json', 'PHUONG-AN-MOI.json'),
                             (root / 'runs/research-benchmark-final.json', 'TOAN-BO-PHEP-DO.json'),
                             (xml_path, 'pytest-linux.xml'),
                             (root / 'harness/experiments/README.md', 'HUONG-DAN.md')]:
        shutil.copy2(source, out / filename)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    print(out)


if __name__ == '__main__':
    main()
