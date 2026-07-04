import sqlite3
import logging
from urllib.parse import urlparse
import pandas as pd
from src.config import DB_URI

logger = logging.getLogger(__name__)

class DatabaseManager:
    """
    Manages database connections and operations for the Pharma Safety Pipeline.
    Supports SQLite out-of-the-box, and PostgreSQL if configured.
    """
    def __init__(self, db_uri: str = DB_URI):
        self.db_uri = db_uri
        self.is_postgres = db_uri.startswith(("postgresql://", "postgres://"))
        
        # If Postgres, check if psycopg2 is installed
        if self.is_postgres:
            try:
                import psycopg2  # noqa: F401
            except ImportError:
                logger.warning(
                    "PostgreSQL URI provided but 'psycopg2' is not installed. "
                    "Falling back to local SQLite database."
                )
                self.is_postgres = False
                # Reset DB_URI to local sqlite file
                from src.config import GOLD_DIR
                self.db_uri = f"sqlite:///{GOLD_DIR / 'safety_signals.db'}"

    def get_connection(self):
        """Returns a database connection based on the configured URI."""
        if self.is_postgres:
            import psycopg2
            # Extract parameters from URI
            result = urlparse(self.db_uri)
            username = result.username
            password = result.password
            database = result.path[1:]
            hostname = result.hostname
            port = result.port
            return psycopg2.connect(
                database=database,
                user=username,
                password=password,
                host=hostname,
                port=port
            )
        else:
            # SQLite connection
            db_path = self.db_uri.replace("sqlite:///", "")
            return sqlite3.connect(db_path)

    def execute_non_query(self, query: str, params: tuple = None):
        """Executes a query that does not return rows (e.g. CREATE TABLE, INSERT)."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            conn.commit()
        finally:
            conn.close()

    def execute_query(self, query: str, params: tuple = None) -> pd.DataFrame:
        """Executes a SELECT query and returns a pandas DataFrame."""
        conn = self.get_connection()
        try:
            if params:
                return pd.read_sql_query(query, conn, params=params)
            else:
                return pd.read_sql_query(query, conn)
        finally:
            conn.close()

    def save_dataframe(self, df: pd.DataFrame, table_name: str, if_exists: str = "replace"):
        """Saves a pandas DataFrame to the specified table, preserving explicit schema constraints."""
        conn = self.get_connection()
        try:
            # Handle 'replace' by deleting rows instead of dropping table
            if if_exists == "replace":
                try:
                    cursor = conn.cursor()
                    cursor.execute(f"DELETE FROM {table_name}")
                    conn.commit()
                except Exception:
                    # Table might not exist yet, which is fine
                    pass
                # Switch to append since we cleared the data
                load_mode = "append"
            else:
                load_mode = if_exists
                
            if self.is_postgres:
                try:
                    from sqlalchemy import create_engine
                    # Convert postgres:// to postgresql:// for SQLAlchemy compatibility
                    sqlalchemy_uri = self.db_uri
                    if sqlalchemy_uri.startswith("postgres://"):
                        sqlalchemy_uri = sqlalchemy_uri.replace("postgres://", "postgresql://", 1)
                    engine = create_engine(sqlalchemy_uri)
                    df.to_sql(table_name, engine, if_exists=load_mode, index=False)
                except ImportError:
                    # Fallback manual insert for postgres
                    self._save_postgres_manual(df, table_name, load_mode)
            else:
                df.to_sql(table_name, conn, if_exists=load_mode, index=False)
        finally:
            conn.close()

    def _save_postgres_manual(self, df: pd.DataFrame, table_name: str, if_exists: str):
        """Fallback manual insert for postgres database when sqlalchemy is not available."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            if if_exists == "replace":
                cursor.execute(f"DELETE FROM {table_name};")
                load_mode = "append"
            else:
                load_mode = if_exists
            
            # Simple schema inference (only creates if not exists)
            cols = []
            for col, dtype in zip(df.columns, df.dtypes):
                col_name = f'"{col}"'
                if "int" in str(dtype):
                    col_type = "INTEGER"
                elif "float" in str(dtype):
                    col_type = "DOUBLE PRECISION"
                else:
                    col_type = "TEXT"
                cols.append(f"{col_name} {col_type}")
            
            create_sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(cols)});"
            cursor.execute(create_sql)
            
            # Insert values in bulk
            columns = ", ".join([f'"{c}"' for c in df.columns])
            placeholders = ", ".join(["%s"] * len(df.columns))
            insert_sql = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders});"
            
            tuples = [tuple(x) for x in df.to_numpy()]
            cursor.executemany(insert_sql, tuples)
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def initialize_schema(self, force: bool = False):
        """Initializes the database schema if tables do not exist. If force is True, drops tables first."""
        if force:
            logger.info("Re-creation forced. Dropping existing tables to refresh schemas...")
            self.execute_non_query("DROP TABLE IF EXISTS reports;")
            self.execute_non_query("DROP TABLE IF EXISTS report_drugs;")
            self.execute_non_query("DROP TABLE IF EXISTS report_reactions;")
            self.execute_non_query("DROP TABLE IF EXISTS safety_signals;")

        # Reports Table
        self.execute_non_query("""
            CREATE TABLE IF NOT EXISTS reports (
                case_id TEXT PRIMARY KEY,
                case_version INTEGER,
                received_date TEXT,
                age REAL,
                sex TEXT,
                country TEXT,
                seriousness INTEGER,
                serious_outcome TEXT
            )
        """)
        
        # Report Drugs Table
        self.execute_non_query("""
            CREATE TABLE IF NOT EXISTS report_drugs (
                case_id TEXT,
                drug_name TEXT,
                role TEXT
            )
        """)
        
        # Report Reactions Table
        self.execute_non_query("""
            CREATE TABLE IF NOT EXISTS report_reactions (
                case_id TEXT,
                reaction_name TEXT
            )
        """)
        
        # Safety Signals Table
        self.execute_non_query("""
            CREATE TABLE IF NOT EXISTS safety_signals (
                drug_name TEXT,
                reaction_name TEXT,
                a INTEGER,
                b INTEGER,
                c INTEGER,
                d INTEGER,
                N_drug INTEGER,
                N_event INTEGER,
                prr REAL,
                chi2 REAL,
                ror REAL,
                ror_ci_lower REAL,
                ror_ci_upper REAL,
                is_signal INTEGER,
                PRIMARY KEY (drug_name, reaction_name)
            )
        """)
        logger.info("Database schema initialized successfully.")
