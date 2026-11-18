# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace, ledger so với nhãn, và lý do của grader Lab 8.

## Case: `seeded_regression C-002@11`

Output lệnh trên (rút gọn):
```
== seeded_regression C-002@11  lab8 grader: FAIL (status resolved != denied)
   1 handoff            {... "claim_id": "C-002", "facts": {} ...}
   2 investigator       {"lookup_order": {"visible": true, "order": {"order_id": "O-202", "status": "delivered", "delay_days": 2 ...
   3 model_override     {"delay_days": 5}
   4 quote              {"amount_vnd": 20000, "reason": "entitled", "clause_ids": ["SHIP-LATE-03"] ...}
   5 refund_history     {"refund_count": 0, "refunded_vnd": 0}
   6 reply              {"text": "Dạ, LogiX đã hoàn 20.000đ cho đơn O-202."}
  refund_vnd     ledger=20000    label=0   <-- differs
  refund_count   ledger=1        label=0   <-- differs
  status         result=resolved label=denied
```

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, report `E-seeded_regression-20261118-4d40` (dòng E-002, cả 5 seed đều fail) |
| Triệu chứng | `pass_rate`, `refund_amount_correct`, `db_fact_kept` fail. Reply nói "đã hoàn 20.000đ", ledger cũng ghi 20.000 nên `reply_matches_ledger` không bắt; nhãn là denied / 0đ. Reply khớp ledger nhưng cả hai đều sai so với chính sách. |
| Bước sai đầu tiên | event 3 `model_override {"delay_days": 5}` |
| Vì sao là bước *đầu tiên* | event 1 handoff đúng hợp đồng (`facts` rỗng, chỉ có tool read-only). event 2 investigator đọc từ DB `delay_days` = 2, và với 2 ngày trễ đơn O-202 không đủ điều kiện. Từ event 3 trở đi mọi bước đều dùng con số đã bị đè: quote ở event 4 tính lại thành 20.000 rồi host ghi tiền. |
| Failure mode | FM-03 ticket_trust (`docs/failure_taxonomy.md`) |
| Đối chứng | `fixed C-002@11`: không có `model_override`. event 3 là `quote {"amount_vnd": 0, "reason": "no_entitlement"}`, event 4 reply "chưa đủ điều kiện hoàn", ledger 0, lab8 grader PASS. |
| Regression test | `src/tests/test_lab9_trace_case.py::test_fm03_ticket_delay_overrides_db_c002_seed11`: replay trial bằng `lab9.trace_case.investigate`, assert event 3 là `model_override` và `db_fact_kept`, `refund_amount_correct`, `pass_rate` đều False; cùng claim@seed trên `fixed` thì cả ba True. Test chạy trong CI (`-k "lab9 and not advanced"`). Đã thấy nó fail trên variant lỗi và pass trên `fixed`. Item E-002 đã có `provenance.from_trace = "swarm C-002@55"`, là cùng lỗi trên baseline, nên không cần thêm item mới. |
| Chưa chắc chắn | Trace không ghi kết quả của `issue_refund` (host), nên chỉ thấy tiền đã ghi qua ledger chứ không thấy ở event. Trace không cho biết vì sao model đè `delay_days`: MockLLM không có lý do, và variant bật `ticket_trust` cố định. Với LLM thật cần log prompt/response để biết đây là lỗi prompt hay lỗi parse. `seeded_regression` còn bật `pre_deducted` (event 5 `refund_history`), nhưng ở C-002 bước này không đổi số tiền. |

## Case phụ: FM-08 (reply sai số tiền, ledger đúng)

`bug_misreport C-008@11`: event 4 reply "đã hoàn 35.000đ", ledger 20.000 (approval A-008 cap). Grader Lab 8 PASS, nên chỉ `reply_matches_ledger` bắt được lỗi này. Regression test: `test_fm08_reply_amount_differs_from_ledger` (cùng file).

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
