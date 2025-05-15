import sqlite3
from datetime import datetime
import json
import os

class Database:
    def __init__(self, db_file='websites.db'):
        self.db_file = db_file
        self._create_tables()

    def _create_tables(self):
        """Create necessary database tables if they don't exist"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
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
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_config (
                admin_id TEXT PRIMARY KEY,
                notify_on_changes BOOLEAN DEFAULT TRUE,
                notify_on_errors BOOLEAN DEFAULT TRUE
            )
        ''')
        
        conn.commit()
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
