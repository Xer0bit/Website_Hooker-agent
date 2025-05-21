import sqlite3
import os

class Database:
    def __init__(self):
        self.data_dir = os.environ.get('DATA_DIR', 'data')  # Default to local 'data' directory
        try:
            if not os.path.exists(self.data_dir):
                os.makedirs(self.data_dir, exist_ok=True)
        except Exception as e:
            print(f"Warning: Could not create data directory: {e}")
            self.data_dir = '.'  # Fallback to current directory
        
        self.db_file = os.path.join(self.data_dir, 'websites.db')
        self._create_tables()

    def _create_tables(self):
        """Create necessary database tables if they don't exist"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_file)
            cursor = conn.cursor()
            
            # Create websites table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS websites (
                    url TEXT PRIMARY KEY,
                    interval INTEGER,
                    last_check TEXT,
                    last_hash TEXT,
                    ip TEXT,
                    dns TEXT,
                    screenshot_path TEXT
                )
            ''')
            
            # Create admin_config table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS admin_config (
                    admin_id TEXT PRIMARY KEY,
                    notify_on_changes BOOLEAN DEFAULT TRUE,
                    notify_on_errors BOOLEAN DEFAULT TRUE
                )
            ''')
            
            # Create website_checks table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS website_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT,
                    timestamp TEXT,
                    status_code INTEGER,
                    response_time REAL,
                    error_message TEXT,
                    FOREIGN KEY(url) REFERENCES websites(url)
                )
            ''')
            
            conn.commit()
            
        except sqlite3.Error as e:
            print(f"SQLite error: {e}")
            raise
        except Exception as e:
            print(f"Error creating tables: {e}")
            raise
        finally:
            if conn:
                conn.close()

    def add_website(self, website_data):
        """Add a new website to the database"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO websites 
            (url, interval, last_check, last_hash, ip, dns, screenshot_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            website_data['url'],
            website_data['interval'],
            website_data['last_check'],
            website_data['last_hash'],
            website_data['ip'],
            website_data['dns'],
            website_data['screenshot_path']
        ))
        
        conn.commit()
        conn.close()

    def remove_website(self, url):
        """Remove a website from the database"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM websites WHERE url = ?', (url,))
        
        conn.commit()
        conn.close()

    def get_all_websites(self):
        """Get all monitored websites"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM websites')
        columns = [description[0] for description in cursor.description]
        websites = []
        
        for row in cursor.fetchall():
            website = dict(zip(columns, row))
            websites.append(website)
        
        conn.close()
        return websites

    def get_website_status(self, url):
        """Get status of a specific website"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM websites WHERE url = ?', (url,))
        columns = [description[0] for description in cursor.description]
        row = cursor.fetchone()
        
        conn.close()
        
        if row:
            return dict(zip(columns, row))
        return None

    def update_website_status(self, url, status):
        """Update website status in the database"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE websites 
            SET last_check = ?, last_hash = ?, ip = ?, dns = ?, screenshot_path = ?
            WHERE url = ?
        ''', (
            status['timestamp'],
            status.get('last_hash', ''),
            status['ip'],
            status['dns'],
            status['screenshot_path'],
            url
        ))
        
        conn.commit()
        conn.close()

    def add_admin(self, admin_id: str):
        """Add an admin to the configuration"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('INSERT OR IGNORE INTO admin_config (admin_id) VALUES (?)', (admin_id,))
        conn.commit()
        conn.close()

    def remove_admin(self, admin_id: str):
        """Remove an admin from the configuration"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM admin_config WHERE admin_id = ?', (admin_id,))
        conn.commit()
        conn.close()

    def get_admins(self):
        """Get list of all admin configurations"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM admin_config')
        admins = cursor.fetchall()
        conn.close()
        return [{'admin_id': row[0], 'notify_on_changes': row[1], 'notify_on_errors': row[2]} for row in admins]

    def get_recent_checks(self, url: str, hours: int = 24):
        """Get recent checks for a website"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        # Get checks from the last X hours
        cursor.execute('''
            SELECT * FROM website_checks 
            WHERE url = ? AND timestamp > datetime('now', '-' || ? || ' hours')
            ORDER BY timestamp DESC
        ''', (url, hours))
        
        checks = cursor.fetchall()
        conn.close()
        
        return checks if checks else []

    def add_check_history(self, url: str, check_data: dict):
        """Add a check result to history"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO website_checks 
            (url, timestamp, status_code, response_time, error_message)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            url,
            check_data['timestamp'],
            check_data['status_code'],
            check_data['response_time'],
            check_data.get('technical_details', '')
        ))
        
        conn.commit()
        conn.close()

    def get_site_status_history(self, url: str, hours: int = 24):
        """Get site status history for the last X hours"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT timestamp, status_code, response_time, error_message
            FROM website_checks
            WHERE url = ? AND timestamp > datetime('now', '-' || ? || ' hours')
            ORDER BY timestamp DESC
        ''', (url, hours))
        
        history = cursor.fetchall()
        conn.close()
        
        return [{
            'timestamp': row[0],
            'status_code': row[1],
            'response_time': row[2],
            'error_message': row[3]
        } for row in history]
