#!/usr/bin/env python3
"""
create_oauth_app.py

Creates:
 - OAuth App Registration (Application)
 - Client secret for the app
 - Service Principal (Enterprise App)
 - Adds Owner (resolved via mailNickname)
 - Assigns API Permissions
 - Updates Internal Notes

Requirements:
 pip install msal requests
 Set environment vars: AZ_TENANT_ID, AZ_CLIENT_ID, AZ_CLIENT_SECRET, OWNER_MAILNICKNAME
"""

import os, requests
from msal import ConfidentialClientApplication

TENANT_ID = os.environ.get("TENANT_ID")
CLIENT_ID = os.environ.get("CLIENT_ID")        # Mgmt App (with Directory.ReadWrite.All)
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")

GRAPH_SCOPE = ["https://graph.microsoft.com/.default"]
GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# ------------------ Helpers ------------------
def get_token():
    app = ConfidentialClientApplication(
        CLIENT_ID, CLIENT_SECRET,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}"
    )
    resp = app.acquire_token_for_client(GRAPH_SCOPE)
    if "access_token" not in resp:
        raise Exception(resp)
    return resp["access_token"]

def graph_call(method, endpoint, payload=None, params=None):
    token = get_token()
    url = GRAPH_BASE + endpoint
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = requests.request(method, url, headers=headers, json=payload, params=params)
    if not r.ok:
        raise Exception(f"{method} {url} failed: {r.status_code} {r.text}")
    if r.text:
        return r.json()
    return {}

# ------------------ Actions ------------------
def create_app(display_name, redirect_uris, notes_text):
    body = {
        "displayName": display_name,
        "signInAudience": "AzureADMyOrg",
        "web": {"redirectUris": redirect_uris},
        "notes": notes_text
    }
    return graph_call("POST", "/applications", body)

def add_secret(app_object_id):
    token = get_token()
    url = f"{GRAPH_BASE}/applications/{app_object_id}/addPassword"
    body = {"passwordCredential": {"displayName": "auto-secret"}}
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=body
    )
    if not r.ok:
        raise Exception(r.text)
    return r.json()

def create_service_principal(appid):
    return graph_call("POST", "/servicePrincipals", {"appId": appid, "accountEnabled": True})

def resolve_user_by_mailnickname(mailnickname: str):
    """Search user by mailNickname and return object id"""
    params = {
        "$filter": f"mailNickname eq '{mailnickname}'",
        "$select": "id,displayName,mailNickname"
    }
    result = graph_call("GET", "/users", params=params)
    users = result.get("value", [])
    if not users:
        raise Exception(f"No user found with mailNickname='{mailnickname}'")
    return users[0]["id"]

def add_owner(app_object_id, owner_object_id):
    body = {"@odata.id": f"{GRAPH_BASE}/directoryObjects/{owner_object_id}"}
    return graph_call("POST", f"/applications/{app_object_id}/owners/$ref", body)

def add_api_permissions(app_object_id):
    permissions = [
        {"id": "df021288-bdef-4463-88db-98f22de89214", "type": "Role"},   # User.Read.All (Application)
        {"id": "e1fe6dd8-ba31-4d61-89e7-88639da4683d", "type": "Scope"}   # User.Read (Delegated)
    ]
    body = {"requiredResourceAccess": [
        {
            "resourceAppId": "00000003-0000-0000-c000-000000000000", # Microsoft Graph
            "resourceAccess": permissions
        }
    ]}
    return graph_call("PATCH", f"/applications/{app_object_id}", body)

def update_internal_notes(app_object_id, notes):
    body = {"notes": notes}
    return graph_call("PATCH", f"/applications/{app_object_id}", body)

# ------------------ Main ------------------
if __name__ == "__main__":
    display_name = os.environ.get("APP_DISPLAY_NAME")
    redirect_uris = os.environ.get("REDIRECT_URIS", "")
    redirect_uris_list = [u.strip() for u in redirect_uris.split(",") if u.strip()]
    NOTES_TEXT = os.environ.get("NOTES_TEXT")

    OWNER_MAILNICKNAME = os.environ.get("OWNER_MAILNICKNAME")

    # Create App
    app = create_app(display_name, redirect_uris_list, NOTES_TEXT)
    print("✅ Application created:", app["appId"])
    
    # Add Secret
    secret = add_secret(app["id"])
    print("✅ Client Secret (save now!):", secret["secretText"])

    # Create Service Principal
    sp = create_service_principal(app["appId"])
    print("✅ Service Principal created:", sp["id"])

    # Resolve and Add Owner
    if OWNER_MAILNICKNAME:
        owner_id = resolve_user_by_mailnickname(OWNER_MAILNICKNAME)
        add_owner(app["id"], owner_id)
        print(f"✅ Owner added (mailNickname={OWNER_MAILNICKNAME}, objectId={owner_id})")
    else:
        print("⚠️ No OWNER_MAILNICKNAME set, skipping owner assignment.")

    # Add API Permissions
    add_api_permissions(app["id"])
    print("✅ API permissions added (Graph User.Read + User.Read.All).")

    # Update Internal Notes
    update_internal_notes(app["id"], "Updated notes: now managed by CloudOps")
    print("✅ Internal notes updated.")
