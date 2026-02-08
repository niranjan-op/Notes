import configparser
import os
import time

try:
    # FIXED: Use relative import for sibling file
    from . import secure_storage as ss
    print("Success! Module loaded.")
except ImportError:
    try:
        import secure_storage as ss
    except ImportError as e:
        print(f"Failed to load secure_storage: {e}")
        ss = None

CONFIG_FILE = "config.ini"

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return None
    else:
        parser = configparser.ConfigParser()
        parser.read(CONFIG_FILE)
        return {
            'db_path': parser.get('setup', 'db_path'),
            'theme': parser.get('preferences', 'theme', fallback='Dark')
        }
        
def create_config(db_path: str, theme: str, password: str):
    if ss is None:
        print("Error: secure_storage module is missing.")
        return False

    clean_dir_path = os.path.abspath(os.path.normpath(db_path.strip()))
    print(f"Full db path:{clean_dir_path}")
    
    # 4. Remove existing DB file to ensure fresh creation
    if os.path.exists(clean_dir_path):
        try:
            os.remove(clean_dir_path)
            time.sleep(0.1) 
            print("Removed existing DB file.")
        except Exception as e:
            print(f"Warning: Could not remove existing file: {e}")

    # 5. Connect and Create DB
    try:
        # Strategy A: Use Native OS Path
        print(f"Attempting creation with native path: {clean_dir_path}")
        db = ss.DbOperations(clean_dir_path)
        
        if db.connect(password):
            print("Connection successful! Database created.")
            write_config_file(clean_dir_path, theme)
            return True
        else:
            print("Native path failed. Attempting fallback...")
            
            # Strategy B: Force Forward Slashes (Unix Style fallback)
            fallback_path = clean_dir_path.replace("\\", "/")
            print(f"Attempting creation with fallback path: {fallback_path}")
            
            db_retry = ss.DbOperations(fallback_path)
            if db_retry.connect(password):
                print("Fallback connection successful!")
                write_config_file(clean_dir_path, theme) # Save the native path to config
                return True
                
            print("All creation strategies failed.")
            return False
            
    except Exception as e:
        print(f"CRITICAL EXCEPTION during DB creation: {e}")
        return False

def write_config_file(path, theme):
    config = configparser.ConfigParser()
    config['setup'] = { 'db_path': path }
    config['preferences'] = { 'theme': theme }
    
    with open(os.path.join(path,CONFIG_FILE), 'w') as f:
        config.write(f)
    
    # Print absolute path of the created config file
    abs_config_path = os.path.abspath(CONFIG_FILE)
    print(f"Config file updated successfully at: {abs_config_path}")



