import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from modules.database import Database

db = Database()
cursor = db.conn.cursor()
cursor.execute("SELECT COUNT(*) FROM counter_users")
users_before = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM counter_totals")
totals_before = cursor.fetchone()[0]

db.reset_all_counters()

cursor.execute("SELECT COUNT(*) FROM counter_users")
users_after = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM counter_totals")
totals_after = cursor.fetchone()[0]

db.close()

print(f"Reset complete.")
print(f"  counter_users: {users_before} -> {users_after}")
print(f"  counter_totals: {totals_before} -> {totals_after}")
print("Restart daemon for changes to take effect.")
