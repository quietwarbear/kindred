import logging
import os

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import HTMLResponse, JSONResponse

from db import client, communities_collection, invites_collection
from routes.activity import router as activity_router
from routes.auth import router as auth_router
from routes.communications import router as communications_router
from routes.community import router as community_router
from routes.events import router as events_router
from routes.finance import router as finance_router
from routes.legacy import router as legacy_router
from routes.polls import router as polls_router
from routes.revenuecat import router as revenuecat_router
from routes.subscriptions import router as subscriptions_router
from routes.timeline import router as timeline_router

load_dotenv()

app = FastAPI(title="Kindred API")

# Health check
api_root = APIRouter(prefix="/api")


@api_root.get("/")
async def root():
    return {"message": "Kindred API is ready."}


# Include all domain routers
app.include_router(api_root)
app.include_router(activity_router)
app.include_router(auth_router)
app.include_router(community_router)
app.include_router(communications_router)
app.include_router(events_router)
app.include_router(finance_router)
app.include_router(legacy_router)
app.include_router(polls_router)
app.include_router(revenuecat_router)
app.include_router(subscriptions_router)
app.include_router(timeline_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# ===================== INVITE LANDING PAGE =====================

INVITE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Join {community_name} on heyKindred</title>
  <meta property="og:title" content="Join {community_name} on heyKindred" />
  <meta property="og:description" content="You've been invited to a Kindred community — plan events, share memories, and preserve your family's legacy." />
  <meta property="og:type" content="website" />
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
           background: linear-gradient(135deg, #F5F0EB, #EDE4D9); min-height: 100vh;
           display: flex; align-items: center; justify-content: center; padding: 24px; }}
    .card {{ background: white; border-radius: 20px; padding: 40px 32px; max-width: 400px;
             width: 100%; text-align: center; box-shadow: 0 8px 30px rgba(0,0,0,0.08); }}
    .icon {{ width: 72px; height: 72px; background: #F5F0EB; border-radius: 50%;
             display: flex; align-items: center; justify-content: center; margin: 0 auto 24px;
             font-size: 32px; }}
    h1 {{ font-family: Georgia, 'Times New Roman', serif; font-size: 24px; color: #1a1a1a; margin-bottom: 8px; }}
    .community {{ font-size: 18px; color: #78593A; font-weight: 600; margin-bottom: 16px; }}
    p {{ color: #6b7280; font-size: 15px; line-height: 1.5; margin-bottom: 24px; }}
    .code-box {{ background: #F9FAFB; border: 2px dashed #D1D5DB; border-radius: 12px;
                 padding: 16px; margin-bottom: 24px; }}
    .code-label {{ font-size: 11px; color: #9CA3AF; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px; }}
    .code {{ font-size: 28px; font-weight: 700; letter-spacing: 3px; color: #1a1a1a; font-family: monospace; }}
    .btn {{ display: block; width: 100%; padding: 14px; border-radius: 12px; font-size: 16px;
            font-weight: 600; text-decoration: none; margin-bottom: 12px; transition: opacity 0.2s; }}
    .btn:hover {{ opacity: 0.9; }}
    .btn-ios {{ background: #000; color: #fff; }}
    .btn-android {{ background: #16A34A; color: #fff; }}
    .or {{ color: #9CA3AF; font-size: 13px; margin-bottom: 12px; }}
    .footer {{ color: #9CA3AF; font-size: 12px; margin-top: 20px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">&#129309;</div>
    <h1>You're Invited!</h1>
    <div class="community">{community_name}</div>
    <p>Join this Kindred community to plan events, share memories, and stay connected with your people.</p>
    <div class="code-box">
      <div class="code-label">Invite Code</div>
      <div class="code">{code}</div>
    </div>
    <div class="or">Download the app and enter the code above</div>
    <a href="https://apps.apple.com/app/heykindred/id6760608478" class="btn btn-ios">Download on App Store</a>
    <a href="https://play.google.com/store/apps/details?id=com.ubuntumarket.kindred" class="btn btn-android">Get on Google Play</a>
    <div class="footer">heyKindred by Ubuntu Market LLC</div>
  </div>
  <script>
    var code = "{code}";
    var isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
    var isAndroid = /Android/.test(navigator.userAgent);
    if (isIOS || isAndroid) {{
      var deepLink = "kindred://invite/" + code;
      var timeout = setTimeout(function() {{ }}, 1500);
      window.location.href = deepLink;
      window.addEventListener("blur", function() {{ clearTimeout(timeout); }});
    }}
  </script>
</body>
</html>"""

INVITE_NOT_FOUND_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>heyKindred</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
           background: linear-gradient(135deg, #F5F0EB, #EDE4D9); min-height: 100vh;
           display: flex; align-items: center; justify-content: center; padding: 24px; }}
    .card {{ background: white; border-radius: 20px; padding: 40px 32px; max-width: 400px;
             width: 100%; text-align: center; box-shadow: 0 8px 30px rgba(0,0,0,0.08); }}
    h1 {{ font-family: Georgia, 'Times New Roman', serif; font-size: 24px; color: #1a1a1a; margin-bottom: 16px; }}
    p {{ color: #6b7280; font-size: 15px; line-height: 1.5; margin-bottom: 24px; }}
    .btn {{ display: block; width: 100%; padding: 14px; border-radius: 12px; font-size: 16px;
            font-weight: 600; text-decoration: none; background: #78593A; color: #fff; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>Invite Not Found</h1>
    <p>This invite code doesn't match any community. It may have expired or been revoked.</p>
    <a href="https://heykindred.com" class="btn">Visit heyKindred</a>
  </div>
</body>
</html>"""


@app.get("/invite/{code}", response_class=HTMLResponse)
async def invite_landing(code: str):
    """Public landing page for invite links — no auth required."""
    code = code.strip().upper()
    invite = await invites_collection.find_one({"code": code}, {"_id": 0, "community_id": 1, "code": 1})
    community_name = "a Kindred Community"
    if invite:
        community = await communities_collection.find_one(
            {"id": invite["community_id"]}, {"_id": 0, "name": 1}
        )
        if community:
            community_name = community["name"]
        html = INVITE_HTML.replace("{community_name}", community_name).replace("{code}", invite["code"])
        return HTMLResponse(content=html)
    return HTMLResponse(content=INVITE_NOT_FOUND_HTML, status_code=404)


@app.get("/.well-known/apple-app-site-association")
async def apple_app_site_association():
    return JSONResponse(content={
        "applinks": {
            "apps": [],
            "details": [
                {
                    "appID": "H543QXDYUW.com.ubuntumarket.kindred",
                    "paths": ["/invite/*"]
                }
            ]
        }
    }, headers={"Content-Type": "application/json"})


@app.get("/.well-known/assetlinks.json")
async def android_asset_links():
    return JSONResponse(content=[
        {
            "relation": ["delegate_permission/common.handle_all_urls"],
            "target": {
                "namespace": "android_app",
                "package_name": "com.ubuntumarket.kindred",
                "sha256_cert_fingerprints": [
                    "BE:F3:3C:3E:C2:DF:E1:F4:34:70:21:07:8C:81:4B:8D:C8:A2:95:56:2C:28:DA:F0:C4:33:B8:0B:63:32:C6:49"
                ]
            }
        }
    ])


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
