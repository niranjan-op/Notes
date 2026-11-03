#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <iostream>
#include <optional>
#include <vector>
#include <sstream>
#include <iomanip>
#include <ctime>
#include <sqlcipher/sqlite3.h>

namespace py = pybind11;
using namespace std;

struct Note
{
    int id;
    int folder_id;
    string content;
    string title;
    bool is_md;
    string created_at;
    string updated_at;
};
struct Folder
{
    int id;
    string name;
    int parent_id;
    string created_at;
    string updated_at;
};

struct MiniNote
{
    int note_id;
    int folder_id;
    string title;
    string created_at;
    string updated_at;
};

class DbOperations
{
    sqlite3 *db = nullptr;
    string db_path;
    int rc;

public:
    DbOperations(const string &path) : db_path(path) {}
    ~DbOperations() { close(); }
    void close()
    {
        if (db)
        {
            sqlite3_close(db);
            db = nullptr;
        }
    }
    void create_table()
    {
        const char *notes_sql =
            "CREATE TABLE IF NOT EXISTS notes("
            "note_id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "folder_id INTEGER,"
            "title TEXT,"
            "content TEXT,"
            "is_markdown INTEGER,"
            "created_at TEXT,"
            "updated_at TEXT,"
            "FOREIGN KEY(folder_id) REFERENCES folders(folder_id));";

        const char *folders_sql =
            "CREATE TABLE IF NOT EXISTS folders("
            "folder_id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "name TEXT,"
            "parent_id INTEGER,"
            "created_at TEXT,"
            "updated_at TEXT,"
            "FOREIGN KEY(parent_id) REFERENCES folders(folder_id));";

        char *errMsg = 0;
        sqlite3_exec(db, folders_sql, 0, 0, &errMsg);
        sqlite3_exec(db, notes_sql, 0, 0, &errMsg);
    }

    bool connect(const string &password, const string &name)
    {

        char separator = '/';
#ifdef _WIN32
        separator = '\\';
#endif

        string full_path = db_path;
        if (!full_path.empty() && full_path.back() != separator)
        {
            full_path += separator;
        }
        full_path += name + ".db";

        rc = sqlite3_open(full_path.c_str(), &db);

        if (rc != SQLITE_OK)
        {
            cerr << "Cannot open database: " << sqlite3_errmsg(db) << endl;
            return false;
        }

        // 1. Apply the key immediately
        rc = sqlite3_key(db, password.c_str(), static_cast<int>(password.size()));
        if (rc != SQLITE_OK)
        {
            cerr << "Failed to set encryption key" << endl;
            close();
            return false;
        }

        // 2. FORCE ENCRYPTION: Create a dummy table if it's a new DB
        // This forces SQLCipher to write the encrypted header to the file.
        char *errMsg = nullptr;
        const char *init_sql = "CREATE TABLE IF NOT EXISTS _sqlcipher_flush (id INTEGER);";
        sqlite3_exec(db, init_sql, nullptr, nullptr, &errMsg);

        // 3. Test access
        rc = sqlite3_exec(db, "SELECT count(*) FROM sqlite_master;", nullptr, nullptr, &errMsg);
        if (rc == SQLITE_OK)
        {
            cout << "\nC++: Connection established and database encrypted!" << endl;
            create_table();
            return true;
        }
        else
        {
            cerr << "\nC++: Authentication failed!" << endl;
            if (errMsg)
                sqlite3_free(errMsg);
            close();
            return false;
        }
    }

    bool connect_readonly(const string &password, const string &name)
    {
        char separator = '/';
#ifdef _WIN32
        separator = '\\';
#endif
        string full_path = db_path;
        if (!full_path.empty() && full_path.back() != separator)
        {
            full_path += separator;
        }
        full_path += name + ".db";

        rc = sqlite3_open_v2(full_path.c_str(), &db, SQLITE_OPEN_READONLY, nullptr);
        if (rc != SQLITE_OK)
        {
            close();
            return false;
        }
        rc = sqlite3_key(db, password.c_str(), static_cast<int>(password.size()));
        if (rc != SQLITE_OK)
        {
            close();
            return false;
        }
        char *errMsg = nullptr;
        rc = sqlite3_exec(db, "SELECT count(*) FROM sqlite_master;", nullptr, nullptr, &errMsg);
        if (rc != SQLITE_OK)
        {
            if (errMsg)
                sqlite3_free(errMsg);
            close();
            return false;
        }
        return true;
    }

    string get_current_timestamp()
    {
        time_t now = time(0);
        char buf[80];
        strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M:%S", localtime(&now));
        return string(buf);
    }

    void add_note(string title, string content, bool is_md, int folder_id = 0)
    {
        sqlite3_stmt *stmt;
        const char *sql = "INSERT INTO notes (folder_id,title,content, is_markdown, created_at, updated_at) VALUES (?,?,?,?,?,?);";
        string timestamp = get_current_timestamp();
        sqlite3_prepare_v2(db, sql, -1, &stmt, 0);
        sqlite3_bind_int(stmt, 1, folder_id);
        sqlite3_bind_text(stmt, 2, title.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_text(stmt, 3, content.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_int(stmt, 4, is_md ? 1 : 0);
        sqlite3_bind_text(stmt, 5, timestamp.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_text(stmt, 6, timestamp.c_str(), -1, SQLITE_STATIC);

        sqlite3_step(stmt);
        sqlite3_finalize(stmt);
    }
    void add_folder(string name, int parent_id = 0)
    {
        sqlite3_stmt *stmt;
        const char *sql = "INSERT INTO folders(name, parent_id,created_at,updated_at) VALUES(?,?,?,?);";
        string timestamp = get_current_timestamp();
        sqlite3_prepare_v2(db, sql, -1, &stmt, 0);
        sqlite3_bind_text(stmt, 1, name.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_int(stmt, 2, parent_id);
        sqlite3_bind_text(stmt, 3, timestamp.c_str(), -1, SQLITE_STATIC);
        sqlite3_bind_text(stmt, 4, timestamp.c_str(), -1, SQLITE_STATIC);

        sqlite3_step(stmt);
        sqlite3_finalize(stmt);
    }
    void update_note(int id, optional<string> title, optional<string> content, optional<bool> is_md, optional<int> folder_id)
    {
        stringstream ss;
        ss << "UPDATE notes SET ";

        bool first = true;
        if (title.has_value())
        {
            if (!first)
                ss << ", ";
            ss << "title = ?";
            first = false;
        }
        if (content.has_value())
        {
            if (!first)
                ss << ", ";
            ss << "content = ?";
            first = false;
        }
        if (is_md.has_value())
        {
            if (!first)
                ss << ", ";
            ss << "is_markdown = ?";
            first = false;
        }
        if (folder_id.has_value())
        {
            if (!first)
                ss << ", ";
            ss << "folder_id = ?";
            first = false;
        }

        if (!first)
            ss << ", ";
        ss << "updated_at = ? WHERE note_id = ?;";

        sqlite3_stmt *stmt;
        if (sqlite3_prepare_v2(db, ss.str().c_str(), -1, &stmt, 0) == SQLITE_OK)
        {
            int idx = 1;
            if (title.has_value())
                sqlite3_bind_text(stmt, idx++, title->c_str(), -1, SQLITE_TRANSIENT);
            if (content.has_value())
                sqlite3_bind_text(stmt, idx++, content->c_str(), -1, SQLITE_TRANSIENT);
            if (is_md.has_value())
                sqlite3_bind_int(stmt, idx++, is_md.value() ? 1 : 0);
            if (folder_id.has_value())
                sqlite3_bind_int(stmt, idx++, folder_id.value());

            string timestamp = get_current_timestamp();
            sqlite3_bind_text(stmt, idx++, timestamp.c_str(), -1, SQLITE_TRANSIENT);
            sqlite3_bind_int(stmt, idx++, id);

            if (sqlite3_step(stmt) != SQLITE_DONE)
            {
                cerr << "Update failed: " << sqlite3_errmsg(db) << endl;
            }
            sqlite3_finalize(stmt);
        }
    }

    void delete_note(int id)
    {
        sqlite3_stmt *stmt;
        const char *sql = "DELETE FROM notes WHERE note_id = ?;";
        if (sqlite3_prepare_v2(db, sql, -1, &stmt, 0) == SQLITE_OK)
        {
            sqlite3_bind_int(stmt, 1, id);
            if (sqlite3_step(stmt) != SQLITE_DONE)
            {
                cerr << "Delete failed: " << sqlite3_errmsg(db) << endl;
            }
            sqlite3_finalize(stmt);
        }
    }

    void delete_folder(int folder_id)
    {
        sqlite3_stmt *stmt;
        const char *folders_sql = "DELETE FROM folders WHERE folder_id = ?;";
        const char *notes_sql = "DELETE FROM notes WHERE folder_id = ?;";

        if (sqlite3_prepare_v2(db, notes_sql, -1, &stmt, 0) == SQLITE_OK)
        {
            sqlite3_bind_int(stmt, 1, folder_id);
            if (sqlite3_step(stmt) != SQLITE_DONE)
                cerr << "Note deletion failed! " << sqlite3_errmsg(db) << endl;
            sqlite3_finalize(stmt);
        }

        if (sqlite3_prepare_v2(db, folders_sql, -1, &stmt, 0) == SQLITE_OK)
        {
            sqlite3_bind_int(stmt, 1, folder_id);
            if (sqlite3_step(stmt) != SQLITE_DONE)
                cerr << "Folder deletion failed! " << sqlite3_errmsg(db) << endl;
            sqlite3_finalize(stmt);
        }
    }
    vector<MiniNote> get_all_mini_notes()
    {
        vector<MiniNote> notes;
        sqlite3_stmt *stmt;
        const char *sql = "SELECT note_id, folder_id, title, created_at, updated_at FROM notes;";
        if (sqlite3_prepare_v2(db, sql, -1, &stmt, 0) == SQLITE_OK)
        {
            while (sqlite3_step(stmt) == SQLITE_ROW)
            {
                MiniNote n;
                n.note_id = sqlite3_column_int(stmt, 0);
                n.folder_id = sqlite3_column_int(stmt, 1);
                const unsigned char *t = sqlite3_column_text(stmt, 2);
                n.title = t ? reinterpret_cast<const char *>(t) : "";
                const unsigned char *ca = sqlite3_column_text(stmt, 3);
                n.created_at = ca ? reinterpret_cast<const char *>(ca) : "";
                const unsigned char *ua = sqlite3_column_text(stmt, 4);
                n.updated_at = ua ? reinterpret_cast<const char *>(ua) : "";
                notes.emplace_back(n);
            }
        }
        sqlite3_finalize(stmt);
        return notes;
    }

    vector<Note> get_all_notes()
    {
        vector<Note> notes;
        sqlite3_stmt *stmt;
        const char *sql = "SELECT note_id, folder_id, title, content, is_markdown, created_at, updated_at FROM notes ORDER BY updated_at DESC, note_id DESC;";
        if (sqlite3_prepare_v2(db, sql, -1, &stmt, 0) == SQLITE_OK)
        {
            while (sqlite3_step(stmt) == SQLITE_ROW)
            {
                Note note;
                note.id = sqlite3_column_int(stmt, 0);
                note.folder_id = sqlite3_column_int(stmt, 1);
                const unsigned char *title = sqlite3_column_text(stmt, 2);
                const unsigned char *content = sqlite3_column_text(stmt, 3);
                note.title = title ? reinterpret_cast<const char *>(title) : "";
                note.content = content ? reinterpret_cast<const char *>(content) : "";
                note.is_md = sqlite3_column_int(stmt, 4) != 0;
                const unsigned char *created_at = sqlite3_column_text(stmt, 5);
                const unsigned char *updated_at = sqlite3_column_text(stmt, 6);
                note.created_at = created_at ? reinterpret_cast<const char *>(created_at) : "";
                note.updated_at = updated_at ? reinterpret_cast<const char *>(updated_at) : "";
                notes.emplace_back(note);
            }
        }
        sqlite3_finalize(stmt);
        return notes;
    }

    vector<Folder> get_all_folders()
    {
        vector<Folder> folders;
        sqlite3_stmt *stmt;
        const char *sql = "SELECT folder_id, name, parent_id, created_at, updated_at FROM folders;";
        if (sqlite3_prepare_v2(db, sql, -1, &stmt, 0) == SQLITE_OK)
        {
            while (sqlite3_step(stmt) == SQLITE_ROW)
            {
                Folder f;
                f.id = sqlite3_column_int(stmt, 0);
                const unsigned char *n = sqlite3_column_text(stmt, 1);
                f.name = n ? reinterpret_cast<const char *>(n) : "";
                f.parent_id = sqlite3_column_int(stmt, 2);
                const unsigned char *ca = sqlite3_column_text(stmt, 3);
                f.created_at = ca ? reinterpret_cast<const char *>(ca) : "";
                const unsigned char *ua = sqlite3_column_text(stmt, 4);
                f.updated_at = ua ? reinterpret_cast<const char *>(ua) : "";
                folders.emplace_back(f);
            }
        }
        sqlite3_finalize(stmt);
        return folders;
    }
};
PYBIND11_MODULE(secure_storage, m)
{
    py::class_<Note>(m, "Note")
        .def_readonly("id", &Note::id)
        .def_readonly("folder_id", &Note::folder_id)
        .def_readonly("title", &Note::title)
        .def_readonly("content", &Note::content)
        .def_readonly("is_markdown", &Note::is_md)
        .def_readonly("created_at", &Note::created_at)
        .def_readonly("updated_at", &Note::updated_at);

    py::class_<MiniNote>(m, "MiniNote")
        .def_readonly("note_id", &MiniNote::note_id)
        .def_readonly("folder_id", &MiniNote::folder_id)
        .def_readonly("title", &MiniNote::title)
        .def_readonly("created_at", &MiniNote::created_at)
        .def_readonly("updated_at", &MiniNote::updated_at);

    py::class_<Folder>(m, "Folder")
        .def_readonly("id", &Folder::id)
        .def_readonly("name", &Folder::name)
        .def_readonly("parent_id", &Folder::parent_id)
        .def_readonly("created_at", &Folder::created_at)
        .def_readonly("updated_at", &Folder::updated_at);

    py::class_<DbOperations>(m, "DbOperations")
        .def(py::init<const string &>())
        .def("connect", &DbOperations::connect)
        .def("connect_readonly", &DbOperations::connect_readonly)
        .def("close", &DbOperations::close)
        .def("add_note", &DbOperations::add_note,
             py::arg("title"), py::arg("content"), py::arg("is_md"), py::arg("folder_id") = 0)
        .def("add_folder", &DbOperations::add_folder,
             py::arg("name"), py::arg("parent_id") = 0)
        .def("update_note", &DbOperations::update_note,
             py::arg("id"),
             py::arg("title") = py::none(),
             py::arg("content") = py::none(),
             py::arg("is_md") = py::none(),
             py::arg("folder_id") = py::none())
        .def("delete_note", &DbOperations::delete_note)
        .def("delete_folder", &DbOperations::delete_folder)
        .def("get_all_mini_notes", &DbOperations::get_all_mini_notes)
        .def("get_all_notes", &DbOperations::get_all_notes)
        .def("get_all_folders", &DbOperations::get_all_folders);
}
