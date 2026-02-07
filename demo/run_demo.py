import pysqlcipher
import os

db_file = "py_vault.db"
salt_file = "py_vault.salt"
vault = pysqlcipher.SecureDB(db_file)

print("--- Step 1: Initialization ---")
if not os.path.exists(salt_file):
    print("Creating new secure database...")
    salt = vault.generate_salt()
    
    # Save salt
    with open(salt_file, "w") as f:
        f.write(salt)
    
    password = input("Set a password: ")
    vault.connect(password, salt)
    
    # Create Table
    vault.execute("CREATE TABLE secrets (id INTEGER PRIMARY KEY, note TEXT);")
    vault.execute("INSERT INTO secrets (note) VALUES ('My Python Secret');")
    print("Database created and seeded.")
    vault.close()
else:
    print("Database already exists.")

print("\n--- Step 2: Login Check ---")
try:
    with open(salt_file, "r") as f:
        salt = f.read().strip()
    
    password = input("Enter password to unlock: ")
    vault.connect(password, salt)
    
    print("Login Success! Reading Data:")
    data = vault.execute("SELECT * FROM secrets;")
    print(data)
    
except Exception as e:
    print(f"ERROR: {e}")