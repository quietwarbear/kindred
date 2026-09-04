"""Static trust boundaries for Release 2 store and public positioning."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text()


def test_public_and_auth_positioning_share_reunion_first_promise():
    landing = read("frontend/src/components/LandingPage.jsx")
    auth = read("frontend/src/components/AuthPage.jsx")
    index = read("frontend/public/index.html")
    store = read("frontend/STORE_LISTINGS.md")
    promise = "Plan the reunion. Bring everyone in. Keep the stories."

    assert promise in landing
    assert promise in auth
    assert promise in store
    assert "Private family reunion planning" in index
    assert "does not need to replace WhatsApp" in landing
    assert "Facebook" in landing
    assert "automatically start your own Kindred space" not in auth


def test_deletion_copy_matches_documented_limitations():
    support = read("frontend/src/components/SupportPage.jsx")
    terms = read("frontend/src/components/TermsOfServicePage.jsx")
    settings = read("frontend/src/components/SettingsPage.jsx")
    policy = read("frontend/src/components/PrivacyPolicyPage.jsx")
    data_map = read("docs/PRIVACY_DATA_MAP.md")
    combined = "\n".join((support, terms, settings, policy, data_map)).lower()

    assert "all personal data is permanently removed within 30 days" not in combined
    assert "your personal data will be permanently removed within 30 days" not in combined
    assert "shared content" in combined
    assert "provider records" in combined
    assert "backups" in combined
    assert "legal" in combined


def test_store_privacy_matrix_covers_required_categories_and_processors():
    matrix = read("docs/STORE_PRIVACY_DECLARATION_MATRIX.md").lower()
    for category in (
        "account name, email, phone",
        "profile, community, roles",
        "events, invitations, itineraries, rsvp",
        "photos",
        "voice notes",
        "diagnostics",
        "product interaction and analytics",
        "temporary processing",
        "linked to identity",
        "deletion",
        "retention",
    ):
        assert category in matrix
    for processor in ("apple", "google", "revenuecat", "resend", "vercel", "railway"):
        assert f"| {processor} |" in matrix
    assert "| mongodb / configured database host |" in matrix
    assert "does collect and process user data" in matrix
    assert "do not promise complete removal within 30 days" in matrix


def test_store_metadata_is_reunion_first_and_unpublished():
    store = read("frontend/STORE_LISTINGS.md")
    assert "heyKindred: Reunion Planner" in store
    assert "Family Reunion Planner" in store
    assert "without creating an account" in store
    assert "https://www.heykindred.org/support" in store
    assert "https://www.heykindred.org/privacy" in store
    assert "https://www.heykindred.org" in store
    assert "support@heykindred.org" in store
    assert "Nothing in this file has been published" in store
    assert "No data collected" not in store
    assert "Your Community's Digital Home" not in store
    assert "Elder Grove" not in store


def test_support_identity_uses_branded_address():
    # Owner-approved migration to the branded support address. This mailbox MUST
    # be created and monitored before deploy / store submission (see
    # STORE_LISTINGS.md) — the app now directs support here.
    identity = read("frontend/src/config/publicIdentity.js")
    assert 'canonicalOrigin: "https://www.heykindred.org"' in identity
    assert 'supportEmail: "support@heykindred.org"' in identity
    assert "ubuntu-village.org" not in identity


def test_store_campaign_is_synthetic_reproducible_and_exact_size():
    generator = read("frontend/scripts/generate-store-assets.js")
    readme = read("frontend/store-assets/README.md")
    assert "synthetic-only" in generator
    assert "puppeteer-core" in generator
    assert "const frames = [" in generator
    assert "generated.length" in generator
    assert "generated and validated" in generator.lower()
    assert "No email address appears" in readme
    for width, height in ((1320, 2868), (2064, 2752), (1080, 1920)):
        assert f"outputWidth: {width}" in generator
        assert f"outputHeight: {height}" in generator
        assert f"{width} × {height}" in readme
    for forbidden in (
        "Avery Organizer",
        "The Johnson Family Reunion",
        "reviewer identity",
        "Emergent",
    ):
        assert forbidden not in generator


def test_generated_manifest_is_synthetic_and_contains_exact_campaign():
    manifest_path = ROOT / "frontend/store-assets/manifest.json"
    if not manifest_path.exists():
        return
    manifest = json.loads(manifest_path.read_text())
    assert manifest["synthetic_data"] is True
    assert manifest["published"] is False
    assert len(manifest["files"]) == 15
    assert {
        platform: sum(item["platform"] == platform for item in manifest["files"])
        for platform in {item["platform"] for item in manifest["files"]}
    } == {
        "apple-iphone-6.9": 5,
        "apple-ipad-13": 5,
        "google-phone": 5,
    }
    assert {
        (item["platform"], item["width"], item["height"])
        for item in manifest["files"]
    } == {
        ("apple-iphone-6.9", 1320, 2868),
        ("apple-ipad-13", 2064, 2752),
        ("google-phone", 1080, 1920),
    }
    assert all("sha256" in item and len(item["sha256"]) == 64 for item in manifest["files"])
