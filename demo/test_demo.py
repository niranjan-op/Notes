"""
Automated test of the pysqlcipher secure database demo
"""
import pysqlcipher
import os
import sys

db_file = "test_vault.db"
salt_file = "test_vault.salt"

# Clean up previous test files
if os.path.exists(db_file):
    os.remove(db_file)
if os.path.exists(salt_file):
    os.remove(salt_file)

vault = pysqlcipher.SecureDB(db_file)

print("--- Step 1: Initialization ---")
print("Creating new secure database...")

# Generate salt
salt = vault.generate_salt()
print(f"Generated salt: {salt}")

# Save salt
with open(salt_file, "w") as f:
    f.write(salt)

# Set password and connect
password = "TestPassword123"
print(f"Setting password: {password}")
vault.connect(password, salt)

# Create Table
vault.execute("CREATE TABLE secrets (id INTEGER PRIMARY KEY, note TEXT);")
vault.execute("INSERT INTO secrets (note) VALUES ('My Python Secret');")
vault.execute("INSERT INTO secrets (note) VALUES ('Another secret value');")
print("Database created and seeded with data.")
vault.close()

print("\n--- Step 2: Login Check ---")
try:
    # Create new vault instance for login
    vault2 = pysqlcipher.SecureDB(db_file)
    
    with open(salt_file, "r") as f:
        salt = f.read().strip()
    
    print(f"Attempting login with password: {password}")
    vault2.connect(password, salt)
    
    print("✓ Login Success! Reading Data:")
    data = vault2.execute("SELECT * FROM secrets;")
    print(f"Retrieved records: {data}")
    vault2.close()
    
    print("\n✓ Demo completed successfully!")
    
except Exception as e:
    print(f"✗ ERROR: {e}")
    sys.exit(1)
