from flask import Flask, request, jsonify, redirect
import mcp_helper
import os
import json
import logging
import hashlib
import base64
import secrets
import time
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse

# =============================================================================
# App setup
# =============================================================================

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

AUTH_TOKEN = os.getenv('MCP_AUTH_TOKEN', '').strip()
OAUTH_CLIENT_ID = os.getenv('OAUTH_CLIENT_ID', 'claude-pathfinder').strip()
OAUTH_CLIENT_SECRET = os.getenv('OAUTH_CLIENT_SECRET', '').strip()

# In-memory auth code store (single-instance; fine for Cloud Run min=0)
auth_codes = {}

# =============================================================================
# OAuth 2.0 PKCE — Discovery + Auth Endpoints
# =============================================================================

@app.route('/.well-known/oauth-protected-resource')
def oauth_protected_resource():
    base = f"https://{request.host}"
    return jsonify({
        "resource": f"{base}/mcp",
        "authorization_servers": [base]
    })


@app.route('/.well-known/oauth-authorization-server')
def oauth_authorization_server():
    base = f"https://{request.host}"
    return jsonify({
        "issuer": base,
        "authorization_endpoint": f"{base}/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "grant_types_supported": ["authorization_code", "client_credentials"],
        "code_challenge_methods_supported": ["S256"],
        "response_types_supported": ["code"]
    })


@app.route('/authorize')
def authorize():
    response_type = request.args.get('response_type')
    client_id = request.args.get('client_id')
    redirect_uri = request.args.get('redirect_uri')
    code_challenge = request.args.get('code_challenge')
    code_challenge_method = request.args.get('code_challenge_method', 'S256')
    state = request.args.get('state')

    if client_id != OAUTH_CLIENT_ID:
        return jsonify({"error": "invalid_client"}), 401
    if response_type != 'code':
        return jsonify({"error": "unsupported_response_type"}), 400
    if not code_challenge:
        return jsonify({"error": "code_challenge required"}), 400

    code = secrets.token_urlsafe(32)
    auth_codes[code] = {
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "redirect_uri": redirect_uri,
        "expires_at": time.time() + 300
    }

    parsed = urlparse(redirect_uri)
    params = parse_qs(parsed.query)
    params['code'] = [code]
    if state:
        params['state'] = [state]
    new_query = urlencode({k: v[0] for k, v in params.items()})
    redirect_url = urlunparse(parsed._replace(query=new_query))
    return redirect(redirect_url)


@app.route('/oauth/token', methods=['POST'])
def oauth_token():
    if not OAUTH_CLIENT_ID or not AUTH_TOKEN:
        return jsonify({"error": "server_misconfigured"}), 500

    body = request.get_json(silent=True) or {}
    form = request.form

    def get_param(key):
        return form.get(key) or body.get(key)

    grant_type = get_param('grant_type')

    if grant_type == 'authorization_code':
        code = get_param('code')
        code_verifier = get_param('code_verifier')
        redirect_uri = get_param('redirect_uri')

        stored = auth_codes.get(code)
        if not stored or stored['expires_at'] < time.time():
            return jsonify({"error": "invalid_grant"}), 400

        expected = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).rstrip(b'=').decode()

        if expected != stored['code_challenge']:
            return jsonify({"error": "invalid_grant"}), 400
        if redirect_uri and redirect_uri != stored['redirect_uri']:
            return jsonify({"error": "invalid_grant"}), 400

        del auth_codes[code]
        return jsonify({"access_token": AUTH_TOKEN, "token_type": "Bearer", "expires_in": 86400})

    # client_credentials grant
    if not OAUTH_CLIENT_SECRET:
        return jsonify({"error": "server_misconfigured"}), 500

    client_id = None
    client_secret = None
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Basic '):
        decoded = base64.b64decode(auth_header[6:]).decode()
        colon = decoded.index(':')
        client_id = decoded[:colon]
        client_secret = decoded[colon + 1:]
    else:
        client_id = get_param('client_id')
        client_secret = get_param('client_secret')

    if client_id != OAUTH_CLIENT_ID or client_secret != OAUTH_CLIENT_SECRET:
        return jsonify({"error": "invalid_client"}), 401

    return jsonify({"access_token": AUTH_TOKEN, "token_type": "Bearer", "expires_in": 86400})


# =============================================================================
# Bearer Token Auth Helper
# =============================================================================

def require_auth():
    """Returns a Flask response tuple if auth fails, None if OK."""
    if not AUTH_TOKEN:
        return None  # Auth not configured — allow through
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return (
            jsonify({"error": "Unauthorized"}),
            401,
            {'WWW-Authenticate': f'Bearer resource_metadata="https://{request.host}/.well-known/oauth-protected-resource"'}
        )
    if auth_header[7:] != AUTH_TOKEN:
        return (
            jsonify({"error": "Unauthorized"}),
            401,
            {'WWW-Authenticate': 'Bearer error="invalid_token"'}
        )
    return None


# =============================================================================
# Health Check
# =============================================================================

@app.route('/health')
def health():
    return jsonify({"status": "ok"})


# =============================================================================
# MCP Endpoint
# =============================================================================

@app.route('/mcp', methods=['POST'])
def mcp_endpoint():
    auth_error = require_auth()
    if auth_error:
        return auth_error

    request_id = None

    try:
        data = request.get_json(force=True)
    except Exception as e:
        app.logger.exception("Parse error in /mcp")
        return jsonify({
            "jsonrpc": "2.0",
            "error": {"code": -32700, "message": f"Parse error: {str(e)}"},
            "id": None
        }), 200

    method = data.get("method")
    params = data.get("params", {})
    request_id = data.get("id")

    app.logger.info("MCP request: method=%s id=%s", method, request_id)

    # Notifications must not return a JSON-RPC body
    if request_id is None:
        app.logger.info("Notification: %s (no response body)", method)
        return ("", 204)

    try:
        result = mcp_helper.handle_request(method, params)

        if method in ("tools/list", "tools/call"):
            try:
                preview = json.dumps(result, ensure_ascii=False)[:300]
            except Exception:
                preview = str(result)[:300]
            app.logger.info("%s result preview: %s", method, preview)

        return jsonify({"jsonrpc": "2.0", "result": result, "id": request_id}), 200

    except Exception as e:
        app.logger.exception("Unhandled error in /mcp for method=%s id=%s", method, request_id)
        if method == "tools/call":
            return jsonify({
                "jsonrpc": "2.0",
                "result": {
                    "isError": True,
                    "content": [{"type": "text", "text": f"Internal tool error: {str(e)}"}]
                },
                "id": request_id
            }), 200
        return jsonify({
            "jsonrpc": "2.0",
            "error": {"code": -32603, "message": f"Internal error: {str(e)}"},
            "id": request_id
        }), 200


if __name__ == "__main__":
    app.run()
