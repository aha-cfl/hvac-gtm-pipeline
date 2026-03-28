"""
Module 2: Website Audit Engine
Checks 13 incompetence signals and produces a scored report per business.
"""

import requests
import time
import re
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from config import SCORING


def audit_website(business):
    """Audit a single business website. Returns enriched business dict with score."""
    url = business.get("website", "")
    if not url:
        return {**business, "score": 0, "issues": [], "audit_error": "No website"}

    # Normalize URL
    if not url.startswith("http"):
        url = "https://" + url

    issues = []
    details = {}
    load_time = None

    try:
        # ── Fetch the page ──
        start = time.time()
        resp = requests.get(
            url,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SiteAuditBot/1.0)"},
            allow_redirects=True,
        )
        load_time = round(time.time() - start, 2)
        final_url = resp.url
        html = resp.text
        soup = BeautifulSoup(html, "lxml")

        # ── 1. SSL ──
        if not final_url.startswith("https"):
            issues.append("no_ssl")
            details["ssl"] = "HTTP only"
        else:
            details["ssl"] = "HTTPS ✓"

        # ── 2. Load time ──
        if load_time > 3.0:
            issues.append("slow_load")
        details["load_time_sec"] = load_time

        # ── 3. Phone visible on page ──
        phone_pattern = re.compile(
            r"(\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4})"
        )
        body_text = soup.get_text()
        phones_found = phone_pattern.findall(body_text)
        if not phones_found:
            issues.append("no_phone_visible")
            details["phone_on_page"] = "Not found"
        else:
            details["phone_on_page"] = phones_found[0]

        # ── 4. Click-to-call (tel: link) ──
        tel_links = soup.find_all("a", href=re.compile(r"^tel:"))
        if not tel_links:
            issues.append("no_click_to_call")
            details["click_to_call"] = "Missing"
        else:
            details["click_to_call"] = "Present ✓"

        # ── 5. Contact form ──
        forms = soup.find_all("form")
        has_contact_form = False
        for form in forms:
            inputs = form.find_all("input")
            textareas = form.find_all("textarea")
            if len(inputs) >= 2 or textareas:
                has_contact_form = True
                break
        if not has_contact_form:
            issues.append("no_contact_form")
            details["contact_form"] = "Not found"
        else:
            details["contact_form"] = "Present ✓"

        # ── 6. Google Analytics ──
        has_ga = bool(
            re.search(r"(google-analytics\.com|gtag|UA-\d+|G-[A-Z0-9]+)", html)
        )
        if not has_ga:
            issues.append("no_analytics")
            details["analytics"] = "Not detected"
        else:
            details["analytics"] = "Present ✓"

        # ── 7. Google Tag Manager ──
        has_gtm = bool(re.search(r"googletagmanager\.com", html))
        if not has_gtm:
            issues.append("no_gtm")
            details["gtm"] = "Not detected"
        else:
            details["gtm"] = "Present ✓"

        # ── 8. Meta description ──
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if not meta_desc or not meta_desc.get("content", "").strip():
            issues.append("no_meta_description")
            details["meta_description"] = "Missing"
        else:
            details["meta_description"] = meta_desc["content"][:80] + "..."

        # ── 9. H1 tag ──
        h1 = soup.find("h1")
        if not h1 or not h1.get_text(strip=True):
            issues.append("no_h1")
            details["h1"] = "Missing"
        else:
            details["h1"] = h1.get_text(strip=True)[:60]

        # ── 10. Homepage as landing page (no dedicated landing pages) ──
        # Heuristic: if the page title is just the company name with no service keyword
        title_tag = soup.find("title")
        title_text = title_tag.get_text(strip=True).lower() if title_tag else ""
        service_keywords = ["hvac", "heating", "cooling", "air conditioning", "ac ",
                            "furnace", "repair", "install", "emergency", "service"]
        if title_tag and not any(kw in title_text for kw in service_keywords):
            issues.append("homepage_as_landing")
            details["landing_page"] = "Generic homepage"
        else:
            details["landing_page"] = "Service-focused ✓"

        # ── 11. Schema markup (JSON-LD or microdata) ──
        has_schema = bool(
            soup.find("script", type="application/ld+json")
            or soup.find(attrs={"itemtype": True})
        )
        if not has_schema:
            issues.append("no_schema_markup")
            details["schema"] = "Missing"
        else:
            details["schema"] = "Present ✓"

        # ── 12. Viewport meta (mobile-friendly) ──
        viewport = soup.find("meta", attrs={"name": "viewport"})
        if not viewport:
            issues.append("no_viewport_meta")
            details["viewport"] = "Missing — not mobile-friendly"
        else:
            details["viewport"] = "Present ✓"

        # ── 13. Reviews/testimonials on site ──
        review_keywords = ["review", "testimonial", "customer said", "★", "stars",
                           "rated", "what our customers"]
        has_reviews = any(kw in body_text.lower() for kw in review_keywords)
        if not has_reviews:
            issues.append("no_reviews_on_site")
            details["reviews_on_site"] = "Not found"
        else:
            details["reviews_on_site"] = "Present ✓"

    except requests.exceptions.Timeout:
        issues.append("slow_load")
        details["audit_error"] = "Timeout (>10s)"
    except requests.exceptions.RequestException as e:
        details["audit_error"] = str(e)[:100]

    # ── Calculate score ──
    score = sum(SCORING.get(issue, 0) for issue in issues)

    return {
        **business,
        "score": score,
        "issues": issues,
        "issue_count": len(issues),
        "details": details,
        "load_time": load_time,
        "audited_url": url,
    }


def audit_batch(businesses, delay=1.0):
    """Audit a list of businesses with a delay between requests."""
    results = []
    for i, biz in enumerate(businesses, 1):
        name = biz.get("name", "Unknown")
        url = biz.get("website", "N/A")
        print(f"  [{i}/{len(businesses)}] Auditing: {name} — {url}")
        result = audit_website(biz)
        score = result["score"]
        n_issues = result["issue_count"]
        label = "🔥 HOT" if score >= 80 else ("🟡 WARM" if score >= 50 else "⚪ LOW")
        print(f"    Score: {score}/130 ({n_issues} issues) {label}")
        results.append(result)
        if i < len(businesses):
            time.sleep(delay)

    results.sort(key=lambda x: x["score"], reverse=True)
    return results
