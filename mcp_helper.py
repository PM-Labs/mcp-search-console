from google.oauth2 import service_account
from googleapiclient.discovery import build
import os
import json
import base64
import requests

# =============================================================================
# Instantly API
# =============================================================================

INSTANTLY_API_BASE = "https://api.instantly.ai/api/v1"


def get_instantly_api_key():
    key = os.getenv('INSTANTLY_API_KEY', '').strip()
    if not key:
        raise ValueError("INSTANTLY_API_KEY environment variable is not set.")
    return key


def instantly_get(path, params=None):
    api_key = get_instantly_api_key()
    p = {"api_key": api_key}
    if params:
        p.update(params)
    resp = requests.get(f"{INSTANTLY_API_BASE}{path}", params=p, timeout=30)
    resp.raise_for_status()
    return resp.json()


def instantly_post(path, payload=None):
    api_key = get_instantly_api_key()
    body = payload or {}
    body["api_key"] = api_key
    resp = requests.post(f"{INSTANTLY_API_BASE}{path}", json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()


# =============================================================================
# Google Auth
# =============================================================================

SCOPES = ['https://www.googleapis.com/auth/webmasters.readonly']


def get_credentials():
    gsc_base64_key = os.getenv('SEARCH_CONSOLE_KEY')
    if not gsc_base64_key:
        raise ValueError("SEARCH_CONSOLE_KEY environment variable is not set.")
    # Strip whitespace/newlines and fix base64 padding (common with PowerShell encoding)
    key_b64 = gsc_base64_key.strip()
    padding_needed = (4 - len(key_b64) % 4) % 4
    key_b64 += '=' * padding_needed
    decoded_bytes = base64.b64decode(key_b64)
    key_info = json.loads(decoded_bytes.decode('utf-8'))
    return service_account.Credentials.from_service_account_info(key_info, scopes=SCOPES)


def get_service():
    return build('webmasters', 'v3', credentials=get_credentials())


# =============================================================================
# MCP Protocol Request Routing
# =============================================================================

def handle_request(method, params):
    if method == "initialize":
        return handle_initialize()
    elif method == "tools/list":
        return handle_tools_list()
    elif method == "tools/call":
        return handle_tool_call(params)
    elif method in ("notifications/initialized", "notifications/cancelled"):
        return {}
    else:
        raise ValueError(f"Method not found: {method}")


# =============================================================================
# MCP Protocol Handlers
# =============================================================================

def handle_initialize():
    return {
        "protocolVersion": "2024-11-05",
        "serverInfo": {
            "name": "search_console_mcp",
            "version": "1.0.0"
        },
        "capabilities": {
            "tools": {}
        }
    }


def handle_tools_list():
    return {
        "tools": [
            # ------------------------------------------------------------------
            # Instantly tools
            # ------------------------------------------------------------------
            {
                "name": "instantly_list_campaigns",
                "description": (
                    "List all Instantly.ai email outreach campaigns for the account. "
                    "Returns campaign IDs, names, and status."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "skip": {
                            "type": "integer",
                            "description": "Number of campaigns to skip (for pagination). Defaults to 0.",
                            "default": 0
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of campaigns to return (1-100). Defaults to 100.",
                            "default": 100,
                            "minimum": 1,
                            "maximum": 100
                        }
                    },
                    "required": [],
                    "additionalProperties": False
                }
            },
            {
                "name": "instantly_get_campaign_analytics",
                "description": (
                    "Get summary analytics for one or all Instantly campaigns: "
                    "emails sent, opened, replied, bounced, unsubscribed, etc."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "campaign_id": {
                            "type": "string",
                            "description": "Campaign ID to get analytics for. Omit to get analytics for all campaigns."
                        },
                        "start_date": {
                            "type": "string",
                            "description": "Start date filter in YYYY-MM-DD format."
                        },
                        "end_date": {
                            "type": "string",
                            "description": "End date filter in YYYY-MM-DD format."
                        }
                    },
                    "required": [],
                    "additionalProperties": False
                }
            },
            {
                "name": "instantly_get_leads",
                "description": (
                    "List leads (contacts) in a specific Instantly campaign. "
                    "Returns email, name, status, and other lead data."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "campaign_id": {
                            "type": "string",
                            "description": "The campaign ID to retrieve leads from."
                        },
                        "skip": {
                            "type": "integer",
                            "description": "Number of leads to skip for pagination. Defaults to 0.",
                            "default": 0
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum leads to return (1-100). Defaults to 100.",
                            "default": 100,
                            "minimum": 1,
                            "maximum": 100
                        }
                    },
                    "required": ["campaign_id"],
                    "additionalProperties": False
                }
            },
            {
                "name": "instantly_add_leads",
                "description": (
                    "Add one or more leads (contacts) to an Instantly campaign. "
                    "Each lead must include at least an email address."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "campaign_id": {
                            "type": "string",
                            "description": "The campaign ID to add leads to."
                        },
                        "leads": {
                            "type": "array",
                            "description": "Array of lead objects to add.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "email": {"type": "string", "description": "Lead email address (required)."},
                                    "first_name": {"type": "string"},
                                    "last_name": {"type": "string"},
                                    "company_name": {"type": "string"},
                                    "personalization": {"type": "string", "description": "Custom personalisation line for this lead."},
                                    "phone": {"type": "string"},
                                    "website": {"type": "string"},
                                    "custom1": {"type": "string"},
                                    "custom2": {"type": "string"},
                                    "custom3": {"type": "string"}
                                },
                                "required": ["email"]
                            },
                            "minItems": 1
                        },
                        "skip_if_in_workspace": {
                            "type": "boolean",
                            "description": "Skip adding a lead if it already exists in any campaign in the workspace. Defaults to false.",
                            "default": False
                        }
                    },
                    "required": ["campaign_id", "leads"],
                    "additionalProperties": False
                }
            },
            {
                "name": "instantly_get_account_vitals",
                "description": (
                    "Retrieve high-level account information and sending statistics "
                    "for the authenticated Instantly account."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False
                }
            },
            # ------------------------------------------------------------------
            # Google Search Console tools
            # ------------------------------------------------------------------
            {
                "name": "list_sites",
                "description": (
                    "List all Google Search Console properties the service account has access to. "
                    "Use this first to discover available client sites and their exact site_url values "
                    "before running queries."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False
                }
            },
            {
                "name": "query_search_analytics",
                "description": (
                    "Query Google Search Console search analytics for a specific property. "
                    "Returns clicks, impressions, CTR, and position data segmented by the specified dimensions. "
                    "Call list_sites first to get valid site_url values."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "site_url": {
                            "type": "string",
                            "description": (
                                "The GSC property URL exactly as returned by list_sites "
                                "(e.g. 'https://example.com/' or 'sc-domain:example.com')."
                            )
                        },
                        "start_date": {
                            "type": "string",
                            "description": "Start date in YYYY-MM-DD format."
                        },
                        "end_date": {
                            "type": "string",
                            "description": "End date in YYYY-MM-DD format."
                        },
                        "dimensions": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["query", "page", "country", "device", "date", "searchAppearance"]
                            },
                            "description": "Dimensions to group results by. Defaults to ['query'].",
                            "default": ["query"]
                        },
                        "row_limit": {
                            "type": "integer",
                            "description": "Maximum rows to return (1-25000). Defaults to 25. For date-trended queries set this to cover the full number of days in the range.",
                            "default": 25,
                            "minimum": 1,
                            "maximum": 25000
                        },
                        "start_row": {
                            "type": "integer",
                            "description": "Zero-based row offset for pagination. Defaults to 0.",
                            "default": 0
                        },
                        "search_type": {
                            "type": "string",
                            "enum": ["web", "image", "video", "news", "discover", "googleNews"],
                            "description": "Search surface to filter by. Defaults to 'web'.",
                            "default": "web"
                        },
                        "aggregation_type": {
                            "type": "string",
                            "enum": ["auto", "byPage", "byProperty"],
                            "description": "How data is aggregated. Defaults to 'auto'.",
                            "default": "auto"
                        },
                        "dimension_filter_groups": {
                            "type": "array",
                            "description": (
                                "Filter groups to narrow results. Filters within a group are combined with AND logic. "
                                "Country values: ISO 3166-1 alpha-3 (e.g. 'GBR', 'USA', 'AUS'). "
                                "Device values: 'DESKTOP', 'MOBILE', 'TABLET'."
                            ),
                            "items": {
                                "type": "object",
                                "properties": {
                                    "groupType": {
                                        "type": "string",
                                        "enum": ["and"],
                                        "default": "and"
                                    },
                                    "filters": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "dimension": {
                                                    "type": "string",
                                                    "enum": ["query", "page", "country", "device", "searchAppearance"]
                                                },
                                                "operator": {
                                                    "type": "string",
                                                    "enum": ["equals", "notEquals", "contains", "notContains", "includingRegex", "excludingRegex"],
                                                    "default": "equals"
                                                },
                                                "expression": {
                                                    "type": "string",
                                                    "description": "The filter value."
                                                }
                                            },
                                            "required": ["dimension", "expression"]
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "required": ["site_url", "start_date", "end_date"],
                    "additionalProperties": False
                }
            }
        ]
    }


def handle_tool_call(params):
    tool_name = params.get("name")
    arguments = params.get("arguments", {})

    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except Exception:
            return {
                "isError": True,
                "content": [{"type": "text", "text": "Invalid arguments: expected object or JSON string."}]
            }

    # Instantly tools
    if tool_name == "instantly_list_campaigns":
        try:
            result = instantly_list_campaigns(arguments)
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
        except Exception as e:
            return {"isError": True, "content": [{"type": "text", "text": f"Tool error (instantly_list_campaigns): {str(e)}"}]}

    elif tool_name == "instantly_get_campaign_analytics":
        try:
            result = instantly_get_campaign_analytics(arguments)
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
        except Exception as e:
            return {"isError": True, "content": [{"type": "text", "text": f"Tool error (instantly_get_campaign_analytics): {str(e)}"}]}

    elif tool_name == "instantly_get_leads":
        try:
            result = instantly_get_leads(arguments)
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
        except Exception as e:
            return {"isError": True, "content": [{"type": "text", "text": f"Tool error (instantly_get_leads): {str(e)}"}]}

    elif tool_name == "instantly_add_leads":
        try:
            result = instantly_add_leads(arguments)
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
        except Exception as e:
            return {"isError": True, "content": [{"type": "text", "text": f"Tool error (instantly_add_leads): {str(e)}"}]}

    elif tool_name == "instantly_get_account_vitals":
        try:
            result = instantly_get_account_vitals()
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
        except Exception as e:
            return {"isError": True, "content": [{"type": "text", "text": f"Tool error (instantly_get_account_vitals): {str(e)}"}]}

    # Google Search Console tools
    elif tool_name == "list_sites":
        try:
            result = list_sites()
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
        except Exception as e:
            return {"isError": True, "content": [{"type": "text", "text": f"Tool error (list_sites): {str(e)}"}]}

    elif tool_name == "query_search_analytics":
        try:
            result = run_search_analytics_query(arguments)
            return {"content": [{"type": "text", "text": json.dumps(result, indent=2)}]}
        except Exception as e:
            return {"isError": True, "content": [{"type": "text", "text": f"Tool error (query_search_analytics): {str(e)}"}]}

    else:
        return {"isError": True, "content": [{"type": "text", "text": f"Tool not found: {tool_name}"}]}


# =============================================================================
# Tool Implementations
# =============================================================================

def list_sites():
    """List all GSC properties the service account has access to."""
    service = get_service()
    response = service.sites().list().execute()
    sites = response.get('siteEntry', [])
    return {
        "sites": [
            {
                "site_url": site['siteUrl'],
                "permission_level": site['permissionLevel']
            }
            for site in sites
        ],
        "total": len(sites)
    }


def run_search_analytics_query(arguments):
    """Execute a structured GSC search analytics query."""
    site_url = arguments.get('site_url')
    start_date = arguments.get('start_date')
    end_date = arguments.get('end_date')

    if not site_url or not start_date or not end_date:
        raise ValueError("site_url, start_date, and end_date are required.")

    payload = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": arguments.get('dimensions', ['query']),
        "rowLimit": arguments.get('row_limit', 25),
        "startRow": arguments.get('start_row', 0),
        "type": arguments.get('search_type', 'web'),
        "aggregationType": arguments.get('aggregation_type', 'auto'),
    }

    filter_groups = arguments.get('dimension_filter_groups')
    if filter_groups:
        payload['dimensionFilterGroups'] = filter_groups

    service = get_service()
    response = service.searchanalytics().query(siteUrl=site_url, body=payload).execute()

    rows = response.get('rows', [])
    dimensions = payload['dimensions']

    results = []
    for row in rows:
        data = {}
        keys = row.get('keys', [])
        for i, dim in enumerate(dimensions):
            data[dim] = keys[i] if i < len(keys) else None
        data['clicks'] = row.get('clicks', 0)
        data['impressions'] = row.get('impressions', 0)
        data['ctr'] = round(row.get('ctr', 0) * 100, 4)
        data['position'] = round(row.get('position', 0), 2)
        results.append(data)

    return {
        "site_url": site_url,
        "start_date": start_date,
        "end_date": end_date,
        "dimensions": dimensions,
        "row_count": len(results),
        "rows": results
    }


# =============================================================================
# Instantly Tool Implementations
# =============================================================================

def instantly_list_campaigns(arguments):
    """List all Instantly campaigns."""
    params = {
        "skip": arguments.get("skip", 0),
        "limit": arguments.get("limit", 100),
    }
    data = instantly_get("/campaign/list", params)
    return data


def instantly_get_campaign_analytics(arguments):
    """Get analytics summary for campaigns."""
    params = {}
    if arguments.get("campaign_id"):
        params["campaign_id"] = arguments["campaign_id"]
    if arguments.get("start_date"):
        params["start_date"] = arguments["start_date"]
    if arguments.get("end_date"):
        params["end_date"] = arguments["end_date"]
    return instantly_get("/analytics/campaign/summary", params)


def instantly_get_leads(arguments):
    """Get leads from a campaign."""
    campaign_id = arguments.get("campaign_id")
    if not campaign_id:
        raise ValueError("campaign_id is required.")
    params = {
        "campaign_id": campaign_id,
        "skip": arguments.get("skip", 0),
        "limit": arguments.get("limit", 100),
    }
    return instantly_get("/lead/get", params)


def instantly_add_leads(arguments):
    """Add leads to a campaign."""
    campaign_id = arguments.get("campaign_id")
    leads = arguments.get("leads")
    if not campaign_id or not leads:
        raise ValueError("campaign_id and leads are required.")
    payload = {
        "campaign_id": campaign_id,
        "leads": leads,
        "skip_if_in_workspace": arguments.get("skip_if_in_workspace", False),
    }
    return instantly_post("/lead/add", payload)


def instantly_get_account_vitals():
    """Get account-level information."""
    return instantly_get("/account/list")
