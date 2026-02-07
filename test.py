import secure_storage as ss
import os
db = ss.DbOperation(os.cwd())
password= "Check1234"
if db.connect(password):
    print("connecion successful!")
else:
    print("error")