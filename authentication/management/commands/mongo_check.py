from django.core.management.base import BaseCommand

try:
    from mongoengine.connection import get_db
except Exception:  # pragma: no cover
    get_db = None


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


class Command(BaseCommand):
    help = "Diagnose MongoDB index state and duplicate conflicts for users/customers."

    def add_arguments(self, parser):
        parser.add_argument(
            "--collections",
            nargs="*",
            default=["users", "customers", "Roles"],
            help="Collections to inspect (default: users customers Roles)",
        )

    def handle(self, *args, **options):
        if get_db is None:
            self.stderr.write("mongoengine not available; cannot inspect DB")
            return 1

        db = get_db()
        self.stdout.write(f"Using database: {db.name}")

        cols = options["collections"]
        for coll in cols:
            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_HEADING(f"Collection: {coll}"))
            try:
                idx = list_indexes(db, coll)
                for i in idx:
                    self.stdout.write(f"  - {i}")
            except Exception as e:  # pragma: no cover
                self.stderr.write(self.style.ERROR(f"  ! Failed to list indexes: {e}"))
                continue

            if coll == "users":
                dups_userid = find_duplicates_single(db, coll, "userid")
                dups_username = find_duplicates_single(db, coll, "username")
                dups_email = find_duplicates_single(db, coll, "email")
                if any([dups_userid, dups_username, dups_email]):
                    self.stdout.write(self.style.WARNING("  Potential duplicates:"))
                    if dups_userid:
                        self.stdout.write(f"    userid duplicates: {len(dups_userid)} (showing up to 50)")
                    if dups_username:
                        self.stdout.write(f"    username duplicates: {len(dups_username)} (showing up to 50)")
                    if dups_email:
                        self.stdout.write(f"    email duplicates (non-null): {len(dups_email)} (showing up to 50)")
                else:
                    self.stdout.write("  No duplicate userid/username/email detected.")

            if coll == "customers":
                dups_custid = find_duplicates_single(db, coll, "customerID")
                dups_userid = find_duplicates_single(db, coll, "userID")
                dups_email = find_duplicates_single(db, coll, "email")
                dups_pair = find_duplicates_pair(db, coll, "customerID", "email")
                if any([dups_custid, dups_userid, dups_email, dups_pair]):
                    self.stdout.write(self.style.WARNING("  Potential duplicates:"))
                    if dups_custid:
                        self.stdout.write(f"    customerID duplicates: {len(dups_custid)} (showing up to 50)")
                    if dups_userid:
                        self.stdout.write(f"    userID duplicates: {len(dups_userid)} (showing up to 50)")
                    if dups_email:
                        self.stdout.write(f"    email duplicates (non-null): {len(dups_email)} (showing up to 50)")
                    if dups_pair:
                        self.stdout.write(
                            f"    (customerID, email) pair duplicates: {len(dups_pair)} (showing up to 50)"
                        )
                else:
                    self.stdout.write("  No duplicate customerID/userID/email or pair duplicates detected.")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Mongo diagnostics complete."))
        return 0

