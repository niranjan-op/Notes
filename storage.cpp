#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "sqlite3.h" 
#include <openssl/evp.h>
#include <vector>
#include <string>
#include <ctime>
#include <cstdlib>
#include <iomanip>
#include <sstream>

namespace py = pybind11;
using namespace std;

struct Note {
    int id;
    string title;
    string content;
    bool is_markdown;
    int folder_id;  
    string created_at;  
    string updated_at;  
};

struct Folder {  
    int id;
    string name;
    int parent_id;
};

class StorageManager {
    sqlite3* db;
    string db_path;

    private:
    string derive_key(const string& password, const string& salt){
        unsigned char key[32];
        unsigned char salt_bytes[16];
        
        // Convert hex salt string to bytes
        for(size_t i = 0; i < salt.length(); i += 2){
            string byte_str = salt.substr(i, 2);
            salt_bytes[i/2] = strtol(byte_str.c_str(), nullptr, 16);
        }

        // PBKDF2 with SHA256, 100000 iterations
        PKCS5_PBKDF2_HMAC(password.c_str(), password.length(), 
                          salt_bytes, 16, 
                          100000, EVP_sha256(), 
                          32, key);
        
        // Convert to hex string for SQLCipher
        stringstream ss;
        for(int i = 0; i < 32; i++){
            ss << hex << setw(2) << setfill('0') << (int)key[i];
        }
        return ss.str();
    }
    
    public:
    StorageManager(string path, string password, string salt) : db_path(path) {
        if (sqlite3_open(path.c_str(), &db)) {
            throw runtime_error("Cannot open database");
        }
        
        // Derive key from password + salt (all in C++)
        string encryption_key = derive_key(password, salt);
        
        // Set encryption key for SQLCipher
        sqlite3_stmt* stmt;
        string pragma = "PRAGMA key = 'x" + encryption_key + "';";
        if (sqlite3_prepare_v2(db, pragma.c_str(), -1, &stmt, 0) == SQLITE_OK) {
            sqlite3_step(stmt);
            sqlite3_finalize(stmt);
        } else {
            throw runtime_error("Cannot set encryption key");
        }
        
        create_table();
    }

    string get_current_timestamp() {
        time_t now = time(0);
        char buf[80];
        strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M:%S", localtime(&now));
        return string(buf);
    }
    
    ~StorageManager() {
        sqlite3_close(db);
    }
    
    void create_table() {
        const char* notes_sql = 
            "CREATE TABLE IF NOT EXISTS NOTES("
            "ID INTEGER PRIMARY KEY AUTOINCREMENT,"
            "TITLE TEXT,"
            "CONTENT TEXT,"
            "IS_MARKDOWN INTEGER,"
            "FOLDER_ID INTEGER DEFAULT 0,"
            "CREATED_AT TEXT,"
            "UPDATED_AT TEXT);";
        
        const char* folders_sql = 
            "CREATE TABLE IF NOT EXISTS FOLDERS("
            "ID INTEGER PRIMARY KEY AUTOINCREMENT,"
            "NAME TEXT,"
            "FOREIGN KEY(PARENT_ID) REFERENNCES FOLDERS(ID);";
        
        char* errMsg = 0;
        sqlite3_exec(db, notes_sql, 0, 0, &errMsg);
        sqlite3_exec(db, folders_sql, 0, 0, &errMsg);
    }
    
    void add_note(string title, string content, bool is_md, int folder_id = 0){
        sqlite3_stmt* stmt;
        const char* sql = "INSERT INTO NOTES (TITLE, CONTENT, IS_MARKDOWN, FOLDER_ID, CREATED_AT, UPDATED_AT) VALUES (?,?,?,?,?,?)";
        
        string timestamp = get_current_timestamp();
        
        sqlite3_prepare_v2(db, sql, -1, &stmt, 0);
        sqlite3_bind_text(stmt, 1, title.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_text(stmt, 2, content.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_int(stmt, 3, is_md ? 1 : 0);
        sqlite3_bind_int(stmt, 4, folder_id);
        sqlite3_bind_text(stmt, 5, timestamp.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_text(stmt, 6, timestamp.c_str(), -1, SQLITE_STATIC);
        
        sqlite3_step(stmt);
        sqlite3_finalize(stmt);
    }
    
    void update_note(int id, string title, string content, bool is_md){
        sqlite3_stmt* stmt;
        const char* sql = "UPDATE NOTES SET TITLE = ?, CONTENT = ?, IS_MARKDOWN = ?, UPDATED_AT = ? WHERE ID = ?;";
        
        string timestamp = get_current_timestamp();
        
        if(sqlite3_prepare_v2(db, sql, -1, &stmt, 0) == SQLITE_OK){
            sqlite3_bind_text(stmt, 1, title.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(stmt, 2, content.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_int(stmt, 3, is_md ? 1 : 0);
            sqlite3_bind_text(stmt, 4, timestamp.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_int(stmt, 5, id);
            sqlite3_step(stmt);
        }
        sqlite3_finalize(stmt);
    }
    
    vector<Note> get_all_notes(){
        vector<Note> notes;
        sqlite3_stmt* stmt;
        const char* sql = "SELECT ID, TITLE, CONTENT, IS_MARKDOWN, FOLDER_ID, CREATED_AT, UPDATED_AT FROM NOTES";
        
        if(sqlite3_prepare_v2(db, sql, -1, &stmt, 0) == SQLITE_OK){
            while(sqlite3_step(stmt) == SQLITE_ROW){
                Note n;
                n.id = sqlite3_column_int(stmt, 0);
                const unsigned char* t = sqlite3_column_text(stmt, 1);
                n.title = t ? reinterpret_cast<const char*>(t) : "";
                const unsigned char* c = sqlite3_column_text(stmt, 2);
                n.content = c ? reinterpret_cast<const char*>(c) : "";
                n.is_markdown = sqlite3_column_int(stmt, 3);
                n.folder_id = sqlite3_column_int(stmt, 4);
                const unsigned char* ca = sqlite3_column_text(stmt, 5);
                n.created_at = ca ? reinterpret_cast<const char*>(ca) : "";
                const unsigned char* ua = sqlite3_column_text(stmt, 6);
                n.updated_at = ua ? reinterpret_cast<const char*>(ua) : "";
                notes.emplace_back(n);
            }
        }
        sqlite3_finalize(stmt);
        return notes;
    }
    
    int add_folder(string name, int parent_id = 0){
        sqlite3_stmt* stmt;
        const char* sql = "INSERT INTO FOLDERS (NAME, PARENT_ID) VALUES (?,?)";
        
        sqlite3_prepare_v2(db, sql, -1, &stmt, 0);
        sqlite3_bind_text(stmt, 1, name.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_int(stmt, 2, parent_id);
        sqlite3_step(stmt);
        sqlite3_finalize(stmt);
        
        return sqlite3_last_insert_rowid(db);
    }
    
    vector<Folder> get_all_folders(){
        vector<Folder> folders;
        sqlite3_stmt* stmt;
        const char* sql = "SELECT ID, NAME, PARENT_ID FROM FOLDERS";
        
        if(sqlite3_prepare_v2(db, sql, -1, &stmt, 0) == SQLITE_OK){
            while(sqlite3_step(stmt) == SQLITE_ROW){
                Folder f;
                f.id = sqlite3_column_int(stmt, 0);
                const unsigned char* n = sqlite3_column_text(stmt, 1);
                f.name = n ? reinterpret_cast<const char*>(n) : "";
                f.parent_id = sqlite3_column_int(stmt, 2);
                folders.emplace_back(f);
            }
        }
        sqlite3_finalize(stmt);
        return folders;
    }
};

PYBIND11_MODULE(secure_storage, m){
    py::class_<Note>(m, "Note")
        .def_readonly("id", &Note::id)
        .def_readonly("title", &Note::title)
        .def_readonly("content", &Note::content)
        .def_readonly("is_markdown", &Note::is_markdown)
        .def_readonly("folder_id", &Note::folder_id)
        .def_readonly("created_at", &Note::created_at)
        .def_readonly("updated_at", &Note::updated_at);
    
    py::class_<Folder>(m, "Folder")
        .def_readonly("id", &Folder::id)
        .def_readonly("name", &Folder::name)
        .def_readonly("parent_id", &Folder::parent_id);
    
    py::class_<StorageManager>(m, "StorageManager")
        .def(py::init<std::string, std::string, std::string>())
        .def("add_note", &StorageManager::add_note, py::arg("title"), py::arg("content"), py::arg("is_md"), py::arg("folder_id") = 0)
        .def("update_note", &StorageManager::update_note)
        .def("get_all_notes", &StorageManager::get_all_notes)
        .def("add_folder", &StorageManager::add_folder, py::arg("name"), py::arg("parent_id") = 0)
        .def("get_all_folders", &StorageManager::get_all_folders);
}