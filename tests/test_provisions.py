from vbpl_kb.legal_tree import parse_legal_tree


def test_parse_legal_tree_is_ordered_and_preserves_nested_structure() -> None:
    html_text = (
        "<div class='content'>"
        "<h2>Phần I. QUY ĐỊNH CHUNG</h2>"
        "<h3>Chương I. ĐIỀU KHOẢN CHUNG</h3>"
        "<h4>Điều 1. Phạm vi điều chỉnh</h4>"
        "<p>1. Luật này quy định về quản lý thuế.</p>"
        "<p>a) Thuế giá trị gia tăng;</p>"
        "<p>b) Thuế thu nhập doanh nghiệp.</p>"
        "<h4>Điều 2. Đối tượng áp dụng</h4>"
        "<p>Nội dung áp dụng.</p>"
        "</div>"
    )
    raw_html = html_text.encode("utf-8")
    detail_data = {"id": 1001, "title": "Luật Quản lý thuế"}

    nodes = parse_legal_tree(detail_data, raw_html)
    paths = [n.materialized_path for n in nodes]

    assert paths == [
        "phan-01",
        "phan-01/chuong-01",
        "phan-01/chuong-01/dieu-01",
        "phan-01/chuong-01/dieu-01/khoan-01",
        "phan-01/chuong-01/dieu-01/khoan-01/diem-a",
        "phan-01/chuong-01/dieu-01/khoan-01/diem-b",
        "phan-01/chuong-01/dieu-02",
    ]
