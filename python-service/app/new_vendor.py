def map_new_vendors():
    db=SessionLocal()

    transaction_vendors=db.query(Transaction.vendor).distinct().all()
    transaction_vendor_names={v[0] for v in transaction_vendors}

    known_raw_names={v.name for v in db.query(Vendor.all())}
    known_normalized_names={v.normalizedname for v in db.query(Vendor.all())}

    UnknownVendors=[]
    for(vendor in transaction_vendor_names):
        if vendor_name not in known_raw_names and vendor_name not in known_normalized_names:
            count=db.query(Transaction).filter(transaction.vendor==vendor_name).count()
            UnknownVendors.append((vendor_name,count))

    unmapped.sort(key=lamda x:x[1],reverse=True)
    print(f"\n Found {len(UnknownVendors)} unmapped vendors:")

    for vendor_name,count in unmapped:
        print(f"\nVendor:'{vendor_name}'")
        print(f"Appears in {count} transactions")
        normalized=input("Normalized name for this vendor: ").strip()
        if normalized:
            parser_type=input("Enter parser type(defautl is generic):").strip or "generic"
            vendor = Vendor(
                name=vendor_name,
                normalized_name=normalized,
                parser_type=parser_type
            )
            db.add(vendor)
            print(f"  Added: '{vendor_name}' → '{normalized}'")
    
    db.commit()


# Run it:
if __name__ == "__main__":
    discover_unmapped_vendors()