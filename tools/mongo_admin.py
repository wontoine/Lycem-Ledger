#!/usr/bin/env python
"""
Utility script to diagnose and fix MongoDB index issues used by this Django app.

Usage examples:
  py tools/mongo_admin.py --check
  py tools/mongo_admin.py --fix-users-indexes

This script bootstraps Django so it uses the same settings (.env, tunnel) as the app.
"""

from __future__ import annotations

import argparse
import os
import sys


def bootstrap_django():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")
    import django  # type: ignore

    django.setup()


def get_db():
    from mongoengine.connection import get_db  # type: ignore

    return get_db()


def list_indexes(db, coll_name):
    return [ix for ix in db[coll_name].list_indexes()]


def find_duplicates_single(db, coll_name, field):
    pipeline = [
        {"$group": {"_id": f"${field}", "count": {"$sum": 1}, "ids": {"$push": "$_id"}}},
        {"$match": {"count": {"$gt": 1}, "_id": {"$ne": None}}},
        {"$limit": 50},
    ]
    return list(db[coll_name].aggregate(pipeline))


def find_duplicates_pair(db, coll_name, field_a, field_b):
    pipeline = [
        {
            "$group": {
                "_id": {field_a: f"${field_a}", field_b: f"${field_b}"},
                "count": {"$sum": 1},
                "ids": {"$push": "$_id"},
            }
        },
        {"$match": {"count": {"$gt": 1}, "_id": {field_a: {"$ne": None}, field_b: {"$ne": None}}}},
        {"$limit": 50},
    ]
    return list(db[coll_name].aggregate(pipeline))


def cmd_check(args):
    db = get_db()
    print(f"Using database: {db.name}")
    cols = args.collections or ["users", "customers", "Roles"]
    for coll in cols:
        print(f"\nCollection: {coll}")
        try:
            for ix in list_indexes(db, coll):
                print(f"  - {ix}")
        except Exception as e:
            print(f"  ! Failed to list indexes: {e}")
            continue

        if coll == "users":
            dups_userid = find_duplicates_single(db, coll, "userid")
            dups_username = find_duplicates_single(db, coll, "username")
            dups_email = find_duplicates_single(db, coll, "email")
            if any([dups_userid, dups_username, dups_email]):
                print("  Potential duplicates:")
                if dups_userid:
                    print(f"    userid duplicates: {len(dups_userid)} (showing up to 50)")
                if dups_username:
                    print(f"    username duplicates: {len(dups_username)} (showing up to 50)")
                if dups_email:
                    print(f"    email duplicates (non-null): {len(dups_email)} (showing up to 50)")
            else:
                print("  No duplicate userid/username/email detected.")

        if coll == "customers":
            dups_custid = find_duplicates_single(db, coll, "customerID")
            dups_userid = find_duplicates_single(db, coll, "userID")
            dups_email = find_duplicates_single(db, coll, "email")
            dups_pair = find_duplicates_pair(db, coll, "customerID", "email")
            if any([dups_custid, dups_userid, dups_email, dups_pair]):
                print("  Potential duplicates:")
                if dups_custid:
                    print(f"    customerID duplicates: {len(dups_custid)} (showing up to 50)")
                if dups_userid:
                    print(f"    userID duplicates: {len(dups_userid)} (showing up to 50)")
                if dups_email:
                    print(f"    email duplicates (non-null): {len(dups_email)} (showing up to 50)")
                if dups_pair:
                    print(f"    (customerID, email) pair duplicates: {len(dups_pair)} (showing up to 50)")
            else:
                print("  No duplicate customerID/userID/email or pair duplicates detected.")


def cmd_fix_users_indexes(args):
    db = get_db()
    coll = db["users"]
    existing = [ix["name"] for ix in coll.list_indexes()]
    to_drop = [name for name in ["username_1", "email_1"] if name in existing]
    for name in to_drop:
        try:
            print(f"Dropping index: {name}")
            coll.drop_index(name)
        except Exception as e:
            print(f"  ! skip {name}: {e}")

    # Ensure desired indexes
    print("Creating indexes (unique username, sparse-unique email, unique userid)…")
    coll.create_index("username", name="user_username_unique", unique=True)
    coll.create_index("email", name="user_email_sparse_unique", unique=True, sparse=True)
    coll.create_index("userid", name="user_userid_unique", unique=True)
    print("Done.")


def main(argv=None):
    bootstrap_django()

    p = argparse.ArgumentParser(description="Mongo admin utility for this app")
    sub = p.add_subparsers(dest="cmd")

    p_check = sub.add_parser("check", help="List indexes and detect duplicates")
    p_check.add_argument("--collections", nargs="*")
    p_check.set_defaults(func=cmd_check)

    p_fix = sub.add_parser("fix-users-indexes", help="Align users indexes to model intent")
    p_fix.set_defaults(func=cmd_fix_users_indexes)

    args = p.parse_args(argv)
    if not hasattr(args, "func"):
        p.print_help()
        return 2
    try:
        args.func(args)
        return 0
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())

