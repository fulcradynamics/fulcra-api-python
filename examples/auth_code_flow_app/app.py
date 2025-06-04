from flask import Flask, redirect, request, url_for, session, render_template_string
from fulcra_api.core import FulcraAPI
import json # For pretty printing the metrics catalog

# Configuration
# IMPORTANT: This redirect URI must be added to your Auth0 application's
# "Allowed Callback URLs" in the Auth0 dashboard.
REDIRECT_URI = "http://localhost:4499/callback"

CUSTOM_OIDC_DOMAIN = None
CUSTOM_OIDC_CLIENT_ID = None
CUSTOM_OIDC_SCOPE = None
CUSTOM_OIDC_AUDIENCE = None

app = Flask(__name__)
# It's important to set a secret key for session management in Flask.
# In a real application, use a strong, randomly generated key and keep it secret.
app.secret_key = "your_very_secret_key_here_change_me" 

fulcra_client = FulcraAPI(
    oidc_domain=CUSTOM_OIDC_DOMAIN,
    oidc_client_id=CUSTOM_OIDC_CLIENT_ID,
    oidc_scope=CUSTOM_OIDC_SCOPE,
    oidc_audience=CUSTOM_OIDC_AUDIENCE
)

# HTML Templates (in-line for simplicity)
HOME_TEMPLATE = """
<!DOCTYPE html>
<html>
<head><title>Fulcra API Auth Code Flow Demo</title></head>
<body>
    <h1>Fulcra API Auth Code Flow Demo</h1>
    {% if fulcra_userid %}
        <p>Logged in as: {{ fulcra_userid }}</p>
        <p><a href="{{ url_for('metrics') }}">View Metrics Catalog</a></p>
        <p><a href="{{ url_for('logout') }}">Logout</a></p>
    {% else %}
        <p><a href="{{ url_for('login') }}">Login with Fulcra</a></p>
    {% endif %}
</body>
</html>
"""

METRICS_TEMPLATE = """
<!DOCTYPE html>
<html>
<head><title>Metrics Catalog</title></head>
<body>
    <h1>Metrics Catalog</h1>
    <p><a href="{{ url_for('home') }}">Home</a></p>
    <pre>{{ metrics_data | tojson(indent=4) }}</pre>
</body>
</html>
"""

ERROR_TEMPLATE = """
<!DOCTYPE html>
<html>
<head><title>Error</title></head>
<body>
    <h1>An Error Occurred</h1>
    <p>{{ error_message }}</p>
    <p><a href="{{ url_for('home') }}">Go to Home Page</a></p>
</body>
</html>
"""

@app.route('/')
def home():
    fulcra_userid = session.get('fulcra_userid')
    return render_template_string(HOME_TEMPLATE, fulcra_userid=fulcra_userid)

@app.route('/login')
def login():
    # Generate the authorization URL
    authorization_url = fulcra_client.get_authorization_code_url(
        redirect_uri=REDIRECT_URI,
        state="some_random_state_string" # Optional: for CSRF protection
    )
    # Redirect the user to the authorization URL
    return redirect(authorization_url)

@app.route('/callback')
def callback():
    # Auth0 will redirect the user here after authentication
    error = request.args.get('error')
    if error:
        error_description = request.args.get('error_description', 'No description provided.')
        return render_template_string(ERROR_TEMPLATE, error_message=f"Auth0 Error: {error} - {error_description}")

    code = request.args.get('code')
    # Optional: Verify state parameter here if you sent one
    # received_state = request.args.get('state')
    # if received_state != "some_random_state_string":
    #     return render_template_string(ERROR_TEMPLATE, error_message="State mismatch. Possible CSRF attack.")

    if not code:
        return render_template_string(ERROR_TEMPLATE, error_message="Authorization code not found in callback.")

    try:
        # Exchange the authorization code for an access token
        fulcra_client.authorize_with_authorization_code(
            code=code,
            redirect_uri=REDIRECT_URI
        )
        # Store token info or user identifier in session if needed for subsequent requests
        # For this demo, FulcraAPI caches the token internally.
        # We can store the user ID for display purposes.
        session['fulcra_userid'] = fulcra_client.get_fulcra_userid()
        return redirect(url_for('metrics'))
    except Exception as e:
        return render_template_string(ERROR_TEMPLATE, error_message=f"Failed to exchange authorization code for token: {str(e)}")

@app.route('/metrics')
def metrics():
    if not fulcra_client.fulcra_cached_access_token:
        return redirect(url_for('login'))
    
    try:
        # Make an API call
        metrics_data = fulcra_client.metrics_catalog()
        return render_template_string(METRICS_TEMPLATE, metrics_data=metrics_data)
    except Exception as e:
        # If token expired or other API error, could try to refresh or re-login
        if fulcra_client.fulcra_cached_refresh_token:
            try:
                refreshed = fulcra_client.refresh_access_token()
                if refreshed:
                    metrics_data = fulcra_client.metrics_catalog()
                    return render_template_string(METRICS_TEMPLATE, metrics_data=metrics_data)
                else:
                    # Clear session and redirect to login if refresh fails
                    session.pop('fulcra_userid', None)
                    fulcra_client.fulcra_cached_access_token = None
                    fulcra_client.fulcra_cached_refresh_token = None
                    fulcra_client.fulcra_cached_access_token_expiration = None
                    return render_template_string(ERROR_TEMPLATE, error_message=f"Failed to refresh token. Please login again. Original error: {str(e)}")
            except Exception as refresh_e:
                session.pop('fulcra_userid', None)
                fulcra_client.fulcra_cached_access_token = None
                fulcra_client.fulcra_cached_refresh_token = None
                fulcra_client.fulcra_cached_access_token_expiration = None
                return render_template_string(ERROR_TEMPLATE, error_message=f"Error during token refresh: {str(refresh_e)}. Please login again.")
        
        session.pop('fulcra_userid', None)
        fulcra_client.fulcra_cached_access_token = None
        fulcra_client.fulcra_cached_refresh_token = None
        fulcra_client.fulcra_cached_access_token_expiration = None
        return render_template_string(ERROR_TEMPLATE, error_message=f"API call failed: {str(e)}. Please login again.")

@app.route('/logout')
def logout():
    # Clear session data
    session.pop('fulcra_userid', None)
    
    # Clear cached tokens in FulcraAPI client
    # Note: This is a client-side logout. For a full Auth0 logout,
    # you would redirect to the Auth0 logout endpoint.
    # https://auth0.com/docs/api/authentication#logout
    fulcra_client.fulcra_cached_access_token = None
    fulcra_client.fulcra_cached_refresh_token = None
    fulcra_client.fulcra_cached_access_token_expiration = None
    
    # For a full Single Sign-Out (SSO) with an OIDC provider like Auth0, you'd redirect to:
    # client_id = fulcra_client.oidc_client_id # Use instance specific client_id
    # return_to_url = url_for('home', _external=True)
    # oidc_domain = fulcra_client.oidc_domain # Use instance specific domain
    # logout_url = f"https://{oidc_domain}/v2/logout?client_id={client_id}&returnTo={return_to_url}" # Path might vary by provider
    # return redirect(logout_url)
    
    return redirect(url_for('home'))

if __name__ == '__main__':
    # Make sure to run with HTTPS if deploying, for security of tokens.
    # For local development, HTTP is often fine but be aware of risks.
    # Flask's dev server is not for production. Use a proper WSGI server like Gunicorn.
    app.run(port=4499, debug=True)
