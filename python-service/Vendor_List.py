def Vendor_List():
    db=SessionLocal()

    vendors=[
        Vendor(name="Amzn Mktp US",normalized_name="Amazon",parser_type="amazon"),
        Vendor(name="Amazon.com",normalized_name="Amazon",parser_type="amazon"),
        Vendor(name="amzn.com/bill",normalized_name="Amazon",parser_type="amazon"),

        Vendor(nameVendor(name="Paypal *UberEats",normalized_name="UberEats",parser_type="paypal")),
        Vendor(name="Paypal *BestBuy",normalized_name="BestBuy",parser_type="paypal")
    ]
    for vendor in vendors:
        existing = db.query(Vendor).filter(Vendor.name == vendor.name).first()
        if not existing:
            db.add(vendor)
    
    db.commit()
    print("✅ Vendor List mappings")

# Run once:
if __name__ == "__main__":
    Vendor_List()