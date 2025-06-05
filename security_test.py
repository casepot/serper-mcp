#!/usr/bin/env python3
"""
Security Testing Script for Serper MCP Server

This script performs various security tests against the MCP server to verify
that security controls are working correctly.
"""

import asyncio
import os
import time
from typing import Dict, Any, List
import httpx
from fastmcp import Client
from fastmcp.client.auth import BearerAuth
from fastmcp.exceptions import ToolError

# Test configuration
TEST_SERVER_URL = os.getenv("TEST_SERVER_URL", "http://localhost:8000")
TEST_TOKEN = os.getenv("TEST_TOKEN", "")
INVALID_TOKEN = "invalid-token-12345"

class SecurityTester:
    """Security testing suite for Serper MCP Server"""
    
    def __init__(self, server_url: str):
        self.server_url = server_url
        self.sse_url = f"{server_url}/sse"
        self.results: List[Dict[str, Any]] = []
    
    def log_test_result(self, test_name: str, passed: bool, details: str = ""):
        """Log test results"""
        result = {
            "test": test_name,
            "passed": passed,
            "details": details,
            "timestamp": time.time()
        }
        self.results.append(result)
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} {test_name}: {details}")
    
    async def test_no_authentication(self):
        """Test that unauthenticated requests are rejected"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.sse_url,
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {
                            "name": "google_search",
                            "arguments": {"query": "test"}
                        },
                        "id": 1
                    },
                    timeout=10.0
                )
                
                if response.status_code == 401:
                    self.log_test_result(
                        "No Authentication",
                        True,
                        "Correctly rejected unauthenticated request"
                    )
                else:
                    self.log_test_result(
                        "No Authentication",
                        False,
                        f"Expected 401, got {response.status_code}: {response.text[:200]}"
                    )
        except Exception as e:
            self.log_test_result(
                "No Authentication",
                False,
                f"Exception during test: {str(e)}"
            )
    
    async def test_invalid_token(self):
        """Test that invalid tokens are rejected"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.sse_url,
                    headers={"Authorization": f"Bearer {INVALID_TOKEN}"},
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {
                            "name": "google_search",
                            "arguments": {"query": "test"}
                        },
                        "id": 1
                    },
                    timeout=10.0
                )
                
                if response.status_code == 401:
                    self.log_test_result(
                        "Invalid Token",
                        True,
                        "Correctly rejected invalid token"
                    )
                else:
                    self.log_test_result(
                        "Invalid Token",
                        False,
                        f"Expected 401, got {response.status_code}: {response.text[:200]}"
                    )
        except Exception as e:
            self.log_test_result(
                "Invalid Token",
                False,
                f"Exception during test: {str(e)}"
            )
    
    async def test_valid_authentication(self):
        """Test that valid tokens are accepted"""
        if not TEST_TOKEN:
            self.log_test_result(
                "Valid Authentication",
                False,
                "No test token provided (set TEST_TOKEN environment variable)"
            )
            return
        
        try:
            client = Client(
                self.sse_url,
                auth=BearerAuth(token=TEST_TOKEN)
            )
            
            async with client:
                _ = await client.call_tool("google_search", {"query": "test security"})
                self.log_test_result(
                    "Valid Authentication",
                    True,
                    "Successfully authenticated and executed tool"
                )
        except ToolError as e:
            if "scope" in str(e).lower():
                self.log_test_result(
                    "Valid Authentication",
                    True,
                    "Authentication succeeded, tool failed due to scope restrictions"
                )
            else:
                self.log_test_result(
                    "Valid Authentication",
                    False,
                    f"Tool error: {str(e)}"
                )
        except Exception as e:
            self.log_test_result(
                "Valid Authentication",
                False,
                f"Exception during test: {str(e)}"
            )
    
    async def test_input_validation_query_length(self):
        """Test query length validation"""
        if not TEST_TOKEN:
            self.log_test_result(
                "Query Length Validation",
                False,
                "No test token provided"
            )
            return
        
        try:
            client = Client(
                self.sse_url,
                auth=BearerAuth(token=TEST_TOKEN)
            )
            
            long_query = "A" * 1000
            
            async with client:
                await client.call_tool("google_search", {"query": long_query})
                self.log_test_result(
                    "Query Length Validation",
                    False,
                    "Long query was not rejected"
                )
        except ToolError as e:
            if "too long" in str(e).lower() or "length" in str(e).lower():
                self.log_test_result(
                    "Query Length Validation",
                    True,
                    "Correctly rejected overly long query"
                )
            else:
                self.log_test_result(
                    "Query Length Validation",
                    False,
                    f"Unexpected error: {str(e)}"
                )
        except Exception as e:
            self.log_test_result(
                "Query Length Validation",
                False,
                f"Exception during test: {str(e)}"
            )
    
    async def test_input_validation_malicious_content(self):
        """Test malicious content filtering"""
        if not TEST_TOKEN:
            self.log_test_result(
                "Malicious Content Validation",
                False,
                "No test token provided"
            )
            return
        
        malicious_queries = [
            "<script>alert('xss')</script>",
            "javascript:alert('xss')",
            "vbscript:msgbox('xss')",
            "onload=alert('xss')",
            "onerror=alert('xss')"
        ]
        
        try:
            client = Client(
                self.sse_url,
                auth=BearerAuth(token=TEST_TOKEN)
            )
            
            blocked_count = 0
            async with client:
                for query in malicious_queries:
                    try:
                        await client.call_tool("google_search", {"query": query})
                    except ToolError as e:
                        if "malicious" in str(e).lower() or "suspicious" in str(e).lower():
                            blocked_count += 1
            
            if blocked_count >= len(malicious_queries) // 2:
                self.log_test_result(
                    "Malicious Content Validation",
                    True,
                    f"Blocked {blocked_count}/{len(malicious_queries)} malicious queries"
                )
            else:
                self.log_test_result(
                    "Malicious Content Validation",
                    False,
                    f"Only blocked {blocked_count}/{len(malicious_queries)} malicious queries"
                )
        except Exception as e:
            self.log_test_result(
                "Malicious Content Validation",
                False,
                f"Exception during test: {str(e)}"
            )
    
    async def test_rate_limiting(self):
        """Test rate limiting functionality"""
        if not TEST_TOKEN:
            self.log_test_result(
                "Rate Limiting",
                False,
                "No test token provided"
            )
            return
        
        try:
            client = Client(
                self.sse_url,
                auth=BearerAuth(token=TEST_TOKEN)
            )
            
            # Send many requests rapidly
            request_count = 70
            success_count = 0
            rate_limited_count = 0
            
            async with client:
                for i in range(request_count):
                    try:
                        await client.call_tool("google_search", {"query": f"test {i}"})
                        success_count += 1
                    except ToolError as e:
                        if "rate limit" in str(e).lower():
                            rate_limited_count += 1
                        else:
                            pass
                        await asyncio.sleep(0.1)
            
            if rate_limited_count > 0:
                self.log_test_result(
                    "Rate Limiting",
                    True,
                    f"Rate limiting activated after {success_count} requests, {rate_limited_count} blocked"
                )
            else:
                self.log_test_result(
                    "Rate Limiting",
                    False,
                    f"No rate limiting detected after {request_count} requests"
                )
        except Exception as e:
            self.log_test_result(
                "Rate Limiting",
                False,
                f"Exception during test: {str(e)}"
            )
    
    async def test_parameter_validation(self):
        """Test parameter validation"""
        if not TEST_TOKEN:
            self.log_test_result(
                "Parameter Validation",
                False,
                "No test token provided"
            )
            return
        
        try:
            client = Client(
                self.sse_url,
                auth=BearerAuth(token=TEST_TOKEN)
            )
            
            validation_errors = 0
            async with client:
                try:
                    await client.call_tool("google_search", {
                        "query": "test",
                        "num_results": 200
                    })
                except ToolError as e:
                    if "num_results" in str(e).lower():
                        validation_errors += 1
                try:
                    await client.call_tool("google_search", {
                        "query": "test",
                        "page_number": 50
                    })
                except ToolError as e:
                    if "page_number" in str(e).lower():
                        validation_errors += 1
            
            if validation_errors > 0:
                self.log_test_result(
                    "Parameter Validation",
                    True,
                    f"Correctly validated {validation_errors} invalid parameters"
                )
            else:
                self.log_test_result(
                    "Parameter Validation",
                    False,
                    "No parameter validation detected"
                )
        except Exception as e:
            self.log_test_result(
                "Parameter Validation",
                False,
                f"Exception during test: {str(e)}"
            )
    
    async def test_error_information_disclosure(self):
        """Test that error messages don't disclose sensitive information"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.sse_url,
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {
                            "name": "nonexistent_tool",
                            "arguments": {"query": "test"}
                        },
                        "id": 1
                    },
                    timeout=10.0
                )
                
                response_text = response.text.lower()
                
                sensitive_patterns = [
                    "traceback",
                    "stack trace",
                    "file path",
                    "/home/",
                    "/usr/",
                    "secret",
                    "password",
                    "api_key"
                ]
                disclosed_patterns = [p for p in sensitive_patterns if p in response_text]
                
                if not disclosed_patterns:
                    self.log_test_result(
                        "Error Information Disclosure",
                        True,
                        "No sensitive information detected in error messages"
                    )
                else:
                    self.log_test_result(
                        "Error Information Disclosure",
                        False,
                        f"Sensitive patterns detected: {disclosed_patterns}"
                    )
        except Exception as e:
            self.log_test_result(
                "Error Information Disclosure",
                False,
                f"Exception during test: {str(e)}"
            )
    
    async def run_all_tests(self):
        """Run all security tests"""
        print("🔒 Starting Security Test Suite for Serper MCP Server")
        print("=" * 60)
        
        tests = [
            self.test_no_authentication,
            self.test_invalid_token,
            self.test_valid_authentication,
            self.test_input_validation_query_length,
            self.test_input_validation_malicious_content,
            self.test_rate_limiting,
            self.test_parameter_validation,
            self.test_error_information_disclosure
        ]
        
        for test in tests:
            await test()
            await asyncio.sleep(1)  # Brief pause between tests
        
        print("\n" + "=" * 60)
        print("🔒 Security Test Results Summary")
        print("=" * 60)
        
        passed_tests = sum(1 for r in self.results if r["passed"])
        total_tests = len(self.results)
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {total_tests - passed_tests}")
        print(f"Success Rate: {(passed_tests / total_tests * 100):.1f}%")
        
        print("\nDetailed Results:")
        for result in self.results:
            status = "✅" if result["passed"] else "❌"
            print(f"{status} {result['test']}: {result['details']}")
        
        return passed_tests == total_tests

async def main():
    """Main function to run security tests"""
    print("Serper MCP Server Security Testing Tool")
    print("----------------------------------------")
    
    if not TEST_TOKEN:
        print("⚠️  WARNING: No TEST_TOKEN provided. Authentication tests will be limited.")
        print("   Set TEST_TOKEN environment variable with a valid bearer token.")
        print()
    
    tester = SecurityTester(TEST_SERVER_URL)
    success = await tester.run_all_tests()
    
    if success:
        print("\n🎉 All security tests passed!")
        return 0
    else:
        print("\n⚠️  Some security tests failed. Review the results above.")
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))