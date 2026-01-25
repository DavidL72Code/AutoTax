from amazon_parser import amazon_parser

test_email = """
PayPal Receipt

Transaction date: Jan 4, 2026
Order Total: $49.99
Tax: $4.50

Thank you for your purchase!
"""

result = amazon_parser(test_email, "test_123")
print(result)