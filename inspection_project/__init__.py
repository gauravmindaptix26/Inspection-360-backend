"""
Project package init.

Enables `PyMySQL` as a drop-in replacement for `MySQLdb` when `mysqlclient`
is not installed (common on Windows without build tools).
"""

try:
    import MySQLdb  # type: ignore  # noqa: F401
except (ModuleNotFoundError, ImportError):
    import pymysql

    pymysql.install_as_MySQLdb()
