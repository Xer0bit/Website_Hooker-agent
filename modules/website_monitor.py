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
import pytz

class WebsiteMonitor:
    def __init__(self, database):
        self.db = database
        self.setup_selenium()
        self.consecutive_failures = {}  # Track consecutive failures per site
        self.alert_threshold = 3  # Alert after 3 consecutive failures

    def setup_selenium(self):
        """Setup Selenium with Chrome in headless mode"""
        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--disable-software-rasterizer')
            chrome_options.add_argument('--disable-extensions')
            chrome_options.add_argument('--window-size=1920,1080')
            
            # Use local ChromeDriver
            driver_path = '/usr/local/bin/chromedriver'
            service = Service(driver_path)
            
            self.driver = webdriver.Chrome(
                service=service,
                options=chrome_options
            )
            print("Selenium setup completed successfully")
        except Exception as e:
            print(f"Error setting up Selenium: {e}")
            self.driver = None

    def add_website(self, url: str, interval: int):
        """Add a new website to monitor"""
        try:
            # Initial check
            status = self._check_website(url)
            
            # Store in database with safe defaults if check fails
            website_data = {
                'url': url,
                'interval': interval,
                'last_check': datetime.now().isoformat(),
                'last_hash': self._get_page_hash(status.get('content', '')),
                'ip': status.get('ip', 'Unknown'),
                'dns': status.get('dns', 'Unknown'),
                'screenshot_path': status.get('screenshot_path')
            }
            
            self.db.add_website(website_data)
            return status
            
        except Exception as e:
            raise Exception(f"Failed to add website: {str(e)}")

    def remove_website(self, url: str):
        """Remove a website from monitoring"""
        self.db.remove_website(url)

    def get_all_websites(self):
        """Get list of all monitored websites"""
        return self.db.get_all_websites()

    def get_website_status(self, url: str):
        """Get current status of a specific website with fresh check"""
        try:
            # Get current status from db
            stored_status = self.db.get_website_status(url)
            if not stored_status:
                return None

            # Perform a fresh check
            current_status = self._check_website(url)
            
            # Update database with new status
            self.db.update_website_status(url, current_status)
            
            # Merge stored and current status
            stored_status.update(current_status)
            return stored_status
            
        except Exception as e:
            print(f"Error checking website {url}: {str(e)}")
            return {
                'error': str(e),
                'url': url,
                'status_code': 0,
                'response_time': 0,
                'timestamp': datetime.now().isoformat(),
                'error_type': 'check_error'
            }

    def _check_website(self, url: str):
        """Enhanced website check with failure tracking"""
        try:
            # Clean up URL
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url

            start_time = datetime.now()
            response = requests.get(url, timeout=30, verify=True)
            domain = url.split("//")[-1].split("/")[0]
            
            # Reset failure counter on success
            if response.status_code < 400:
                self.consecutive_failures[url] = 0
                
            # Get status info
            status_info = self._get_status_info(response.status_code)
            ip_info = socket.getaddrinfo(domain, None)
            ip = ip_info[0][4][0]
            
            # DNS lookups
            dns_info = self._get_dns_info(domain)
            
            result = {
                'content': response.text,
                'ip': ip,
                'dns': '\n'.join(dns_info),
                'timestamp': datetime.now().isoformat(),
                'status_code': response.status_code,
                'response_time': (datetime.now() - start_time).total_seconds(),
                'screenshot_path': self._take_screenshot(url),
                'requires_attention': status_info['requires_attention'],
                'consecutive_failures': self.consecutive_failures.get(url, 0),
                'availability': {
                    'reachable': status_info['is_ok'],
                    'status': status_info['message'],
                    'response_ok': status_info['is_ok'],
                    'status_color': status_info['color'],
                    'error_type': status_info['error_type']
                },
                'technical_details': status_info['details']
            }
            
            # Track the check in history
            self._update_check_history(url, result)
            
            return result

        except Exception as e:
            # Increment failure counter
            self.consecutive_failures[url] = self.consecutive_failures.get(url, 0) + 1
            
            error_response = self._create_error_response(url, str(e))
            error_response['consecutive_failures'] = self.consecutive_failures[url]
            error_response['requires_attention'] = self.consecutive_failures[url] >= self.alert_threshold
            
            # Track the failure in history
            self._update_check_history(url, error_response)
            
            return error_response

    def _create_error_response(self, url: str, error_message: str):
        """Create standardized error response"""
        return {
            'content': '',
            'ip': 'Unknown',
            'dns': 'Unknown',
            'timestamp': datetime.now().isoformat(),
            'status_code': 0,
            'response_time': 0,
            'screenshot_path': None,
            'error_message': error_message,
            'availability': {
                'reachable': False,
                'status': 'Offline',
                'error': error_message
            },
            'technical_details': error_message
        }

    def _take_screenshot(self, url: str):
        """Take a screenshot with fallback"""
        if not self.driver:
            print("Screenshot failed: Selenium driver not available")
            return None
            
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
        try:
            last_check = datetime.fromisoformat(website['last_check'])
            if not last_check.tzinfo:
                last_check = pytz.UTC.localize(last_check)
            now = datetime.now(pytz.UTC)
            elapsed = (now - last_check).total_seconds() / 60
            # Use the website's configured interval (default 30 minutes)
            interval = website.get('interval', 30)
            return elapsed >= interval
        except Exception:
            return True  # Check if there's an error parsing time

    def initial_check_website(self, url: str):
        """Perform thorough initial check of a website"""
        try:
            status = self._check_website(url)
            status['technical_details'] = "Initial check completed successfully"
            return status
        except Exception as e:
            return {'error': str(e), 'technical_details': f"Initial check failed: {str(e)}"}

    def _detect_changes(self, website, new_status):
        """Enhanced change detection with criticality assessment"""
        changes = {
            'dns_changed': False,
            'ip_changed': False,
            'content_changed': False,
            'high_latency': False,
            'status_code_error': False,
            'critical_changes': False,
            'technical_details': []
        }

        # Check for critical changes first
        current_status_code = new_status.get('status_code', 0)
        if current_status_code >= 500:
            changes['status_code_error'] = True
            changes['critical_changes'] = True
            changes['technical_details'].append(f"⚠️ Server Error (HTTP {current_status_code})")
        elif current_status_code >= 400:
            changes['status_code_error'] = True
            changes['technical_details'].append(f"Warning: Client Error (HTTP {current_status_code})")

        # Check IP changes
        if website.get('ip') != new_status.get('ip'):
            changes['ip_changed'] = True
            changes['critical_changes'] = True
            changes['technical_details'].append(f"IP changed: {website.get('ip')} → {new_status.get('ip')}")

        # Check DNS changes
        if website.get('dns') != new_status.get('dns'):
            changes['dns_changed'] = True
            changes['critical_changes'] = True
            changes['technical_details'].append("DNS records modified")

        # Update status with change information
        new_status.update(changes)
        new_status['technical_details'] = "\n".join(changes['technical_details'])

        return any([
            changes['status_code_error'],
            changes['ip_changed'],
            changes['dns_changed'],
            changes['critical_changes']
        ])

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

    def _check_security(self, url, response):
        """Enhanced security checks"""
        security_info = {
            'has_ssl': False,
            'good_security_headers': True,
            'has_protection': False,
            'technical_details': []
        }
        
        # SSL Check
        try:
            cert = response.raw._connection.sock.getpeercert()
            security_info['has_ssl'] = cert is not None
            if cert:
                security_info['technical_details'].append("✅ Valid SSL certificate")
        except Exception:
            security_info['technical_details'].append("❌ SSL verification failed")
        
        # Security Headers Check
        required_headers = {
            'Strict-Transport-Security': 'HSTS',
            'Content-Security-Policy': 'CSP',
            'X-Content-Type-Options': 'XCTO',
            'X-Frame-Options': 'XFO',
            'X-XSS-Protection': 'XXP'
        }
        
        missing_headers = []
        for header, short_name in required_headers.items():
            if header not in response.headers:
                missing_headers.append(short_name)
                security_info['good_security_headers'] = False
        
        if missing_headers:
            security_info['technical_details'].append(f"Missing security headers: {', '.join(missing_headers)}")
        
        # Check for WAF/Security Protection
        security_headers = [h.lower() for h in response.headers.keys()]
        protection_indicators = ['cf-ray', 'x-sucuri-id', 'x-cdn', 'x-cache']
        security_info['has_protection'] = any(h in security_headers for h in protection_indicators)
        
        if security_info['has_protection']:
            security_info['technical_details'].append("✅ WAF/CDN protection detected")
        
        return security_info

    def _calculate_uptime(self, url):
        """Calculate uptime percentage based on stored checks"""
        try:
            # Get last 24 hours of checks from database
            checks = self.db.get_recent_checks(url, hours=24)
            if not checks:
                return 100.0
            
            successful_checks = sum(1 for check in checks if check.get('status_code', 0) < 400)
            return (successful_checks / len(checks)) * 100
        except:
            return 100.0

    def _get_status_info(self, status_code: int):
        """Enhanced status info with attention flag"""
        base_info = {
            'requires_attention': False,
            'alert_level': 'none'
        }
        
        if status_code == 200:
            return {**base_info, 
                   'is_ok': True, 
                   'message': 'Online',
                   'color': 'green',
                   'error_type': None,
                   'details': 'Website is operating normally'}
        
        # Define error codes that require immediate attention
        critical_errors = {
            500: ('Server Error', 'Critical: Internal server error', 'high'),
            502: ('Bad Gateway', 'Critical: Bad Gateway response', 'high'),
            503: ('Service Unavailable', 'Critical: Service unavailable', 'high'),
            504: ('Gateway Timeout', 'Critical: Gateway timeout', 'high')
        }
        
        warning_errors = {
            400: ('Bad Request', 'Warning: Client error', 'medium'),
            401: ('Unauthorized', 'Warning: Authentication required', 'medium'),
            403: ('Forbidden', 'Warning: Access denied', 'medium'),
            404: ('Not Found', 'Warning: Page not found', 'medium')
        }
        
        if status_code in critical_errors:
            error_type, details, level = critical_errors[status_code]
            return {
                **base_info,
                'is_ok': False,
                'message': f'Error: {error_type}',
                'color': 'red',
                'error_type': 'server_error',
                'details': details,
                'requires_attention': True,
                'alert_level': level
            }
            
        if status_code in warning_errors:
            error_type, details, level = warning_errors[status_code]
            return {
                **base_info,
                'is_ok': False,
                'message': f'Warning: {error_type}',
                'color': 'yellow',
                'error_type': 'client_error',
                'details': details,
                'requires_attention': True,
                'alert_level': level
            }
            
        # Unknown status code
        return {
            **base_info,
            'is_ok': False,
            'message': f'Unknown Status ({status_code})',
            'color': 'red',
            'error_type': 'unknown_error',
            'details': f'Unexpected HTTP status code: {status_code}',
            'requires_attention': True,
            'alert_level': 'medium'
        }

    def calculate_performance_score(self, status):
        """Enhanced performance score calculation with error penalties"""
        try:
            response_time = status.get('response_time', 0)
            status_code = status.get('status_code', 200)
            penalties = 0
            
            # Apply penalties for slow response times
            if response_time > 2:
                penalties += 1
            if response_time > 5:
                penalties += 2
            
            # Apply penalties for error status codes
            if status_code >= 400:
                penalties += 3
            
            # Calculate score
            score = max(0, 10 - penalties)
            return score
        except Exception as e:
            print(f"Error calculating performance score: {str(e)}")
            return 0

    def _get_dns_info(self, domain: str) -> list:
        """Get DNS information for a domain"""
        dns_info = []
        try:
            # Get A records
            try:
                a_records = dns.resolver.resolve(domain, 'A')
                dns_info.extend([f"A: {str(record)}" for record in a_records])
            except Exception:
                pass

            # Get MX records
            try:
                mx_records = dns.resolver.resolve(domain, 'MX')
                dns_info.extend([f"MX: {str(record)}" for record in mx_records])
            except Exception:
                pass

            # Get NS records
            try:
                ns_records = dns.resolver.resolve(domain, 'NS')
                dns_info.extend([f"NS: {str(record)}" for record in ns_records])
            except Exception:
                pass

        except Exception as e:
            print(f"Error getting DNS info for {domain}: {str(e)}")
            dns_info.append("DNS lookup failed")

        return dns_info if dns_info else ["No DNS records found"]

    def _update_check_history(self, url: str, status: dict):
        """Update check history in database"""
        try:
            check_data = {
                'timestamp': status['timestamp'],
                'status_code': status.get('status_code', 0),
                'response_time': status.get('response_time', 0),
                'error_message': status.get('technical_details', ''),
                'requires_attention': status.get('requires_attention', False),
                'consecutive_failures': status.get('consecutive_failures', 0)
            }
            self.db.add_check_history(url, check_data)
        except Exception as e:
            print(f"Error updating check history: {str(e)}")

    def check_all_websites(self):
        """Enhanced periodic check of all websites with proper interval checking"""
        anomalies = []
        try:
            websites = self.get_all_websites()
            print(f"Checking {len(websites)} websites...")
            
            for website in websites:
                if self._should_check(website):
                    print(f"Checking website: {website['url']}")
                    current_status = self._check_website(website['url'])
                    stored_status = self.db.get_website_status(website['url'])

                    # Detect changes and issues
                    has_issues = self._detect_issues(stored_status or {}, current_status)
                    
                    # Update database with new status
                    current_status['last_hash'] = self._get_page_hash(current_status.get('content', ''))
                    self.db.update_website_status(website['url'], current_status)
                    
                    # Report issues
                    if has_issues:
                        anomalies.append({
                            'url': website['url'],
                            'current_status': current_status,
                            'previous_status': stored_status,
                            'issues': self._get_issue_description(current_status)
                        })
                        print(f"Issues detected for {website['url']}: {current_status.get('error_message', 'Unknown issue')}")

        except Exception as e:
            print(f"Error in check_all_websites: {str(e)}")

        return anomalies

    def _detect_issues(self, previous_status, current_status):
        """Detect if there are issues with the website"""
        issues = []
        
        # Check for HTTP errors
        status_code = current_status.get('status_code', 0)
        if status_code >= 400:
            issues.append(f"HTTP Error: {status_code}")
        
        # Check for connection errors
        if current_status.get('error_message'):
            issues.append(f"Connection Error: {current_status['error_message']}")
        
        # Check for high response time
        response_time = current_status.get('response_time', 0)
        if response_time > 10:  # More than 10 seconds
            issues.append(f"Slow Response: {response_time:.2f}s")
        
        # Check for consecutive failures
        consecutive_failures = current_status.get('consecutive_failures', 0)
        if consecutive_failures >= 3:
            issues.append(f"Multiple Failures: {consecutive_failures} consecutive")
        
        # Check for IP changes (if we have previous data)
        if previous_status and previous_status.get('ip') != current_status.get('ip'):
            if previous_status.get('ip') != 'Unknown' and current_status.get('ip') != 'Unknown':
                issues.append(f"IP Changed: {previous_status.get('ip')} → {current_status.get('ip')}")
        
        current_status['issues'] = issues
        return len(issues) > 0

    def _get_issue_description(self, status):
        """Get a formatted description of issues"""
        issues = status.get('issues', [])
        if not issues:
            return "No issues detected"
        return "\n".join(f"• {issue}" for issue in issues)
