import os
import dns.resolver
import socket
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import hashlib
import requests
from requests.exceptions import RequestException

class WebsiteMonitor:
    def __init__(self, database):
        self.db = database
        self.setup_selenium()

    def setup_selenium(self):
        """Setup Selenium with Chrome in headless mode"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)

    def add_website(self, url: str, interval: int):
        """Add a new website to monitor"""
        # Initial check
        status = self._check_website(url)
        
        # Store in database
        self.db.add_website({
            'url': url,
            'interval': interval,
            'last_check': datetime.now().isoformat(),
            'last_hash': self._get_page_hash(status['content']),
            'ip': status['ip'],
            'dns': status['dns'],
            'screenshot_path': status['screenshot_path']
        })
        
        return status

    def remove_website(self, url: str):
        """Remove a website from monitoring"""
        self.db.remove_website(url)

    def get_all_websites(self):
        """Get list of all monitored websites"""
        return self.db.get_all_websites()

    def get_website_status(self, url: str):
        """Get current status of a specific website"""
        return self.db.get_website_status(url)

    def check_all_websites(self):
        """Check all websites and return list of anomalies"""
        websites = self.get_all_websites()
        anomalies = []
        
        for website in websites:
            if self._should_check(website):
                status = self._check_website(website['url'])
                if status and self._detect_changes(website, status):
                    anomalies.append({
                        'url': website['url'],
                        'changes': self._get_changes_description(website, status),
                        'timestamp': datetime.now().isoformat(),
                        'screenshot_path': status['screenshot_path']
                    })
                
                # Update database with new status
                if status:
                    self.db.update_website_status(website['url'], status)
        
        return anomalies
    
    def _check_website(self, url: str):
        """Perform complete check of a website"""
        try:
            # Clean up the URL and ensure it has a scheme
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url

            response = requests.get(url, timeout=30)
            content = response.text
            self.last_status_code = response.status_code
            self.last_response_time = response.elapsed.total_seconds()

            # Extract domain from URL
            domain = url.split("//")[-1].split("/")[0]
            
            # Get IP and DNS info with timeout
            ip = socket.getaddrinfo(domain, None, proto=socket.IPPROTO_TCP)[0][4][0]

            # DNS lookup
            dns_info = []
            for qtype in ['A', 'MX', 'NS']:
                try:
                    answers = dns.resolver.resolve(domain, qtype)
                    dns_info.extend([str(rdata) for rdata in answers])
                except Exception:
                    continue
    
            # Take screenshot
            screenshot_path = self._take_screenshot(url)
            
            return {
                'content': content,
                'ip': ip,
                'dns': '\n'.join(dns_info),
                'screenshot_path': screenshot_path,
                'timestamp': datetime.now().isoformat(),
                'status_code': self.last_status_code,  # Add status code
                'response_time': self.last_response_time  # Add response time
            }
            
        except Exception as e:
            print(f"Error checking website {url}: {str(e)}")
            return {
                'status_code': 0,
                'response_time': 0,
                'timestamp': datetime.now().isoformat(),
                'technical_details': str(e)
            }

    def _take_screenshot(self, url: str):
        """Take a screenshot of the website with improved full-page capture"""
        try:
            screenshots_dir = 'screenshots'
            os.makedirs(screenshots_dir, exist_ok=True)
            
            filename = f"{hashlib.md5(url.encode()).hexdigest()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            filepath = os.path.join(screenshots_dir, filename)
            
            # Set desktop viewport
            self.driver.set_window_size(1920, 1080)
            self.driver.get(url)
            self.driver.implicitly_wait(10)
            
            # Get full page dimensions
            height = self.driver.execute_script("return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight, document.body.offsetHeight, document.documentElement.offsetHeight);")
            width = self.driver.execute_script("return Math.max(document.body.scrollWidth, document.documentElement.scrollWidth, document.body.offsetWidth, document.documentElement.offsetWidth);")
            
            # Set viewport to full content size
            self.driver.set_window_size(width + 100, height + 100)
            
            # Additional wait for dynamic content
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            self.driver.execute_script("window.scrollTo(0, 0);")
            
            # Take screenshot
            self.driver.save_screenshot(filepath)
            return filepath
        except Exception as e:
            print(f"Error taking screenshot: {str(e)}")
            return None

    def _get_page_hash(self, content: str):
        """Generate hash of page content"""
        soup = BeautifulSoup(content, 'html.parser')
        # Remove dynamic elements that change frequently
        for elem in soup.find_all(['script', 'style']):
            elem.decompose()
        return hashlib.md5(str(soup).encode()).hexdigest()

    def _should_check(self, website):
        """Determine if website should be checked based on interval"""
        last_check = datetime.fromisoformat(website['last_check'])
        elapsed = (datetime.now() - last_check).total_seconds() / 60
        return elapsed >= website['interval']

    def _detect_changes(self, website, new_status):
        """Detect if there are significant changes in the website"""
        changes = {
            'dns_changed': False,
            'ip_changed': False,
            'content_changed': False,
            'high_latency': False,
            'status_code_error': False,
            'technical_details': []
        }

        # Check IP changes
        if website.get('ip') != new_status['ip']:
            changes['ip_changed'] = True
            changes['technical_details'].append(f"IP changed: {website.get('ip')} → {new_status['ip']}")

        # Check DNS changes
        if website.get('dns') != new_status['dns']:
            changes['dns_changed'] = True
            changes['technical_details'].append("DNS records modified")

        # Check response time
        if hasattr(self, 'last_response_time') and self.last_response_time > 5:  # 5 seconds threshold
            changes['high_latency'] = True
            changes['technical_details'].append(f"High latency detected: {self.last_response_time:.2f}s")

        # Check status code
        if hasattr(self, 'last_status_code') and self.last_status_code >= 400:
            changes['status_code_error'] = True
            changes['technical_details'].append(f"Server error: HTTP {self.last_status_code}")

        # Check content changes
        old_hash = website.get('last_hash')
        new_hash = self._get_page_hash(new_status['content'])
        if old_hash != new_hash:
            changes['content_changed'] = True
            changes['technical_details'].append("Content structure has changed")

        # Update the anomaly detection data
        new_status.update(changes)
        new_status['technical_details'] = "\n".join(changes['technical_details'])

        return any([changes['dns_changed'], changes['ip_changed'], 
                   changes['content_changed'], changes['high_latency'],
                   changes['status_code_error']])

    def _get_changes_description(self, website, new_status):
        """Generate description of changes"""
        changes = []
        
        # Check IP changes
        if website.get('ip') != new_status['ip']:
            changes.append(f"IP changed from {website['ip']} to {new_status['ip']}")
        
        # Check DNS changes
        if website.get('dns') != new_status['dns']:
            changes.append("DNS records have changed")
        
        # Content changes
        if self._detect_changes(website, new_status):
            changes.append("Website content has changed")
        
        return "\n".join(changes) if changes else "No significant changes detected"
