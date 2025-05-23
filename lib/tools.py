#!/usr/bin/env python3
"""
External tool integrations for APTES
"""

import os
import re
import json
import logging
import tempfile
import subprocess
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger('aptes.tools')

# Check for optional imports
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

def check_sqlmap_installation():
    """
    Check if SQLMap is installed
    
    Returns:
        bool: True if SQLMap is installed, False otherwise
    """
    try:
        output = subprocess.check_output(["sqlmap", "--version"], stderr=subprocess.STDOUT)
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        return False

def check_xssniper_installation():
    """
    Check if XSSniper is installed
    
    Returns:
        bool: True if XSSniper is installed, False otherwise
    """
    try:
        # Try to import XSSniper module
        subprocess.check_output(["python3", "-c", "import xssniper"], stderr=subprocess.STDOUT)
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        # Try to check if the script exists
        try:
            subprocess.check_output(["which", "xssniper.py"], stderr=subprocess.STDOUT)
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

def run_sqlmap(target, options=None, output_dir=None, timeout=600):
    """
    Run SQLMap against a target
    
    Args:
        target (str): Target URL or file containing targets
        options (dict): SQLMap options
        output_dir (str): Output directory
        timeout (int): Timeout in seconds
    
    Returns:
        dict: SQLMap results
    """
    logger.info(f"Running SQLMap against {target}")
    
    if not check_sqlmap_installation():
        logger.error("SQLMap is not installed")
        return {"error": "SQLMap is not installed"}
    
    # Create temporary output directory if not provided
    if not output_dir:
        output_dir = tempfile.mkdtemp(prefix="aptes_sqlmap_")
    
    # Base command
    cmd = ["sqlmap", "-u", target, "--batch"]
    
    # Add output directory
    cmd.extend(["--output-dir", output_dir])
    
    # Default options for thorough testing
    default_options = {
        "level": 3,
        "risk": 2,
        "technique": "BEUSTQ",  # Use all techniques
        "random-agent": True,
        "threads": 4
    }
    
    # Merge with user options
    if options:
        default_options.update(options)
    
    # Add options to command
    for key, value in default_options.items():
        if value is True:
            cmd.append(f"--{key}")
        elif value is not False:  # False means don't include the option
            cmd.append(f"--{key}={value}")
    
    # Run SQLMap
    try:
        logger.debug(f"Executing: {' '.join(cmd)}")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        
        stdout, stderr = process.communicate(timeout=timeout)
        
        # Parse results
        results = {
            "command": " ".join(cmd),
            "output_dir": output_dir,
            "stdout": stdout,
            "returncode": process.returncode
        }
        
        # Check for vulnerabilities in output
        if "is vulnerable" in stdout:
            results["vulnerable"] = True
            
            # Extract vulnerabilities
            vuln_params = re.findall(r"Parameter '([^']+)' is vulnerable", stdout)
            vulnerabilities = []
            
            for param in vuln_params:
                # Determine injection type
                injection_type = "Unknown"
                
                if "error-based" in stdout:
                    injection_type = "error-based"
                elif "boolean-based blind" in stdout:
                    injection_type = "boolean-based blind"
                elif "time-based blind" in stdout:
                    injection_type = "time-based blind"
                elif "UNION query" in stdout:
                    injection_type = "UNION query"
                
                vulnerabilities.append({
                    "parameter": param,
                    "type": injection_type
                })
            
            results["vulnerabilities"] = vulnerabilities
        else:
            results["vulnerable"] = False
        
        return results
    
    except subprocess.TimeoutExpired:
        logger.error(f"SQLMap timed out after {timeout} seconds")
        return {
            "command": " ".join(cmd),
            "error": f"Timed out after {timeout} seconds",
            "output_dir": output_dir
        }
    except Exception as e:
        logger.error(f"Error running SQLMap: {e}")
        return {
            "command": " ".join(cmd),
            "error": str(e),
            "output_dir": output_dir
        }

def run_sqlmap_advanced(target, output_dir=None, crawl_depth=5, flush_session=True, timeout=1200):
    """
    Run SQLMap with advanced options for comprehensive web app testing.
    Args:
        target (str): Target URL.
        output_dir (str): Output directory.
        crawl_depth (int): Depth for crawling.
        flush_session (bool): Whether to flush previous session.
        timeout (int): Timeout in seconds.
    Returns:
        dict: SQLMap results.
    """
    logger.info(f"Running advanced SQLMap against {target}")
    if not check_sqlmap_installation():
        logger.error("SQLMap is not installed")
        return {"error": "SQLMap is not installed"}
    if not output_dir:
        output_dir = tempfile.mkdtemp(prefix="aptes_sqlmap_")
    cmd = [
        "sqlmap", "-u", target,
        "--forms",
        f"--crawl={crawl_depth}",
        "--batch",
        f"--output-dir={output_dir}",
        # "--random-agent"
    ]
    if flush_session:
        cmd.append("--flush-session")
    try:
        logger.debug(f"Executing: {' '.join(cmd)}")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        stdout, stderr = process.communicate(timeout=timeout)
        results = {
            "command": " ".join(cmd),
            "output_dir": output_dir,
            "stdout": stdout,
            "returncode": process.returncode
        }
        # Parse vulnerabilities as in run_sqlmap
        if "is vulnerable" in stdout:
            results["vulnerable"] = True
            vuln_params = re.findall(r"Parameter '([^']+)' is vulnerable", stdout)
            vulnerabilities = []
            for param in vuln_params:
                injection_type = "Unknown"
                if "error-based" in stdout:
                    injection_type = "error-based"
                elif "boolean-based blind" in stdout:
                    injection_type = "boolean-based blind"
                elif "time-based blind" in stdout:
                    injection_type = "time-based blind"
                elif "UNION query" in stdout:
                    injection_type = "UNION query"
                vulnerabilities.append({
                    "parameter": param,
                    "type": injection_type
                })
            results["vulnerabilities"] = vulnerabilities
        else:
            results["vulnerable"] = False
        return results
    except subprocess.TimeoutExpired:
        logger.error(f"SQLMap timed out after {timeout} seconds")
        return {
            "command": " ".join(cmd),
            "error": f"Timed out after {timeout} seconds",
            "output_dir": output_dir
        }
    except Exception as e:
        logger.error(f"Error running SQLMap: {e}")
        return {
            "command": " ".join(cmd),
            "error": str(e),
            "output_dir": output_dir
        }

def check_owasp_top10_vulnerabilities(target, options=None):
    """
    Run dedicated checks for all OWASP Top 10 vulnerabilities.
    Args:
        target (str): Target URL.
        options (dict): Optional scan options.
    Returns:
        dict: Results for each OWASP Top 10 category.
    """
    results = {}
    # Try to import requests
    try:
        import requests
    except ImportError:
        # If requests is not available, return not_implemented for all
        owasp_top10 = [
            "A01:2021-Broken Access Control",
            "A02:2021-Cryptographic Failures",
            "A03:2021-Injection",
            "A04:2021-Insecure Design",
            "A05:2021-Security Misconfiguration",
            "A06:2021-Vulnerable and Outdated Components",
            "A07:2021-Identification and Authentication Failures",
            "A08:2021-Software and Data Integrity Failures",
            "A09:2021-Security Logging and Monitoring Failures",
            "A10:2021-Server-Side Request Forgery"
        ]
        for item in owasp_top10:
            results[item] = {"status": "not_implemented"}
        return results

    # A01:2021-Broken Access Control
    try:
        # Try to access a common admin page
        admin_url = f'https://{target.rstrip("/")}' + "/admin"
        resp = requests.get(admin_url, timeout=5, verify=False)
        if resp.status_code == 200 and "login" not in resp.text.lower():
            results["A01:2021-Broken Access Control"] = {
                "status": "potential_issue",
                "details": f"Accessible admin page at {admin_url}"
            }
        else:
            results["A01:2021-Broken Access Control"] = {"status": "ok"}
    except Exception as e:
        results["A01:2021-Broken Access Control"] = {"status": "unknown", "error": str(e)}

    # A02:2021-Cryptographic Failures
    try:
        resp = requests.get(f'https://{target.rstrip("/")}', timeout=5, verify=False)
        headers = resp.headers
        cookies = resp.cookies
        issues = []
        # Check for missing HSTS
        if "Strict-Transport-Security" not in headers:
            issues.append("Missing Strict-Transport-Security header")
        # Check for secure cookies
        for cookie in cookies:
            if not cookie.secure:
                issues.append(f"Cookie {cookie.name} is not marked as Secure")
        if issues:
            results["A02:2021-Cryptographic Failures"] = {"status": "potential_issue", "details": issues}
        else:
            results["A02:2021-Cryptographic Failures"] = {"status": "ok"}
    except Exception as e:
        results["A02:2021-Cryptographic Failures"] = {"status": "unknown", "error": str(e)}

    # A03:2021-Injection
    try:
        # Try a simple SQL injection payload
        test_url = f'https://{target.rstrip("/")}' + "/?id=1'"
        resp = requests.get(test_url, timeout=5, verify=False)
        if any(err in resp.text.lower() for err in ["sql syntax", "mysql", "syntax error", "unclosed quotation", "odbc", "pdo"]):
            results["A03:2021-Injection"] = {
                "status": "potential_issue",
                "details": f"SQL error detected at {test_url}"
            }
        else:
            results["A03:2021-Injection"] = {"status": "ok"}
    except Exception as e:
        results["A03:2021-Injection"] = {"status": "unknown", "error": str(e)}

    # A04:2021-Insecure Design
    # Heuristic: Check for verbose error messages
    try:
        error_url = f'https://{target.rstrip("/")}' + "/nonexistentpage"
        resp = requests.get(error_url, timeout=5, verify=False)
        if resp.status_code >= 500 or "exception" in resp.text.lower():
            results["A04:2021-Insecure Design"] = {
                "status": "potential_issue",
                "details": "Verbose error message or stack trace detected"
            }
        else:
            results["A04:2021-Insecure Design"] = {"status": "ok"}
    except Exception as e:
        results["A04:2021-Insecure Design"] = {"status": "unknown", "error": str(e)}

    # A05:2021-Security Misconfiguration
    try:
        resp = requests.get(f'https://{target.rstrip("/")}', timeout=5, verify=False)
        headers = resp.headers
        issues = []
        if "X-Frame-Options" not in headers:
            issues.append("Missing X-Frame-Options header")
        if "X-Content-Type-Options" not in headers:
            issues.append("Missing X-Content-Type-Options header")
        if "Server" in headers and ("apache" in headers["Server"].lower() or "nginx" in headers["Server"].lower()):
            issues.append(f"Server header reveals technology: {headers['Server']}")
        if issues:
            results["A05:2021-Security Misconfiguration"] = {"status": "potential_issue", "details": issues}
        else:
            results["A05:2021-Security Misconfiguration"] = {"status": "ok"}
    except Exception as e:
        results["A05:2021-Security Misconfiguration"] = {"status": "unknown", "error": str(e)}

    # A06:2021-Vulnerable and Outdated Components
    try:
        resp = requests.get(f'https://{target.rstrip("/")}', timeout=5, verify=False)
        body = resp.text
        outdated = []
        # Simple checks for old jQuery, WordPress, etc.
        if "jquery-1." in body or "jquery-2." in body:
            outdated.append("Old jQuery version detected")
        if "wordpress" in body.lower():
            import re
            m = re.search(r'wordpress\s*([0-9\.]+)', body, re.I)
            if m and m.group(1).startswith("4."):
                outdated.append(f"Old WordPress version detected: {m.group(1)}")
        if outdated:
            results["A06:2021-Vulnerable and Outdated Components"] = {"status": "potential_issue", "details": outdated}
        else:
            results["A06:2021-Vulnerable and Outdated Components"] = {"status": "ok"}
    except Exception as e:
        results["A06:2021-Vulnerable and Outdated Components"] = {"status": "unknown", "error": str(e)}

    # A07:2021-Identification and Authentication Failures
    try:
        login_url = f'https://{target.rstrip("/")}' + "/login"
        resp = requests.get(login_url, timeout=5, verify=False)
        if resp.status_code == 200 and ("password" in resp.text.lower() or "login" in resp.text.lower()):
            # Try default creds (admin/admin)
            resp2 = requests.post(login_url, data={"username": "admin", "password": "admin"}, timeout=5, verify=False)
            if resp2.status_code == 200 and "logout" in resp2.text.lower():
                results["A07:2021-Identification and Authentication Failures"] = {
                    "status": "potential_issue",
                    "details": "Default credentials (admin/admin) may work"
                }
            else:
                results["A07:2021-Identification and Authentication Failures"] = {"status": "ok"}
        else:
            results["A07:2021-Identification and Authentication Failures"] = {"status": "ok"}
    except Exception as e:
        results["A07:2021-Identification and Authentication Failures"] = {"status": "unknown", "error": str(e)}

    # A08:2021-Software and Data Integrity Failures
    # Heuristic: Check for missing SRI in script tags
    try:
        resp = requests.get(f'https://{target.rstrip("/")}', timeout=5, verify=False)
        body = resp.text
        import re
        scripts = re.findall(r'<script[^>]+src=[\'"][^\'"]+[\'"][^>]*>', body, re.I)
        missing_sri = []
        for script in scripts:
            if "integrity=" not in script:
                missing_sri.append(script)
        if missing_sri:
            results["A08:2021-Software and Data Integrity Failures"] = {
                "status": "potential_issue",
                "details": f"{len(missing_sri)} script tags missing SRI"
            }
        else:
            results["A08:2021-Software and Data Integrity Failures"] = {"status": "ok"}
    except Exception as e:
        results["A08:2021-Software and Data Integrity Failures"] = {"status": "unknown", "error": str(e)}

    # A09:2021-Security Logging and Monitoring Failures
    # Heuristic: Check for generic error messages
    try:
        error_url = f'https://{target.rstrip("/")}' + "/nonexistentpage"
        resp = requests.get(error_url, timeout=5, verify=False)
        if resp.status_code == 404 and "not found" in resp.text.lower():
            results["A09:2021-Security Logging and Monitoring Failures"] = {"status": "ok"}
        else:
            results["A09:2021-Security Logging and Monitoring Failures"] = {
                "status": "potential_issue",
                "details": "No standard 404 error message"
            }
    except Exception as e:
        results["A09:2021-Security Logging and Monitoring Failures"] = {"status": "unknown", "error": str(e)}

    # A10:2021-Server-Side Request Forgery
    # Heuristic: Look for SSRF-prone parameters in forms
    try:
        resp = requests.get(f'https://{target.rstrip("/")}', timeout=5, verify=False)
        body = resp.text
        import re
        ssrf_params = re.findall(r'name=["\'](url|uri|path|dest|redirect|next)["\']', body, re.I)
        if ssrf_params:
            results["A10:2021-Server-Side Request Forgery"] = {
                "status": "potential_issue",
                "details": f"Potential SSRF parameter(s) found: {', '.join(set(ssrf_params))}"
            }
        else:
            results["A10:2021-Server-Side Request Forgery"] = {"status": "ok"}
    except Exception as e:
        results["A10:2021-Server-Side Request Forgery"] = {"status": "unknown", "error": str(e)}

    return results

def detect_modern_web_frameworks(target, html_content):
    """
    Identify modern web frameworks and check for framework-specific vulns.
    Args:
        target (str): Target URL.
        html_content (str): HTML content of the page.
    Returns:
        dict: Frameworks detected and possible vulnerabilities.
    """
    frameworks = []
    vulns = []
    # Simple detection by script src and meta tags
    if "react" in html_content.lower():
        frameworks.append("React")
        # Add React-specific checks here
    if "angular" in html_content.lower():
        frameworks.append("Angular")
    if "vue" in html_content.lower():
        frameworks.append("Vue.js")
    if "ember" in html_content.lower():
        frameworks.append("Ember.js")
    if "jquery" in html_content.lower():
        frameworks.append("jQuery")
    # ...add more as needed...
    # Placeholder for framework-specific vulnerability checks
    return {"frameworks": frameworks, "framework_vulnerabilities": vulns}

def detect_technology_stack(html_content, headers=None):
    """
    Enhanced technology stack detection.
    Args:
        html_content (str): HTML content.
        headers (dict): HTTP headers.
    Returns:
        dict: Detected technologies, libraries, dependencies.
    """
    stack = set()
    if headers:
        server = headers.get("Server", "")
        if server:
            stack.add(server)
        x_powered = headers.get("X-Powered-By", "")
        if x_powered:
            stack.add(x_powered)
    # Look for common JS libraries
    for lib in ["jquery", "react", "angular", "vue", "bootstrap", "lodash"]:
        if lib in html_content.lower():
            stack.add(lib)
    return {"technology_stack": list(stack)}

def find_sensitive_info_in_js(js_content):
    """
    Find exposed API keys, credentials in JS files.
    Args:
        js_content (str): JavaScript file content.
    Returns:
        list: Sensitive info findings.
    """
    findings = []
    # Simple regex for API keys, tokens, secrets
    patterns = [
        r"api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]",
        r"secret\s*[:=]\s*['\"][A-Za-z0-9_\-]{8,}['\"]",
        r"token\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]",
        r"password\s*[:=]\s*['\"][^'\"]{6,}['\"]"
    ]
    for pat in patterns:
        for match in re.findall(pat, js_content, re.IGNORECASE):
            findings.append({"type": "sensitive_info", "match": match})
    return findings

def analyze_csp(headers):
    """
    Analyze and test Content Security Policy (CSP) configurations.
    Args:
        headers (dict): HTTP headers.
    Returns:
        dict: CSP analysis results.
    """
    csp = headers.get("Content-Security-Policy", "")
    result = {"csp_present": bool(csp), "issues": []}
    if csp:
        if "'unsafe-inline'" in csp or "'unsafe-eval'" in csp:
            result["issues"].append("CSP allows unsafe-inline or unsafe-eval")
        if "*" in csp:
            result["issues"].append("CSP uses wildcard *")
    else:
        result["issues"].append("No CSP header present")
    return result

def detect_dom_xss(html_content, js_content=None):
    """
    Enhanced DOM-based XSS discovery.
    Args:
        html_content (str): HTML content.
        js_content (str): JS content (optional).
    Returns:
        list: DOM XSS findings.
    """
    findings = []
    # Look for common DOM XSS sinks
    dom_sinks = ["document.write", "innerHTML", "outerHTML", "eval", "setTimeout", "setInterval", "location.hash"]
    for sink in dom_sinks:
        if sink in html_content:
            findings.append({"sink": sink, "location": "html"})
        if js_content and sink in js_content:
            findings.append({"sink": sink, "location": "js"})
    return findings

def find_hidden_parameters(html_content):
    """
    Find non-visible URL parameters and form fields.
    Args:
        html_content (str): HTML content.
    Returns:
        list: Hidden parameter findings.
    """
    findings = []
    # Hidden input fields
    for match in re.findall(r'<input[^>]+type=["\']hidden["\'][^>]*>', html_content, re.IGNORECASE):
        name_match = re.search(r'name=["\']([^"\']+)["\']', match)
        if name_match:
            findings.append({"type": "hidden_input", "name": name_match.group(1)})
    # Non-visible URL params (heuristic: params not in visible forms)
    # Placeholder: implement advanced logic as needed
    return findings

def run_xssniper(target, options=None, timeout=300):
    """
    Run XSSniper against a target
    
    Args:
        target (str): Target URL
        options (dict): XSSniper options
        timeout (int): Timeout in seconds
    
    Returns:
        dict: XSSniper results
    """
    logger.info(f"Running XSSniper against {target}")
    
    if not check_xssniper_installation():
        logger.error("XSSniper is not installed")
        return {"error": "XSSniper is not installed", "fallback": True}
    
    # Base command
    cmd = ["python3", "xssniper.py", "-u", target]
    
    # Default options
    default_options = {
        "auto": True,  # Automatic mode
        "dom": True,   # Check for DOM XSS
        "fuzz": True   # Fuzz parameters
    }
    
    # Merge with user options
    if options:
        default_options.update(options)
    
    # Add options to command
    for key, value in default_options.items():
        if value is True:
            cmd.append(f"--{key}")
        elif value is not False:  # False means don't include the option
            cmd.append(f"--{key}={value}")
    
    # Run XSSniper
    try:
        logger.debug(f"Executing: {' '.join(cmd)}")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        
        stdout, stderr = process.communicate(timeout=timeout)
        
        # Parse results
        results = {
            "command": " ".join(cmd),
            "stdout": stdout,
            "returncode": process.returncode
        }
        
        # Check for vulnerabilities in output (adapt this to match XSSniper's output format)
        if "XSS found" in stdout or "Vulnerable to XSS" in stdout:
            results["vulnerable"] = True
            
            # Extract vulnerabilities (adjust regex according to XSSniper output)
            vuln_params = re.findall(r"Parameter: ([^\s]+)", stdout)
            if not vuln_params:
                vuln_params = re.findall(r"Vulnerable parameter: ([^\s]+)", stdout)
            
            # Collect found XSS vulnerabilities
            vulnerabilities = []
            for param in vuln_params:
                vulnerabilities.append({
                    "parameter": param,
                    "type": "xss"
                })
            
            # If no specific parameters found but vulnerability was detected
            if not vulnerabilities and results["vulnerable"]:
                vulnerabilities.append({
                    "parameter": "unknown",
                    "type": "xss"
                })
            
            results["vulnerabilities"] = vulnerabilities
        else:
            results["vulnerable"] = False
        
        return results
    
    except subprocess.TimeoutExpired:
        logger.error(f"XSSniper timed out after {timeout} seconds")
        return {
            "command": " ".join(cmd),
            "error": f"Timed out after {timeout} seconds",
            "fallback": True
        }
    except Exception as e:
        logger.error(f"Error running XSSniper: {e}")
        return {
            "command": " ".join(cmd),
            "error": str(e),
            "fallback": True
        }

def run_custom_xss_scan(target, options=None):
    """
    Run a custom XSS scan on a target when XSSniper is not available
    
    Args:
        target (str): Target URL
        options (dict): Scan options
    
    Returns:
        dict: Scan results
    """
    logger.info(f"Running custom XSS scan against {target}")
    
    if not REQUESTS_AVAILABLE:
        logger.error("Requests library is required for custom XSS scanning")
        return {"error": "Requests library not available"}
    
    # XSS payloads to test
    payloads = [
        "<script>alert('XSS')</script>",
        "<img src=x onerror=alert('XSS')>",
        "<svg/onload=alert('XSS')>",
        "'\"><script>alert('XSS')</script>",
        "<script>prompt(1)</script>",
        "<img src=x onerror=prompt(1)>",
        "<body onload=alert('XSS')>",
        "<iframe src=\"javascript:alert('XSS')\"></iframe>"
    ]
    
    # Results container
    results = {
        "command": "Custom XSS scanner",
        "target": target,
        "vulnerable": False,
        "vulnerabilities": []
    }
    
    try:
        # Parse URL to get query parameters
        parsed_url = urlparse(target)
        query_params = parse_qs(parsed_url.query)
        
        # If URL has query parameters, test them
        if query_params:
            for param, values in query_params.items():
                for payload in payloads:
                    # Build test URL by replacing parameter value with payload
                    test_params = query_params.copy()
                    test_params[param] = [payload]
                    
                    # Reconstruct query string
                    query_string = "&".join([f"{p}={v[0]}" for p, v in test_params.items()])
                    
                    # Build test URL
                    test_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}?{query_string}"
                    
                    try:
                        response = requests.get(test_url, timeout=10, verify=False)
                        
                        # Check if the exact payload is reflected in the response
                        if payload in response.text:
                            results["vulnerable"] = True
                            results["vulnerabilities"].append({
                                "parameter": param,
                                "payload": payload,
                                "type": "reflected"
                            })
                            # Break after finding a vulnerability for this parameter
                            break
                    except Exception as e:
                        logger.debug(f"Error testing {param} with payload {payload}: {e}")
        else:
            # No query parameters, try to discover inputs
            try:
                response = requests.get(target, timeout=10, verify=False)
                
                # Look for input fields in the response
                input_fields = re.findall(r'<input.*?name=[\'"]([^\'"]+)[\'"]', response.text)
                form_actions = re.findall(r'<form.*?action=[\'"]([^\'"]+)[\'"]', response.text)
                
                if input_fields:
                    results["info"] = f"Found {len(input_fields)} input fields: {', '.join(input_fields)}"
                    results["input_fields"] = input_fields
                
                if form_actions:
                    results["info"] = f"Found {len(form_actions)} form actions: {', '.join(form_actions)}"
                    results["form_actions"] = form_actions
            except Exception as e:
                logger.debug(f"Error scanning for inputs: {e}")
        
        return results
    
    except Exception as e:
        logger.error(f"Error in custom XSS scan: {e}")
        return {
            "error": str(e),
            "vulnerable": False
        }

def run_lfi_tester(target, options=None, timeout=180):
    """
    Test for Local File Inclusion (LFI) vulnerabilities
    
    Args:
        target (str): Target URL
        options (dict): Scan options
        timeout (int): Timeout in seconds
    
    Returns:
        dict: Scan results
    """
    logger.info(f"Testing for LFI vulnerabilities on {target}")
    
    if not REQUESTS_AVAILABLE:
        logger.error("Requests library is required for LFI testing")
        return {"error": "Requests library not available"}
    
    # Common LFI payloads
    payloads = [
        "../../../etc/passwd",
        "../../../../etc/passwd",
        "../../../../../etc/passwd",
        "../../../../../../etc/passwd",
        "/etc/passwd",
        "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
        "....//....//....//etc/passwd",
        "..%252f..%252f..%252fetc%252fpasswd",
        "../../../etc/passwd%00",
        "..\\..\\..\\windows\\win.ini",
        "/proc/self/environ",
        "/var/log/apache2/access.log",
        "/var/log/apache/access.log",
        "php://filter/convert.base64-encode/resource=/etc/passwd"
    ]
    
    # LFI indicators (patterns in response that indicate successful exploitation)
    lfi_indicators = [
        "root:x:",
        "bin/bash",
        "[fonts]",
        "for 16-bit app support",
        "PHP Version",
        "HTTP_USER_AGENT",
        "apache_",
        "www-data"
    ]
    
    # Results container
    results = {
        "command": "Custom LFI scanner",
        "target": target,
        "vulnerable": False,
        "vulnerabilities": []
    }
    
    try:
        # Parse URL to get query parameters
        parsed_url = urlparse(target)
        query_params = parse_qs(parsed_url.query)
        
        # If URL has query parameters, test them
        if query_params:
            for param, values in query_params.items():
                for payload in payloads:
                    # Build test URL by replacing parameter value with payload
                    test_params = query_params.copy()
                    test_params[param] = [payload]
                    
                    # Reconstruct query string
                    query_string = "&".join([f"{p}={v[0]}" for p, v in test_params.items()])
                    
                    # Build test URL
                    test_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}?{query_string}"
                    
                    try:
                        response = requests.get(test_url, timeout=timeout, verify=False)
                        
                        # Check for LFI indicators in the response
                        for indicator in lfi_indicators:
                            if indicator in response.text:
                                results["vulnerable"] = True
                                results["vulnerabilities"].append({
                                    "parameter": param,
                                    "payload": payload,
                                    "indicator": indicator,
                                    "type": "lfi"
                                })
                                # Break after finding a vulnerability for this parameter/payload
                                break
                        
                        # Break the payload loop if we found a vulnerability for this parameter
                        if any(v["parameter"] == param for v in results["vulnerabilities"]):
                            break
                            
                    except Exception as e:
                        logger.debug(f"Error testing {param} with payload {payload}: {e}")
        else:
            # No query parameters, try to identify potential LFI parameters
            # Search the URL path for potential file parameters
            path_segments = parsed_url.path.split('/')
            for segment in path_segments:
                if '.' in segment and segment.lower().endswith(('.php', '.aspx', '.jsp', '.html')):
                    # This could be a file inclusion pattern like view.php or page.asp
                    base_path = parsed_url.path.replace(segment, '')
                    for payload in payloads[:3]:  # Try first 3 payloads
                        test_path = f"{base_path}{payload}"
                        test_url = f"{parsed_url.scheme}://{parsed_url.netloc}{test_path}"
                        
                        try:
                            response = requests.get(test_url, timeout=timeout, verify=False)
                            
                            # Check for LFI indicators in the response
                            for indicator in lfi_indicators:
                                if indicator in response.text:
                                    results["vulnerable"] = True
                                    results["vulnerabilities"].append({
                                        "parameter": "path",
                                        "payload": payload,
                                        "indicator": indicator,
                                        "type": "lfi_path"
                                    })
                                    break
                        except Exception as e:
                            logger.debug(f"Error testing path with payload {payload}: {e}")
        
        return results
    
    except Exception as e:
        logger.error(f"Error in LFI testing: {e}")
        return {
            "error": str(e),
            "vulnerable": False
        }

def run_default_credentials_check(target, service, port=None, timeout=120):
    """
    Check for default credentials on a service
    
    Args:
        target (str): Target host
        service (str): Service to check (ssh, ftp, http, etc.)
        port (int): Port number (optional)
        timeout (int): Timeout in seconds
    
    Returns:
        dict: Results of credential check
    """
    logger.info(f"Checking for default credentials on {target} service {service}")
    
    # Common default credentials by service
    default_creds = {
        "ssh": [
            {"username": "root", "password": "root"},
            {"username": "root", "password": "toor"},
            {"username": "admin", "password": "admin"},
            {"username": "user", "password": "password"},
            {"username": "ubuntu", "password": "ubuntu"},
            {"username": "administrator", "password": "password"}
        ],
        "ftp": [
            {"username": "anonymous", "password": ""},
            {"username": "ftp", "password": "ftp"},
            {"username": "admin", "password": "admin"},
            {"username": "admin", "password": "password"}
        ],
        "http": [
            {"username": "admin", "password": "admin"},
            {"username": "admin", "password": "password"},
            {"username": "administrator", "password": "administrator"},
            {"username": "root", "password": "root"},
            {"username": "user", "password": "password"}
        ],
        "mysql": [
            {"username": "root", "password": ""},
            {"username": "root", "password": "root"},
            {"username": "root", "password": "password"},
            {"username": "admin", "password": "admin"}
        ],
        "mssql": [
            {"username": "sa", "password": ""},
            {"username": "sa", "password": "sa"},
            {"username": "sa", "password": "password"}
        ],
        "postgres": [
            {"username": "postgres", "password": "postgres"},
            {"username": "postgres", "password": "password"},
            {"username": "postgres", "password": ""}
        ],
        "telnet": [
            {"username": "admin", "password": "admin"},
            {"username": "root", "password": "root"},
            {"username": "user", "password": "password"}
        ],
        "snmp": [
            {"community": "public"},
            {"community": "private"},
            {"community": "manager"}
        ]
    }
    
    # Check if we handle this service
    service = service.lower()
    if service not in default_creds:
        return {
            "error": f"Service {service} not supported for default credential checking",
            "supported_services": list(default_creds.keys())
        }
    
    # Use the appropriate default credentials
    credentials = default_creds[service]
    
    # Results container
    results = {
        "service": service,
        "target": target,
        "port": port,
        "tested_credentials": credentials,
        "successful_logins": []
    }
    
    # SSH testing
    if service == "ssh":
        try:
            import paramiko
            for cred in credentials:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                try:
                    ssh.connect(
                        target, 
                        port=port or 22, 
                        username=cred["username"], 
                        password=cred["password"],
                        timeout=10
                    )
                    # If we get here, login was successful
                    results["successful_logins"].append(cred)
                    ssh.close()
                except Exception as e:
                    # Login failed
                    logger.debug(f"SSH login failed with {cred['username']}:{cred['password']} - {str(e)}")
                    continue
        except ImportError:
            logger.warning("Paramiko library not available, using external SSH client")
            # Fallback to external ssh client if available
            for cred in credentials:
                try:
                    cmd = ["sshpass", "-p", cred["password"], "ssh", "-o", "StrictHostKeyChecking=no", 
                          "-o", "ConnectTimeout=10", f"{cred['username']}@{target}", "exit"]
                    subprocess.run(cmd, timeout=15, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                    # If we get here without exception, login was successful
                    results["successful_logins"].append(cred)
                except Exception:
                    # Login failed
                    continue
    
    # FTP testing
    elif service == "ftp":
        try:
            import ftplib
            for cred in credentials:
                try:
                    ftp = ftplib.FTP()
                    ftp.connect(target, port or 21, timeout=10)
                    ftp.login(cred["username"], cred["password"])
                    # If we get here, login was successful
                    results["successful_logins"].append(cred)
                    ftp.quit()
                except Exception as e:
                    # Login failed
                    logger.debug(f"FTP login failed with {cred['username']}:{cred['password']} - {str(e)}")
                    continue
        except ImportError:
            logger.warning("ftplib not available or error occurred")
    
    # HTTP/web login testing
    elif service == "http":
        if not REQUESTS_AVAILABLE:
            logger.error("Requests library required for HTTP credential testing")
            results["error"] = "Requests library not available"
        else:
            # We need to know the login URL and form structure
            # For now, assume basic auth as a fallback
            protocol = "https" if port == 443 else "http"
            base_url = f"{protocol}://{target}"
            if port and port not in (80, 443):
                base_url = f"{base_url}:{port}"
            
            # Try basic authentication
            for cred in credentials:
                try:
                    response = requests.get(
                        base_url, 
                        auth=(cred["username"], cred["password"]),
                        timeout=10,
                        verify=False
                    )
                    
                    # Check if we got past authentication
                    if response.status_code != 401:  # 401 = Unauthorized
                        results["successful_logins"].append({
                            **cred,
                            "auth_type": "basic"
                        })
                except Exception as e:
                    logger.debug(f"HTTP basic auth failed with {cred['username']}:{cred['password']} - {str(e)}")
                    continue
    
    # MySQL testing
    elif service == "mysql":
        try:
            import pymysql as MySQLdb
            for cred in credentials:
                try:
                    conn = MySQLdb.connect(
                        host=target,
                        port=port or 3306,
                        user=cred["username"],
                        passwd=cred["password"]
                    )
                    # If we get here, login was successful
                    results["successful_logins"].append(cred)
                    conn.close()
                except Exception as e:
                    # Login failed
                    logger.debug(f"MySQL login failed with {cred['username']}:{cred['password']} - {str(e)}")
                    continue
        except ImportError:
            logger.warning("MySQLdb library not available")
            # Try with mysql command line client
            for cred in credentials:
                try:
                    cmd = ["mysql", "-h", target, "-u", cred["username"], f"-p{cred['password']}", "-e", "exit"]
                    if port:
                        cmd.extend(["-P", str(port)])
                    subprocess.run(cmd, timeout=15, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                    # If we get here without exception, login was successful
                    results["successful_logins"].append(cred)
                except Exception:
                    # Login failed
                    continue
    
    # SNMP testing
    elif service == "snmp":
        try:
            # Try with snmpwalk command
            for cred in credentials:
                try:
                    cmd = ["snmpwalk", "-v", "2c", "-c", cred["community"], target]
                    subprocess.run(cmd, timeout=15, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                    # If we get here without exception, community string was valid
                    results["successful_logins"].append(cred)
                except Exception:
                    # Login failed
                    continue
        except Exception as e:
            logger.warning(f"SNMP testing error: {e}")
    
    # Set successful flag based on whether we found any valid credentials
    results["successful"] = len(results["successful_logins"]) > 0
    
    return results

def run_cms_vulnerability_check(target, options=None, timeout=180):
    """
    Identify and check for CMS vulnerabilities (WordPress, Joomla, Drupal, etc.)
    
    Args:
        target (str): Target URL
        options (dict): Scan options
        timeout (int): Timeout in seconds
    
    Returns:
        dict: Results of CMS check
    """
    logger.info(f"Checking for CMS vulnerabilities on {target}")
    
    if not REQUESTS_AVAILABLE:
        logger.error("Requests library required for CMS vulnerability checking")
        return {"error": "Requests library not available"}
    
    # Results container
    results = {
        "target": target,
        "cms_detected": False,
        "cms_name": None,
        "cms_version": None,
        "vulnerabilities": [],
    }
    
    try:
        # Get the homepage
        response = requests.get(target, timeout=10, verify=False)
        html_content = response.text
        
        # Check for WordPress indicators
        wp_indicators = [
            "wp-content",
            "wp-includes",
            "wordpress",
            'name="generator" content="WordPress'
        ]
        if any(indicator in html_content for indicator in wp_indicators):
            results["cms_detected"] = True
            results["cms_name"] = "WordPress"
            
            # Try to determine WordPress version
            version_match = re.search(r'name="generator" content="WordPress ([0-9.]+)"', html_content)
            if version_match:
                results["cms_version"] = version_match.group(1)
            
            # Check for specific WordPress files
            wp_files = [
                "wp-login.php",
                "wp-admin/",
                "readme.html",
                "license.txt",
                "wp-content/plugins/",
                "wp-content/themes/"
            ]
            discovered_files = []
            
            for file in wp_files:
                try:
                    file_url = f"{target.rstrip('/')}/{file}"
                    file_response = requests.head(file_url, timeout=5, verify=False)
                    if file_response.status_code == 200:
                        discovered_files.append(file)
                except Exception:
                    continue
            
            results["discovered_files"] = discovered_files
            
            # Check for common WordPress vulnerabilities
            if discovered_files:
                # Check for exposed configuration
                if "wp-config.php" in discovered_files:
                    results["vulnerabilities"].append({
                        "name": "Exposed WordPress Configuration",
                        "description": "wp-config.php is accessible, which may expose database credentials",
                        "risk_level": "critical",
                        "url": f"{target.rstrip('/')}/wp-config.php"
                    })
                
                # Check for vulnerable plugins
                plugin_path = f"{target.rstrip('/')}/wp-content/plugins/"
                try:
                    plugin_response = requests.get(plugin_path, timeout=5, verify=False)
                    if "Index of" in plugin_response.text:
                        # Directory listing is enabled
                        results["vulnerabilities"].append({
                            "name": "WordPress Plugin Directory Listing",
                            "description": "Plugin directory listing is enabled, exposing installed plugins",
                            "risk_level": "medium",
                            "url": plugin_path
                        })
                        
                        # Extract plugin names from directory listing
                        plugin_names = re.findall(r'href="([^"]+)/"', plugin_response.text)
                        results["plugins"] = plugin_names
                
                except Exception:
                    pass
                
                # Check if XML-RPC is enabled
                try:
                    xmlrpc_url = f"{target.rstrip('/')}/xmlrpc.php"
                    xmlrpc_response = requests.get(xmlrpc_url, timeout=5, verify=False)
                    if xmlrpc_response.status_code == 200 and "XML-RPC server accepts POST requests only" in xmlrpc_response.text:
                        results["vulnerabilities"].append({
                            "name": "WordPress XML-RPC Enabled",
                            "description": "XML-RPC is enabled, which can be abused for brute force attacks or DOS",
                            "risk_level": "medium",
                            "url": xmlrpc_url
                        })
                except Exception:
                    pass
        
        # Check for Joomla indicators
        joomla_indicators = [
            "joomla",
            "Joomla!",
            "com_content",
            "com_contact",
            "com_users"
        ]
        if not results["cms_detected"] and any(indicator in html_content for indicator in joomla_indicators):
            results["cms_detected"] = True
            results["cms_name"] = "Joomla"
            
            # Try to determine Joomla version
            version_match = re.search(r'<meta name="generator" content="Joomla! ([0-9.]+)"', html_content)
            if version_match:
                results["cms_version"] = version_match.group(1)
            
            # Check for specific Joomla files
            joomla_files = [
                "administrator/",
                "language/en-GB/en-GB.xml",
                "configuration.php",
                "htaccess.txt",
                "images/"
            ]
            discovered_files = []
            
            for file in joomla_files:
                try:
                    file_url = f"{target.rstrip('/')}/{file}"
                    file_response = requests.head(file_url, timeout=5, verify=False)
                    if file_response.status_code == 200:
                        discovered_files.append(file)
                except Exception:
                    continue
            
            results["discovered_files"] = discovered_files
        
        # Check for Drupal indicators
        drupal_indicators = [
            "drupal",
            "Drupal",
            "sites/all",
            "node/add"
        ]
        if not results["cms_detected"] and any(indicator in html_content for indicator in drupal_indicators):
            results["cms_detected"] = True
            results["cms_name"] = "Drupal"
            
            # Try to determine Drupal version
            response = requests.get(f"{target.rstrip('/')}/CHANGELOG.txt", timeout=5, verify=False)
            if response.status_code == 200 and "Drupal" in response.text:
                version_match = re.search(r'Drupal ([0-9.]+)', response.text.split('\n')[0])
                if version_match:
                    results["cms_version"] = version_match.group(1)
            
            # Check for specific Drupal files
            drupal_files = [
                "sites/default/settings.php",
                "core/CHANGELOG.txt",
                "includes/",
                "modules/",
                "themes/"
            ]
            discovered_files = []
            
            for file in drupal_files:
                try:
                    file_url = f"{target.rstrip('/')}/{file}"
                    file_response = requests.head(file_url, timeout=5, verify=False)
                    if file_response.status_code == 200:
                        discovered_files.append(file)
                except Exception:
                    continue
            
            results["discovered_files"] = discovered_files
        
        # If a CMS was detected and we have a version, check for known vulnerabilities
        if results["cms_detected"] and results["cms_version"]:
            # Placeholder for a vulnerability database lookup
            # In a real implementation, this would query a local or remote vulnerability database
            
            # For demonstration, hardcoded some sample vulnerable versions
            cms_name = results["cms_name"]
            version = results["cms_version"]
            
            # WordPress known vulnerabilities
            if cms_name == "WordPress":
                if version.startswith("5.8") or version.startswith("5.7"):
                    results["vulnerabilities"].append({
                        "name": "WordPress Object Injection",
                        "description": "Object injection vulnerability in PHPMailer",
                        "risk_level": "high",
                        "cve": "CVE-2021-34520"
                    })
                if version.startswith("4.") or version.startswith("5.0"):
                    results["vulnerabilities"].append({
                        "name": "WordPress CSRF to RCE",
                        "description": "Cross-site request forgery vulnerability in WordPress core",
                        "risk_level": "critical",
                        "cve": "CVE-2020-11026"
                    })
            
            # Joomla known vulnerabilities
            elif cms_name == "Joomla":
                if version.startswith("3."):
                    results["vulnerabilities"].append({
                        "name": "Joomla Core Session Injection",
                        "description": "Session injection vulnerability in Joomla core",
                        "risk_level": "high",
                        "cve": "CVE-2020-35616"
                    })
            
            # Drupal known vulnerabilities
            elif cms_name == "Drupal":
                if version.startswith("7.") or version.startswith("8."):
                    results["vulnerabilities"].append({
                        "name": "Drupal Highly Critical RCE",
                        "description": "Drupalgeddon2 Remote Code Execution",
                        "risk_level": "critical",
                        "cve": "CVE-2018-7600"
                    })
        
        return results
    
    except Exception as e:
        logger.error(f"Error in CMS vulnerability check: {e}")
        return {
            "error": str(e),
            "target": target,
            "cms_detected": False
        }
