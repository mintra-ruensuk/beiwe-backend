from db.mongolia_setup import DatabaseObject, DatabaseCollection
from mongolia.constants import REQUIRED_STRING, REQUIRED, REQUIRED_INT, REQUIRED_LIST, REQUIRED_DATETIME

from libs.security import decode_base64

PADDING_ERROR = "PADDING_ERROR"
MP4_PADDING = "MP4_PADDING"
EMPTY_KEY = "EMPTY_KEY"
MALFORMED_CONFIG = "MALFORMED_CONFIG"
IV_MISSING = "IV_MISSING"
LINE_EMPTY = "LINE_EMPTY"
LINE_IS_NONE = "LINE_EMPTY"
INVALID_LENGTH = "INVALID_LENGTH"
AES_KEY_BAD_LENGTH = "AES_KEY_BAD_LENGTH"
IV_BAD_LENGTH = "IV_BAD_LENGTH"

class EncryptionErrorMetadata(DatabaseObject):
    PATH = "beiwe.encryption_error_metadata"
    
    DEFAULTS = {
        "file_name":REQUIRED_STRING,
        "total_lines":REQUIRED_INT,
        "number_errors":REQUIRED_INT,
        "errors_lines":REQUIRED_LIST,
        "error_types":REQUIRED_LIST
    }
    
    
class LineEncryptionError(DatabaseObject):
    PATH = "beiwe.line_encryption_errors"

    DEFAULTS = {
        "type": REQUIRED_STRING,
        "line":REQUIRED_STRING,
        "base64_decryption_key": REQUIRED_STRING,
        "prev_line": "",
        "next_line": ""
    }
    
    
class DecryptionKeyError(DatabaseObject):
    PATH = "beiwe.decryption_key_error"
    
    DEFAULTS = {
        "file_path": REQUIRED_STRING,
        "contents": REQUIRED,
        "user_id": REQUIRED_STRING
    }
    
    def decode(self):
        return decode_base64(self.contents)
    
    # def decrypt(self):
    #     from libs.s3 import get_client_private_key
    #     private_key = get_client_private_key(self.user_id, User(self.user_id).study_id)
    #     return private_key.decrypt( self.decode() )


class UploadTracking(DatabaseObject):
    PATH = "beiwe.upload_tracking"
    
    DEFAULTS = {
        "file_path": REQUIRED_STRING,
        "timestamp": REQUIRED_DATETIME,
        "user_id": REQUIRED_STRING,
        "file_size": None
    }
    
class EncryptionErrorMetadatas(DatabaseCollection):
    OBJTYPE = EncryptionErrorMetadata

class DecryptionKeyErrors(DatabaseCollection):
    OBJTYPE = DecryptionKeyError

class LineEncryptionErrors(DatabaseCollection):
    OBJTYPE = LineEncryptionError

class Uploads(DatabaseCollection):
    OBJTYPE = UploadTracking