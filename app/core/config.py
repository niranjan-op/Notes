import configparser
import os
import shutil
import time
from pathlib import Path

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

import sys

CONFIG_FILE = "config.ini"
APP_NAME = "Secure Notes"


def _default_base_path() -> str:
    if os.name == "nt":
        return os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    if sys.platform == "darwin":
        return str(Path.home() / "Library" / "Application Support")
    return os.getenv("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")


base_path = _default_base_path()

def vault_path(name: str) -> Path:
    """Return the private on-device directory for one vault."""
    return Path(base_path) / APP_NAME / name

def ensure_config():
    config_path = os.path.join(base_path, APP_NAME, CONFIG_FILE)
    if not os.path.exists(config_path):
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        config = configparser.ConfigParser()
        config['vaults'] = {'items': ''}
        config['last_open_vault'] = {'value': ''}
        with open(config_path, "w") as f:
            config.write(f)
    return config_path

def load_config(password,name):
    # FIXED: Path must include vault name to match create_db structure
    app_data_path = vault_path(name)
    
    if os.path.exists(app_data_path):
        print("Attempting db recovery...")
        db = ss.DbOperations(str(app_data_path))
        try:
            if db.connect(str(password), str(name)):
                print("Connection successful! Database recovered successfully.")
                return True
            print("Database recovery failed!")
            return False
        finally:
            db.close()
    else:
        # Fallback or error if directory doesn't exist
        print(f"Vault directory not found: {app_data_path}")
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

def search_config():
    if os.path.exists(os.path.join(base_path,APP_NAME,CONFIG_FILE)):
        return True
    else:
        return False

def read_config():
    config_path = ensure_config()
    config = configparser.ConfigParser()
    config.read(config_path)
    vaults_csv = config.get('vaults', 'items', fallback='')
    vaults = [v for v in vaults_csv.split(',') if v]
    last_open_vault = config.get('last_open_vault', 'value', fallback='')
    return vaults, last_open_vault

def create_config(vault_name: str):
    config_path = ensure_config()
    config = configparser.ConfigParser()
    config.read(config_path)

    vaults_csv = config.get('vaults', 'items', fallback='')
    vaults = [v for v in vaults_csv.split(',') if v]
    if vault_name not in vaults:
        vaults.append(vault_name)

    config['vaults'] = {'items': ','.join(vaults)}
    config['last_open_vault'] = {'value': vault_name}

    with open(config_path, "w") as f:
        config.write(f)

    print(f"Vaults:{vaults}")
    print(f"last_open_vault:{vault_name}")
    print("Config Creation Successful!")
    return True

def update_config(vault_name: str):
    config_path = ensure_config()
    config = configparser.ConfigParser()
    config.read(config_path)

    vaults_csv = config.get('vaults', 'items', fallback='')
    vaults = [v for v in vaults_csv.split(',') if v]
    if vault_name not in vaults:
        vaults.append(vault_name)

    config['vaults'] = {'items': ','.join(vaults)}
    config['last_open_vault'] = {'value': vault_name}

    with open(config_path, "w") as f:
        config.write(f)

    print("Successfully updated config file")
    print(f"Vaults:{vaults}")
    print(f"last_open_vault:{vault_name}")
    return True

_INVALID_NAME_CHARS = set('<>:"/\\|?*')
_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def validate_vault_name(name: str) -> str | None:
    """Return a user-facing problem with a vault name, or None when it is usable."""
    if not name:
        return "Enter a vault name."
    if len(name) > 64:
        return "Use 64 characters or fewer."
    if any(char in _INVALID_NAME_CHARS or ord(char) < 32 for char in name):
        return 'Vault names cannot contain < > : " / \\ | ? *'
    if name.endswith((".", " ")) or name.split(".")[0].upper() in _RESERVED_NAMES:
        return "That name is reserved by Windows."
    return None


def delete_vault(name: str) -> None:
    """Permanently remove a vault's encrypted files and its config entry.

    Files are removed first so a failure (for example a locked database) leaves
    the vault listed and recoverable. Raises ValueError for unsafe names and
    OSError when the files cannot be removed.
    """
    root = (Path(base_path) / APP_NAME).resolve()
    target = vault_path(name).resolve()
    if validate_vault_name(name) or target.parent != root:
        raise ValueError("Invalid vault name.")
    if target.exists():
        shutil.rmtree(target)

    config_path = ensure_config()
    config = configparser.ConfigParser()
    config.read(config_path)
    vaults = [v for v in config.get('vaults', 'items', fallback='').split(',') if v and v != name]
    last_open = config.get('last_open_vault', 'value', fallback='')
    config['vaults'] = {'items': ','.join(vaults)}
    config['last_open_vault'] = {'value': last_open if last_open != name else (vaults[-1] if vaults else '')}
    with open(config_path, "w") as f:
        config.write(f)


def get_preference(key: str, default: str = "") -> str:
    """Read a non-sensitive UI preference from the central config."""
    config = configparser.ConfigParser()
    config.read(ensure_config())
    return config.get('preferences', key, fallback=default)


def set_preference(key: str, value: str) -> None:
    """Persist a non-sensitive UI preference in the central config."""
    config_path = ensure_config()
    config = configparser.ConfigParser()
    config.read(config_path)
    if not config.has_section('preferences'):
        config.add_section('preferences')
    config.set('preferences', key, value)
    with open(config_path, "w") as f:
        config.write(f)


def create_db(password: str, name:str):
    if ss is None:
        raise ImportError("secure_storage module is missing.")
    
    # CHANGED: Create a sub-directory for the specific vault to avoid conflicts with global config
    clean_dir_path = vault_path(name)
    
    print(f"Full db path:{clean_dir_path}")

    if os.path.exists(clean_dir_path):
        raise FileExistsError(f"Vault directory already exists: {clean_dir_path}")
    
    # ADDED: Ensure the directory exists so C++ can create the .db file inside it
    os.makedirs(clean_dir_path, exist_ok=True)

    # 5. Connect and Create DB
    try:
        # Strategy A: Use Native OS Path
        print(f"Attempting creation with native path: {clean_dir_path}")
        
        # FIXED: Cast Path object to string because C++ extension expects std::string
        db = ss.DbOperations(str(clean_dir_path))
        
        if db.connect(password,name):
            print("Connection successful! Database created.")
            # REMOVED: write_config_file(clean_dir_path) 
            # We rely on create_config/update_config to track vaults in the central config.ini
            return True
        else:
            print("Native path failed. Attempting fallback...")
            
            # Strategy B: Force Forward Slashes (Unix Style fallback)
            fallback_path = str(clean_dir_path).replace("\\", "/")
            print(f"Attempting creation with fallback path: {fallback_path}")
            
            db_retry = ss.DbOperations(fallback_path)
            if db_retry.connect(password,name):
                print("Fallback connection successful!")
                return True
                
            print("All creation strategies failed.")
            return False
            
    except Exception as e:
        print(f"CRITICAL EXCEPTION during DB creation: {e}")
        return False




