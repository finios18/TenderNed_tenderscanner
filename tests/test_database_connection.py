import os
import unittest
from unittest.mock import patch

import psycopg

from scanner_database import DatabaseError, connect_database, connection_error_message


class ConnectionDiagnosticsTests(unittest.TestCase):
    def test_driver_errors_are_classified_without_exposing_driver_text(self):
        cases = {
            "FATAL: Tenant or user not found": "DB_PROJECT",
            "FATAL: password authentication failed for user": "DB_AUTH",
            "role is not permitted to log in": "DB_LOGIN",
            "Circuit breaker open: too many authentication errors": "DB_AUTH_LIMIT",
            "could not translate host name": "DB_DNS",
            "connection timeout expired": "DB_TIMEOUT",
            "SSL certificate verify failed": "DB_TLS",
            "connection refused": "DB_NETWORK",
            "FATAL: database does not exist": "DB_NAME",
            "too many connections": "DB_CAPACITY",
            "no pg_hba.conf entry": "DB_ACCESS",
            "invalid percent-encoded token": "DB_URI",
            "unexpected unknown error": "DB_CONNECTION",
        }
        for driver_message, code in cases.items():
            with self.subTest(code=code):
                result = connection_error_message(psycopg.OperationalError(driver_message + " PRIVATE-PASSWORD-123"))
                self.assertTrue(result.startswith(code + ":"), result)
                self.assertNotIn("PRIVATE-PASSWORD-123", result)

    def test_sqlstate_is_used_without_printing_server_message(self):
        class Rejected(Exception):
            sqlstate = "28P01"
        self.assertTrue(connection_error_message(Rejected("private message")).startswith("DB_AUTH:"))

    def test_bad_pooler_user_port_or_password_encoding_fails_before_connection(self):
        cases = [
            ("postgresql://postgres.ref:PRIVATE@aws-1-eu-west-1.pooler.supabase.com:5432/postgres", "DB_USER"),
            ("postgresql://scanner_worker:PRIVATE@aws-1-eu-west-1.pooler.supabase.com:5432/postgres", "DB_USER"),
            ("postgresql://scanner_worker.ref:PRIVATE@aws-1-eu-west-1.pooler.supabase.com:6543/postgres", "DB_PORT"),
            ("postgresql://scanner_worker.ref:PRIVATE@raw@aws-1-eu-west-1.pooler.supabase.com:5432/postgres", "DB_URI"),
            ("postgresql://scanner_worker.ref:PRIVATE%raw@aws-1-eu-west-1.pooler.supabase.com:5432/postgres", "DB_URI"),
        ]
        for uri, code in cases:
            with self.subTest(code=code), patch.dict(os.environ, {"SCANNER_DATABASE_URL": uri}), \
                    patch("scanner_database.psycopg.connect") as connect:
                with self.assertRaises(DatabaseError) as result:
                    connect_database()
                self.assertTrue(str(result.exception).startswith(code + ":"))
                self.assertNotIn("PRIVATE", str(result.exception))
                connect.assert_not_called()

    def test_real_driver_failure_is_wrapped_in_safe_message(self):
        uri = "postgresql://scanner_worker.ref:PRIVATE@aws-1-eu-west-1.pooler.supabase.com:5432/postgres?sslmode=require"
        with patch.dict(os.environ, {"SCANNER_DATABASE_URL": uri}), patch("scanner_database.psycopg.connect", side_effect=psycopg.OperationalError("password authentication failed PRIVATE")):
            with self.assertRaises(DatabaseError) as result:
                connect_database()
            self.assertTrue(str(result.exception).startswith("DB_AUTH:"))
            self.assertNotIn("PRIVATE", str(result.exception))
