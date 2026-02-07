import configparser
import os
# Update this to your EXACT vcpkg 'bin' folder
# This folder must contain sqlcipher.dll
import os
# Add the path where your vcpkg DLLs are located
vcpkg_bin = r'C:\vcpkg\installed\x64-windows\bin'
os.add_dll_directory(vcpkg_bin)

try:
    import secure_storage as ss
    print("Success! Module loaded.")
except ImportError as e:
    print(f"Failed to load: {e}")
CONFIG_FILE = "config.ini"

def load_config():
    if not os.path.exists(CONFIG_FILE):
        print("Config file doesn't exist")
        return None
    else:
        parser = configparser.ConfigParser()
        parser.read(CONFIG_FILE)
        return {
            'db_path': parser.get('setup', 'db_path'),
            'theme': parser.get('preferences', 'theme', fallback='Dark')
        }
        
def create_config(db_path: str, setup_complete: bool, theme: str, password: str):
    config = configparser.ConfigParser()
    config['setup'] = {
        'db_path': db_path,
    }
    config['preferences'] = {
        'theme': theme
    }
    with open(CONFIG_FILE, 'w') as f:
        config.write(f)
    print("Config file created successfully in config.py")
    
    # Create DbOperations instance with the path, then connect
    db = ss.DbOperations(db_path)
    if db.connect(password):
        print("Connection was successful! Database created and connected successfully with user's password")
        return True
    else:
        print("An error occurred! Please try again")
        return False




