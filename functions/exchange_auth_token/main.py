import functions_framework
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
import json

# Load client secrets from a file
with open('config.json', 'r') as f:
    client_config = json.load(f)

CLIENT_ID = client_config['web']['client_id']
CLIENT_SECRET = client_config['web']['client_secret']

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/drive.readonly"
]

# The redirect_uri must be configured in the Google Cloud Console for your client ID.
# For this server-side flow, it can be a simple placeholder.
REDIRECT_URI = "http://localhost"

@functions_framework.http
def exchange_auth_token(request):
    """HTTP Cloud Function to exchange an authorization code for credentials.
    Args:
        request (flask.Request): The request object.
        <http://flask.pocoo.org/docs/1.0/api/#flask.Request>
    Returns:
        The response text, or any set of values that can be turned into a
        Response object using `make_response`
        <http://flask.pocoo.org/docs/1.0/api/#flask.make_response>.
    """
    # Set CORS headers for preflight requests
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600'
        }
        return ('', 204, headers)

    # Set CORS headers for the main request
    headers = {
        'Access-Control-Allow-Origin': '*'
    }

    request_json = request.get_json(silent=True)
    if not request_json or 'authCode' not in request_json:
        return ('Missing authCode in request body', 400, headers)

    auth_code = request_json['authCode']

    try:
        flow = Flow.from_client_config(
            client_config={
                "web": {
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [REDIRECT_URI],
                    "scopes": SCOPES
                }
            },
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )

        # Exchange the authorization code for credentials
        flow.fetch_token(code=auth_code)
        credentials = flow.credentials

        # You can now use these credentials to access Google APIs.
        # For now, we'll just return them to the client for verification.
        creds_json = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }

        return (json.dumps(creds_json), 200, headers)

    except Exception as e:
        return (f"An error occurred: {e}", 500, headers)