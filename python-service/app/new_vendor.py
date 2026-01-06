def map_new_vendors():
    db=SessionLocal()

    transaction_vendors=db.query(Transaction.vendor).distinct().all()
    transaction_vendor_names={v[0] for v in transaction_vendors}

    known_raw_names={v.name for v in db.query(Vendor.all())}
    known_normalized_names={v.normalizedname for v in db.query(Vendor.all())}