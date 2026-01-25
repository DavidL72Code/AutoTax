# test_ai_vendor.py

from parser_select import identify_vendor_with_ai

# Test case 1: Clear vendor name
test_email_1 = """
Amazon
123 Main Street

Your order total: $15.99
Tax: $1.50
Date: January 21, 2026

Thank you for your visit!
"""

vendor = identify_vendor_with_ai(test_email_1)
print(f"Test 1: {vendor}")  # Should print: "Blue Mountain Cafe"


# Test case 2: Vendor in different location
test_email_2 = """
Order Confirmation

Thank you for shopping with Target!

Order Total: $49.99
Order Date: Jan 21, 2026
"""

vendor = identify_vendor_with_ai(test_email_2)
print(f"Test 2: {vendor}")  # Should print: "Target"


# Test case 3: Harder case
test_email_3 = """
Receipt

You purchased items totaling $25.50
from Joe's Pizza on Main St.

Date: 1/21/2026
"""

vendor = identify_vendor_with_ai(test_email_3)
print(f"Test 3: {vendor}")  # Should print: "Joe's Pizza"

## Complete Flow with AI Vendor Detection

### **Example 1: Known Vendor**
"""
Email from: receipts@starbucks.com
    ↓
identify_vendor() → "Starbucks" ✅
    ↓
normalize_vendor_name() → "Starbucks" ✅
    ↓
NO AI CALL (vendor known)
    ↓
generic_parser("Starbucks") → uses regex
    ↓
Done!
"""

### **Example 2: Unknown Vendor**
"""
Email from: noreply@randomsite.com
Subject: "Your Receipt"
Body: "Blue Mountain Cafe\nTotal: $15.99..."
    ↓
identify_vendor() → None
    ↓
normalize_vendor_name() → "Unknown"
    ↓
identify_vendor_with_ai() ← AI CALL
    ↓
AI extracts: "Blue Mountain Cafe" ✅
    ↓
generic_parser("Blue Mountain Cafe") → uses regex for amount/date
    ↓
Save: Transaction(vendor="Blue Mountain Cafe", ...)
    ↓
Later: run map_new_vendors() to add to database
"""


## Performance Impact

### **Without AI vendor identification:**
"""
Unknown vendor → saved as "Unknown"
All unknown vendors clump together ❌
Hard to map later
"""

### **With AI vendor identification:**
"""
Unknown vendor → AI identifies "Blue Mountain Cafe"
Each vendor saved with correct name ✅
Easy to map later with map_new_vendors()
"""