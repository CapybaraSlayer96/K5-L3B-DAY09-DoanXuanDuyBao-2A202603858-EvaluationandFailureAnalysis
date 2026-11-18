# Judge audit

Chạy (trong `src/`): `python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 10` và `python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 12`.
Lớp dương = FAIL (judge có nhiệm vụ tìm lỗi). Backend: replay, tức verdict của judge lưu sẵn trong CSV.

| Tiêu chí | n | κ | Precision | Recall | Confusion (tp/fp/fn/tn) | Tỉ lệ FAIL quan sát → Rogan-Gladen | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | 24 / 4 / 6 / 66 | 0.28 → 0.30 | **PASS** | dùng được (theo dõi, không blocking) |
| helpful | 100 | 0.375 | 1.000 | 0.300 | 9 / 0 / 21 / 70 | 0.09 → 0.30 | **FAIL** (κ, R) | loại, không dùng làm gate |

Vì sao helpful không được làm gate: recall 0.3, tức judge bỏ sót 21/30 reply mà người chấm đánh FAIL. Nếu đặt judge này làm cổng, 70% reply tệ sẽ được merge. Precision 1.0 không cứu được: một judge gần như lúc nào cũng nói PASS thì không bao giờ báo nhầm, nhưng cũng không bắt được gì. Tỉ lệ FAIL quan sát 9% cũng sai lệch mạnh so với tỉ lệ thật: Rogan-Gladen hiệu chỉnh ra 30%, đúng bằng tỉ lệ người chấm (30/100).
18/21 ca bỏ sót là reply **nói sai số tiền so với ledger**, theo cột `note` "ledger ghi …". Judge chỉ đọc văn bản, không thấy ledger, nên không thể chấm tiêu chí này. Đây là việc của code grader `reply_matches_ledger` (FM-08). Đúng như quy tắc: tiền luôn chấm bằng code.

## Case audit thủ công (15 bất đồng: 10 tone + 5 helpful)

| # | Case | Judge nói | Người nói | Ai đúng? | Hành động sửa rubric / nhãn |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha…" | PASS | FAIL | Người | Rubric tone thêm: xưng "em/anh", tiểu từ "nha/nhé" với khách khiếu nại là FAIL; thêm câu này làm few-shot âm. |
| 2 | H-017 "Dạ, bạn ơi LogiX đã hoàn 25.000đ…" | PASS | FAIL | Người | Quy định xưng hô chuẩn "anh/chị"; xưng "bạn" là FAIL. |
| 3 | H-029 "…Hệ thống đang xử lý, không cần nhắn thêm." | PASS | FAIL | Người | Judge chỉ thấy "Dạ, vui lòng". Thêm tiêu chí "không dùng câu mệnh lệnh / cấm khách liên hệ". |
| 4 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Judge phạt vì thiếu xin lỗi. Rubric ghi rõ: kết quả tích cực, ngắn gọn, lễ phép thì không bắt buộc xin lỗi. |
| 5 | H-051 "Dạ, LogiX đã refund 90.000đ…" | FAIL | PASS | Người | CS LogiX cho phép từ "refund". Thêm whitelist thuật ngữ tiếng Anh được phép. |
| 6 | H-063 "…đã hoàn 20.000đ và sẽ hoàn thêm…" | PASS | FAIL | Người | Đây là lỗi nội dung (hứa ngoài kết quả hệ thống), không phải lỗi giọng. Tách khỏi rubric tone, chuyển sang code grader cho cam kết/số tiền (cùng họ FM-08). |
| 7 | H-070 "…đã hoàn 90.000đ cho đơn O-909 ạ 😂😂" | PASS | FAIL | Người | Thêm: emoji trong phản hồi khiếu nại là FAIL. |
| 8 | H-081 "Dạ, đơn O-107 chưa đủ điều kiện hoàn…" | FAIL | PASS | **Judge** | Ghi chú CSV: người đọc nhầm ticket. Sửa nhãn người thành FAIL; nhãn đã sửa thì không tính vào tập held-out. |
| 9 | H-088 "Dạ, dạ, LogiX đã hoàn 40.000đ…" | FAIL | PASS | Người (lỗi gõ nhẹ) | Rubric: lặp từ do gõ là lỗi chính tả, không phải lỗi giọng. Giữ PASS cho tone, ghi nhận ở kiểm tra chính tả riêng. |
| 10 | H-094 "Da, LogiX da hoan 40.000đ…" (mất dấu) | PASS | FAIL | Người | Thêm: tiếng Việt không dấu / dịch máy là FAIL. |
| 11 | HL-015 "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." (ledger 40.000) | PASS | FAIL | Người | Judge không thấy ledger. Bỏ "đúng số tiền" khỏi rubric helpful, giao cho `reply_matches_ledger`. |
| 12 | HL-020 "…đã hoàn 90.000đ cho đơn O-303" (ledger 120.000) | PASS | FAIL | Người | Như #11. |
| 13 | HL-016 xin lỗi dài 3 câu + "đã hoàn 55.000đ" (ledger 35.000) | PASS | FAIL | Người | Hai lỗi: số sai (code) và lời xin lỗi lặp làm loãng thông tin. Rubric helpful thêm "thông tin chính (kết quả, số tiền, thời gian) nằm trong câu đầu; không lặp lời xin lỗi". |
| 14 | HL-047 "Ok bạn, đơn O-515 xử lý rồi nhé." | PASS | FAIL | Người | Không nêu kết quả hay số tiền. Rubric helpful: phải nêu trạng thái (đã hoàn / từ chối / cần thêm thông tin) và bước tiếp theo. |
| 15 | HL-091 "Ok bạn, đơn O-233 xử lý rồi nhé." | PASS | FAIL | Người | Như #14; thêm vào few-shot âm. |

## Kết luận
- **tone_ok**: đạt floors, dùng được để theo dõi chất lượng giọng văn. Không đặt blocking: 6 FN và 4 FP trên 100 câu vẫn đủ làm đỏ CI một cách ngẫu nhiên. Rubric sửa theo #1–#10 rồi phải calibrate lại trên nhãn mới.
- **helpful**: bị loại (κ 0.375 < 0.6, R 0.3 < 0.7, ma trận 9/0/21/70). Phần "đúng số tiền" chuyển sang code (`reply_matches_ledger`, blocking). Phần còn lại (nêu kết quả, không lan man) viết lại rubric theo #13–#15 rồi calibrate lại.
- Rủi ro còn lại: judge chỉ được kiểm trên dữ liệu replay đã công khai, và chính tôi đã đọc các bất đồng để sửa rubric. Vì vậy số liệu ở đây là số train, không phải held-out. Cần nhãn người mới (tập chưa ai xem) mới có held-out thật. Một nhãn người đã sai (#8), nên nhãn người cũng cần người thứ hai kiểm.
