#include<pybind11/pybind11.h>
#include<pybind11/stl.h>
#include<iostream>
#include<vector>
#include<sstream>
#include <sqlcipher/sqlite3.h>
#include<iomanip>

namespace py = pybind11;
using namespace std;

class DbOperations{
    sqlite3 *db = nullptr;
    string db_path;
    int rc;
    public:
        DbOperations(const string &path): db_path(path){}
        ~DbOperations() { close();}
        void close(){
            if(db){
                sqlite3_close(db);
                db = nullptr;
            }
        }

        // FIXED: name should be const reference
        bool connect(const string &password, const string &name) {
            // FIXED: Ensure path separator exists and add .db extension
            char separator = '/';
            #ifdef _WIN32
                separator = '\\';
            #endif
            
            string full_path = db_path;
            if (!full_path.empty() && full_path.back() != separator) {
                full_path += separator;
            }
            full_path += name + ".db";

            rc = sqlite3_open(full_path.c_str(), &db);
    
    if (rc != SQLITE_OK) {
        cerr << "Cannot open database: " << sqlite3_errmsg(db) << std::endl;
        return false;
    }

    // 1. Apply the key immediately
    rc = sqlite3_key(db, password.c_str(), static_cast<int>(password.size()));
    if (rc != SQLITE_OK) {
        cerr << "Failed to set encryption key" << std::endl;
        close();
        return false;
    }

    // 2. FORCE ENCRYPTION: Create a dummy table if it's a new DB
    // This forces SQLCipher to write the encrypted header to the file.
    char *errMsg = nullptr;
    const char* init_sql = "CREATE TABLE IF NOT EXISTS _sqlcipher_flush (id INTEGER);";
    sqlite3_exec(db, init_sql, nullptr, nullptr, &errMsg);

    // 3. Test access
    rc = sqlite3_exec(db, "SELECT count(*) FROM sqlite_master;", nullptr, nullptr, &errMsg);
    if (rc == SQLITE_OK) {
        cout << "\nC++: Connection established and database encrypted!" << endl;
        return true;
    } else {
        cerr << "\nC++: Authentication failed!" << endl;
        if (errMsg) sqlite3_free(errMsg);
        close();
        return false;
    }
}
};
PYBIND11_MODULE(secure_storage, m ){
    py::class_<DbOperations>(m, "DbOperations")
        .def(py::init<const string &>())
        .def("connect", &DbOperations::connect)
        .def("close", &DbOperations::close);
}
