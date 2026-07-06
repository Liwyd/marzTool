import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from modules.database import Database

db = Database()
cursor = db.conn.cursor()

print("=== Counter Reset ===")
cursor.execute("SELECT COUNT(*) FROM counter_users")
cu_before = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM counter_totals")
ct_before = cursor.fetchone()[0]
db.reset_all_counters()
cursor.execute("SELECT COUNT(*) FROM counter_users")
cu_after = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM counter_totals")
ct_after = cursor.fetchone()[0]
print(f"  counter_users: {cu_before} -> {cu_after}")
print(f"  counter_totals: {ct_before} -> {ct_after}")

print("\n=== VCounter Reset ===")
cursor.execute("SELECT COUNT(*) FROM vcounter_users")
vu_before = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM vcounter_totals")
vt_before = cursor.fetchone()[0]
db.reset_all_vcounter()
cursor.execute("SELECT COUNT(*) FROM vcounter_users")
vu_after = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM vcounter_totals")
vt_after = cursor.fetchone()[0]
print(f"  vcounter_users: {vu_before} -> {vu_after}")
print(f"  vcounter_totals: {vt_before} -> {vt_after}")

db.close()
print("\nDone. Restart daemon for changes to take effect.")
