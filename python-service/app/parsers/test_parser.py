from .amazon_parser import amazon_parser

test_email = """
Amazon Receipt

Transaction date: Jan 4, 2026
Order Total: $49.99
Tax: $4.50

Thank you for your purchase!
"""

result = amazon_parser("Amazon package",test_email, "45673","Amazon")
print(result)
