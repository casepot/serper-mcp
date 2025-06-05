# Serper MCP Server - Security Guide

## Overview

This guide covers security best practices for deploying the Serper MCP server in production environments. The secure implementation provides authentication, authorization, rate limiting, input validation, and comprehensive security logging.

## Security Features

### 1. Authentication & Authorization
- **Bearer Token Authentication**: JWT-based authentication with scope-based permissions
- **Multiple Auth Modes**: Development, production, and no-auth modes
- **Scope-based Access Control**: Fine-grained permissions for different operations

### 2. Rate Limiting
- **Per-client Rate Limiting**: Configurable requests per minute per client
- **In-memory Rate Limiter**: Prevents abuse and DoS attacks
- **Configurable Limits**: Adjustable via environment variables

### 3. Input Validation & Sanitization
- **Query Length Limits**: Prevents oversized requests
- **Content Filtering**: Blocks potentially malicious input patterns
- **Parameter Validation**: Validates all optional parameters within safe ranges
- **URL Validation**: Ensures proper URL format for scraping endpoints

### 4. Security Logging & Monitoring
- **Comprehensive Audit Trail**: All requests and security events logged
- **Structured Logging**: JSON-compatible logging for analysis
- **Security Event Tracking**: Failed auth attempts, rate limit violations
- **Log Rotation**: Configurable log file management

### 5. Error Handling & Information Disclosure
- **Error Masking**: Internal error details hidden from clients
- **Generic Error Messages**: Prevents information leakage
- **Security Exception Handling**: Proper handling of security-related errors

## Environment Configuration

### Required Environment Variables

```bash
# API Configuration (Required)
export SERPER_API_KEY="your-serper-api-key"

# Authentication Mode (Required for Production)
export MCP_AUTH_MODE="bearer_prod"  # Options: none, bearer_dev, bearer_prod

# Rate Limiting (Optional)
export MAX_REQUESTS_PER_MINUTE="60"
export MAX_QUERY_LENGTH="500"

# Server Configuration (Optional)
export MCP_SERVER_HOST="0.0.0.0"
export MCP_SERVER_PORT="8000"
export MCP_SERVER_TRANSPORT="sse"  # Options: stdio, streamable-http, sse
```

### Authentication Modes

#### 1. Development Mode (`bearer_dev`)
```bash
export MCP_AUTH_MODE="bearer_dev"
```
- Automatically generates RSA key pair
- Prints access token to console for testing
- **NEVER use in production**

#### 2. Production Mode (`bearer_prod`)
```bash
export MCP_AUTH_MODE="bearer_prod"

# Option A: Use JWKS URI (Recommended)
export JWKS_URI="https://your-identity-provider.com/.well-known/jwks.json"
export TOKEN_ISSUER="https://your-identity-provider.com/"

# Option B: Use Static Public Key
export PUBLIC_KEY_PEM="-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA...
-----END PUBLIC KEY-----"
export TOKEN_ISSUER="https://your-identity-provider.com/"
```

#### 3. No Authentication (`none`)
```bash
export MCP_AUTH_MODE="none"
```
- **NOT recommended for production**
- Only for local development or testing

## Production Deployment

### 1. Infrastructure Security

#### Container Deployment
```dockerfile
FROM python:3.11-slim

# Create non-root user
RUN useradd -m -u 1001 mcpserver

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY serper_mcp_server_secure.py /app/
RUN chown -R mcpserver:mcpserver /app

USER mcpserver
WORKDIR /app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000
CMD ["python", "serper_mcp_server_secure.py"]
```

#### Environment Variables in Production
```bash
# Use secrets management system
export SERPER_API_KEY=$(vault kv get -field=api_key secret/serper)
export MCP_AUTH_MODE="bearer_prod"
export JWKS_URI="https://auth.yourcompany.com/.well-known/jwks.json"
export TOKEN_ISSUER="https://auth.yourcompany.com/"
export MAX_REQUESTS_PER_MINUTE="30"  # Conservative for production
```

### 2. Network Security

#### Reverse Proxy Configuration (Nginx)
```nginx
server {
    listen 443 ssl http2;
    server_name mcp.yourcompany.com;
    
    ssl_certificate /path/to/certificate.crt;
    ssl_certificate_key /path/to/private.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512;
    
    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    
    # Rate limiting
    limit_req_zone $binary_remote_addr zone=mcp:10m rate=10r/m;
    limit_req zone=mcp burst=5 nodelay;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeout settings
        proxy_connect_timeout 30s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
    }
}
```

### 3. Monitoring & Alerting

#### Log Monitoring
```bash
# Monitor security events
tail -f serper_mcp_security.log | grep -E "(SECURITY|ERROR|WARNING)"

# Set up log rotation
cat > /etc/logrotate.d/serper-mcp << EOF
/path/to/serper_mcp_security.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 644 mcpserver mcpserver
    postrotate
        /bin/kill -HUP $(cat /var/run/serper-mcp.pid) 2> /dev/null || true
    endscript
}
EOF
```

#### Security Metrics
Monitor these key security metrics:
- Authentication failures per minute
- Rate limit violations per client
- Input validation failures
- API error rates
- Unusual query patterns

## Security Best Practices

### 1. Secret Management
- **Never hardcode secrets** in configuration files
- Use **environment variables** or **secret management systems**
- **Rotate API keys** regularly
- **Monitor secret usage** and access patterns

### 2. Access Control
- **Implement least privilege** principle
- **Use scoped tokens** for different operations
- **Regularly audit** token permissions
- **Implement token expiration** policies

### 3. Input Validation
- **Validate all inputs** at the boundary
- **Sanitize user data** before processing
- **Implement length limits** for all text inputs
- **Use allowlists** instead of blocklists when possible

### 4. Monitoring & Incident Response
- **Log all security events** with sufficient detail
- **Set up alerts** for suspicious activities
- **Have an incident response plan** ready
- **Regularly review logs** for anomalies

### 5. Network Security
- **Use HTTPS everywhere** (TLS 1.2+)
- **Implement proper CORS** policies
- **Use security headers** appropriately
- **Network segmentation** where possible

## Threat Model

### Identified Threats
1. **API Key Theft**: Unauthorized access to Serper API
2. **Rate Limit Abuse**: DoS attacks through excessive requests
3. **Input Injection**: Malicious content in search queries
4. **Token Theft**: Unauthorized access to MCP server
5. **Information Disclosure**: Sensitive data leakage through errors

### Mitigations
1. **Environment Variables**: Secure API key storage
2. **Rate Limiting**: Per-client request throttling
3. **Input Validation**: Content filtering and sanitization
4. **Bearer Authentication**: JWT-based access control
5. **Error Masking**: Generic error messages

## Security Testing

### 1. Authentication Testing
```bash
# Test without token (should fail)
curl -X POST "https://mcp.yourcompany.com/sse" \
  -H "Content-Type: application/json" \
  -d '{"method": "tools/call", "params": {"name": "google_search", "arguments": {"query": "test"}}}'

# Test with invalid token (should fail)
curl -X POST "https://mcp.yourcompany.com/sse" \
  -H "Authorization: Bearer invalid-token" \
  -H "Content-Type: application/json" \
  -d '{"method": "tools/call", "params": {"name": "google_search", "arguments": {"query": "test"}}}'

# Test with valid token (should succeed)
curl -X POST "https://mcp.yourcompany.com/sse" \
  -H "Authorization: Bearer $VALID_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"method": "tools/call", "params": {"name": "google_search", "arguments": {"query": "test"}}}'
```

### 2. Rate Limit Testing
```bash
# Test rate limiting
for i in {1..100}; do
  curl -X POST "https://mcp.yourcompany.com/sse" \
    -H "Authorization: Bearer $VALID_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"method": "tools/call", "params": {"name": "google_search", "arguments": {"query": "test '$i'"}}}' &
done
```

### 3. Input Validation Testing
```bash
# Test query length limit
curl -X POST "https://mcp.yourcompany.com/sse" \
  -H "Authorization: Bearer $VALID_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"method": "tools/call", "params": {"name": "google_search", "arguments": {"query": "'$(python -c 'print("A" * 1000)')'"}}}'

# Test injection patterns
curl -X POST "https://mcp.yourcompany.com/sse" \
  -H "Authorization: Bearer $VALID_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"method": "tools/call", "params": {"name": "google_search", "arguments": {"query": "<script>alert(\"xss\")</script>"}}}'
```

## Compliance Considerations

### GDPR/Privacy
- **No personal data logging** in search queries
- **Data minimization** in logs
- **Right to erasure** implementation
- **Privacy by design** principles

### SOC 2 / Security Frameworks
- **Access controls** documentation
- **Change management** procedures
- **Incident response** plans
- **Security monitoring** capabilities

### Industry Standards
- **OWASP Top 10** protection
- **NIST Cybersecurity Framework** alignment
- **ISO 27001** security controls
- **PCI DSS** if handling payment data

## Incident Response

### Security Incident Playbook
1. **Detection**: Monitor logs for security events
2. **Assessment**: Determine severity and impact
3. **Containment**: Isolate affected systems
4. **Eradication**: Remove threat and vulnerabilities
5. **Recovery**: Restore normal operations
6. **Lessons Learned**: Post-incident review

### Emergency Contacts
- Security Team: security@yourcompany.com
- Infrastructure Team: infra@yourcompany.com
- Management: management@yourcompany.com

### Emergency Procedures
```bash
# Emergency server shutdown
sudo systemctl stop serper-mcp

# Revoke all tokens (if using JWKS)
curl -X POST "https://auth.yourcompany.com/revoke-all"

# Enable maintenance mode
sudo nginx -s reload -c /etc/nginx/maintenance.conf
```

## Regular Security Tasks

### Daily
- Review security logs for anomalies
- Monitor rate limiting violations
- Check authentication failure rates

### Weekly
- Analyze security metrics trends
- Review and update threat intelligence
- Test backup and recovery procedures

### Monthly
- Security patch management
- Access control review
- Penetration testing
- Security training updates

### Quarterly
- Full security assessment
- Threat model review
- Incident response testing
- Compliance audit

---

**Last Updated**: 2025-01-06
**Version**: 1.0
**Classification**: Internal Use