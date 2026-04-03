from app.parsers.generic_parser import regex_parsing


def test_tax_does_not_use_before_tax_value():
    email_text = """
    Receipt Summary
    Subtotal: $18.40
    Amount Before Tax: $18.40
    Sales Tax: $1.15
    Total: $19.55
    """

    result = regex_parsing(email_text)

    assert result["amount"] == 19.55
    assert result["tax"] == 1.15


def test_plain_tax_label_still_works():
    email_text = """
    Order Total: $49.99
    Tax: $4.50
    """

    result = regex_parsing(email_text)

    assert result["amount"] == 49.99
    assert result["tax"] == 4.50


if __name__ == "__main__":
    test_tax_does_not_use_before_tax_value()
    test_plain_tax_label_still_works()
    print("parser regression checks passed")
