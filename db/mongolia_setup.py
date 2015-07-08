from mongolia import (connect_to_database, authenticate_connection, ID_KEY,
    REQUIRED, UPDATE, CHILD_TEMPLATE, DatabaseObject, DatabaseCollection)

from mongolia.errors import MalformedObjectError, DatabaseConflictError
from config.passwords import MONGO_USERNAME, MONGO_PASSWORD

# We are specifying the default database, see the mongolia documentation if you
# use a non-default configuration.

connect_to_database()
authenticate_connection(MONGO_USERNAME, MONGO_PASSWORD)