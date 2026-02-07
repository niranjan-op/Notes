#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <iostream>
#include <vector>
#include <sstream>
#include <iomanip>

#include <openssl/evp.h>
#include <openssl/rand.h>
#include <openssl/crypto.h>

// --- VITAL: Link against vcpkg's library, don't include local file ---
#include "sqlite3.h"

#ifndef SQLITE_HAS_CODEC
#define SQLITE_HAS_CODEC
#endif

namespace py = pybind11;

// --- Helper Functions ---
static std::string hex_encode(const unsigned char* data, size_t len) {
    std::ostringstream ss;
    ss << std::hex << std::setfill('0');
    for (size_t i = 0; i < len; ++i) ss << std::setw(2) << static_cast<int>(data[i]);
    return ss.str();
}

static bool derive_key(const std::string &pass, const std::string &salt_hex, std::string &out_hex) {
    // Decode Hex Salt
    if (salt_hex.size() % 2 != 0) return false;
    std::vector<unsigned char> salt_vec;
    for (size_t i = 0; i < salt_hex.size(); i += 2) {
        unsigned int val;
        std::stringstream ss;
        ss << std::hex << salt_hex.substr(i, 2);
        ss >> val;
        salt_vec.push_back(static_cast<unsigned char>(val));
    }

    std::vector<unsigned char> key(32);
    int rc = PKCS5_PBKDF2_HMAC(pass.c_str(), pass.size(), salt_vec.data(), salt_vec.size(), 
                               200000, EVP_sha256(), 32, key.data());
    
    if (rc != 1) return false;
    out_hex = hex_encode(key.data(), key.size());
    return true;
}

// --- The Python Module Class ---
class SecureDB {
    sqlite3 *db = nullptr;
    std::string db_path;

public:
    SecureDB(const std::string &path) : db_path(path) {}
    
    ~SecureDB() { close(); }

    void close() {
        if (db) {
            sqlite3_close(db);
            db = nullptr;
        }
    }

    // Returns a new salt to Python
    std::string generate_salt() {
        unsigned char salt[16];
        RAND_bytes(salt, sizeof(salt));
        return hex_encode(salt, sizeof(salt));
    }

    void connect(const std::string &password, const std::string &salt_hex) {
        close(); // Ensure clean state

        std::string key_hex;
        if (!derive_key(password, salt_hex, key_hex)) {
            throw std::runtime_error("Key derivation failed");
        }

        if (sqlite3_open(db_path.c_str(), &db) != SQLITE_OK) {
            throw std::runtime_error("Failed to open DB file");
        }

        // Apply Key
        std::string pragma = "PRAGMA key = \"x'" + key_hex + "'\";";
        sqlite3_exec(db, pragma.c_str(), nullptr, nullptr, nullptr);

        // Verify Key by forcing a read
        if (sqlite3_exec(db, "SELECT count(*) FROM sqlite_master;", nullptr, nullptr, nullptr) != SQLITE_OK) {
            close();
            throw std::runtime_error("Decryption failed (Wrong Password?)");
        }
    }

    void execute(const std::string &sql) {
        if (!db) throw std::runtime_error("Database not connected");
        char *errmsg = nullptr;
        if (sqlite3_exec(db, sql.c_str(), nullptr, nullptr, &errmsg) != SQLITE_OK) {
            std::string err = errmsg ? errmsg : "Unknown Error";
            sqlite3_free(errmsg);
            throw std::runtime_error(err);
        }
    }
};

// --- THIS IS THE MISSING PIECE CAUSING LINKER ERRORS ---
PYBIND11_MODULE(pysqlcipher, m) {
    py::class_<SecureDB>(m, "SecureDB")
        .def(py::init<const std::string &>())
        .def("generate_salt", &SecureDB::generate_salt)
        .def("connect", &SecureDB::connect)
        .def("execute", &SecureDB::execute)
        .def("close", &SecureDB::close);
}