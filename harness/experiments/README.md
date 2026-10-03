# Thử nghiệm cải thiện Agent Arena

Thử nghiệm được thực hiện trên nhánh `experiment/evidence-recovery` trước khi
người dùng yêu cầu đưa phương án tốt nhất lên GitHub. Bản ban đầu còn trong
commit `d2fefdf92b972227d558e68c3ccb9e9c96e73101`.
Phương án được chọn đã tích hợp vào Critic và Retry mặc định; các file đóng băng,
agent, parser và ba lớp còn lại giữ nguyên. Chưa nộp lại VLearn.

## Phương án thử

1. **Khôi phục đoạn trích:** tìm tối đa hai đoạn nguyên văn của câu ghép, chỉ từ
   tài liệu đã được đọc đầy đủ. Mỗi đoạn đủ dài, thuộc hai nguồn khác nhau và
   tổng độ phủ ít nhất 80%. Không bổ sung, sửa chữ hoặc lấy câu mới từ tài liệu.
   Câu trả lời thông báo chưa đủ căn cứ chọn một quy định áp dụng. Đây là biện
   pháp thận trọng với câu ghép, chưa phải bộ phát hiện mâu thuẫn về ngữ nghĩa.
2. **Mở rộng từ khóa:** thêm từ liên quan, giữ câu hỏi gốc, tên thực thể và k.
   Từ điển được khai báo rõ trong `harness/layers/evidence_recovery.py`. Không ánh xạ
   mã câu hỏi, mã tài liệu, con số đáp án hoặc nhãn bẫy.
3. **Ưu tiên loại tài liệu:** câu hỏi theo quy định được thêm từ khóa văn bản
   chính thức/chính sách; câu hỏi thống kê được thêm từ khóa báo cáo. Đây là
   gợi ý cho tìm kiếm từ khóa, **không** chứng minh nguồn nào đáng tin hơn.

Tham khảo cách kiểm tra chất lượng truy xuất và sửa truy vấn trong
[CRAG của tác giả](https://github.com/HuskyInSalt/CRAG) và
[ví dụ Adaptive RAG của LangGraph](https://github.com/langchain-ai/langgraph/blob/main/examples/rag/langgraph_adaptive_rag.ipynb).
Phần thử nghiệm chỉ áp dụng ý tưởng; không cài mô hình CRAG, không dùng mô hình
chấm điểm hoặc tìm kiếm web trong lúc agent chạy.

## Chạy lại

Tại thư mục gốc repo, PowerShell:

```powershell
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe -m pytest -q harness/experiments/test_evidence_recovery.py
.\.venv\Scripts\python.exe -m harness.experiments.run_comparison --variant intent --strict --out runs/experiment-intent-final.json
.\.venv\Scripts\python.exe -m harness.experiments.benchmark_variants --out runs/research-benchmark-final.json
```

Các biến thể: `submitted` (bản đã nộp), `fragments` (khôi phục đoạn trích),
`expanded` (mở rộng từ khóa), `combined` (hai cách trên), `intent` (kèm loại tài liệu).
Chạy `python scripts/run_practice.py` sử dụng phương án mới được chọn.
Biến thể `submitted` đặt `Critic(recover_fragments=False)` và `Retry(query_mode='none')`
để chạy lại hành vi bản ban đầu; đã đối chiếu điểm 81,7116 với commit cũ.
Các phép đo gọi cùng runner, mô hình giả, công cụ và bộ chấm của đề; không sửa
file của giảng viên. Trace lưu trong `runs/experiment-traces/`, điểm lưu trong
`runs/`. Script so sánh chỉ cho phép `--model mock` để tránh gọi API ngoài ý muốn.

## Hợp đồng kiểm chứng

- Các file đã đóng băng, agent và ba lớp không liên quan giữ nguyên.
- Mọi claim giữ nguyên hoặc là đoạn cắt liên tục của chữ mô hình đã viết.
- Không trích nguồn chưa đọc, không sửa trace, không đọc nhãn hoặc đáp án trong layer.
- Không vượt ngân sách công cụ; retry giữ cùng tham số và dành một lượt nộp.
- Đo cùng seed, cùng câu hỏi và cùng kho dữ liệu cho từng biến thể.
- Kiểm tra cổng trace, chuỗi bẫy, lỗi runner và sự kiện không do runner ghi.
- Chạy test lớp, kiểm tra chính thức và toàn bộ test trên Linux.

Trong lúc kiểm chứng, phép thử hiệu năng của bộ phân tích đóng băng đã vượt
ngưỡng 2 giây (lượt đầu 2,39 giây; gọi trực tiếp bản nguyên gốc trên Windows
cũng mất 4,26 giây). Đây là hàm của giảng viên, không phụ thuộc hai lớp thay đổi.
Mọi kết quả thất bại vẫn được lưu trong `runs/`; không sửa hàm, không nới ngưỡng,
không gọi toàn bộ suite xanh nếu vẫn còn thất bại. Đọc trạng thái thực tế trong
báo cáo và `KIEM-CHUNG.json`; thay đổi mới chỉ được coi là đạt các kiểm tra
trong phạm vi khi test lớp, cổng chính thức và phép đo qua runner đều đạt.

Lượt đầy đủ cuối dùng Python 3.13.16 đã qua các ca thời gian, nhưng còn phép thử
bảng xếp hạng: điểm 91,6871 và mốc 24,2747 cho chênh lệch làm tròn 67,41;
hiệu của hai giá trị đã làm tròn là 67,42. Sai khác ở số thực bằng
0,010000000000005116 nên vượt dung sai 0,01. Không sửa script/test đóng băng.
Bộ đầy đủ đạt 778/779 test; các kiểm tra trong phạm vi lớp bảo vệ đạt 40/40,
kiểm tra chính thức đạt 21/21. Báo cáo giữ rõ sự khác nhau này.

Test về câu ghép có liên từ lặp đã được chạy với lớp Critic cũ và thất bại vì
mất hai đoạn trích; lớp mới qua test. Các test khác chặn việc vá số liệu bịa,
nguồn chưa đọc, đoạn vắt qua hai dòng, nhầm hai đoạn cùng nguồn thành mâu thuẫn,
đầu vào quá dài và việc thay thế lớp mặc định ngoài ý muốn.

## Giới hạn cần giữ rõ

- Các từ đồng nghĩa đang được chọn theo miền dữ liệu công khai. `hợp tác lần đầu`
  không nhất thiết là `nhà cung cấp mới`; cần rà soát từ điển hoặc dùng mô hình
  viết lại truy vấn đã được đánh giá trước khi đưa vào ứng dụng thật.
- Cụm từ `theo quy định` và `thống kê` chưa bao phủ mọi cách diễn đạt.
- Năm câu viết lại vẫn dùng cùng kho và đáp án công khai. Không phải bộ kiểm tra riêng.
- Mô hình giả không tạo trường kết luận trong FINAL. Thử nghiệm không tự chèn
  đáp án lựa chọn từ đề để nâng điểm; bài tổng hợp vẫn thiếu phần kết luận.
- Khôi phục đoạn trích làm câu trả lời rõ nguồn hơn nhưng không vượt được
  giới hạn độ phủ của bài mâu thuẫn trong rubric.
- Không cam kết điểm chính thức hoặc đạt 100. Chỉ cập nhật GitHub sau khi
  người dùng đã yêu cầu và kiểm chứng phương án mới.
