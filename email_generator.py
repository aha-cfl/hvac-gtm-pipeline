"""
Module 3: Diagnostic Email Generator
Generates personalized cold outreach emails based on audit findings.
The pitch is diagnostic, not salesy — "you're bleeding here" not "hire me."
"""


def _issue_to_english(issue, details):
    """Convert an audit issue code to a plain-English finding."""
    mapping = {
        "no_ssl": "Your website isn't using HTTPS, which means browsers show a 'Not Secure' warning to potential customers before they even see your services.",
        "slow_load": f"Your site took {details.get('load_time_sec', '3+')} seconds to load. Most customers leave after 3 seconds — especially on mobile when their AC just died.",
        "no_phone_visible": "I couldn't find a phone number visible on your homepage. For emergency HVAC calls, that's the #1 thing customers are looking for.",
        "no_click_to_call": "Your phone number isn't set up as a tap-to-call link. On mobile (where 60%+ of local searches happen), customers have to memorize the number and switch apps to dial.",
        "no_contact_form": "There's no contact form on the main page. Customers who don't want to call — or are browsing after hours — have no way to reach you.",
        "no_analytics": "Your site doesn't appear to have Google Analytics installed, which means you have no visibility into how many people visit, where they come from, or why they leave.",
        "no_gtm": "Google Tag Manager isn't set up, making it difficult to track conversions from any ads you're running.",
        "no_meta_description": "Your site is missing a meta description — the snippet Google shows under your listing. Without it, Google pulls random text from your page.",
        "no_h1": "Your homepage is missing a proper H1 heading, which hurts your ranking for local HVAC searches.",
        "homepage_as_landing": "Your ads (if running) likely send traffic to your generic homepage instead of a dedicated landing page. This typically cuts conversion rates by 50% or more.",
        "no_schema_markup": "Your site lacks structured data (schema markup), so Google can't display your ratings, hours, or service area in search results the way your competitors' sites do.",
        "no_viewport_meta": "Your website doesn't appear to be mobile-optimized. On phones, text is tiny and buttons are hard to tap — and most emergency HVAC searches happen on mobile.",
        "no_reviews_on_site": "I didn't find any customer reviews or testimonials displayed on your site. Social proof is one of the strongest conversion drivers for local services.",
    }
    return mapping.get(issue, f"Issue detected: {issue}")


def generate_diagnostic_email(audit_result):
    """Generate a personalized diagnostic cold email for a single business."""
    name = audit_result.get("name", "your company")
    city = audit_result.get("city", "your area")
    score = audit_result.get("score", 0)
    issues = audit_result.get("issues", [])
    details = audit_result.get("details", {})
    website = audit_result.get("audited_url", audit_result.get("website", ""))

    # Pick top 3 most impactful issues for the email
    priority_order = [
        "no_phone_visible", "no_click_to_call", "no_ssl", "slow_load",
        "no_viewport_meta", "homepage_as_landing", "no_contact_form",
        "no_analytics", "no_reviews_on_site", "no_schema_markup",
        "no_meta_description", "no_h1", "no_gtm",
    ]
    top_issues = [i for i in priority_order if i in issues][:3]

    # Build the findings section
    findings = []
    for idx, issue in enumerate(top_issues, 1):
        findings.append(f"{idx}. {_issue_to_english(issue, details)}")
    findings_text = "\n\n".join(findings)

    subject = f"I found {len(issues)} fixable issues on {name}'s website"

    body = f"""Hi,

I was researching HVAC companies in {city} and came across {name}'s website ({website}). I do website audits for local service businesses, and I noticed a few things that are likely costing you calls and leads.

Here's what I found:

{findings_text}

These are all straightforward fixes. Most can be handled in a week or two, and the impact on your call volume is usually noticeable within the first month.

I typically work on a flat monthly retainer — no long-term contracts. Most of my clients see measurable results within the first 3 weeks.

Would it make sense to jump on a quick 10-minute call this week so I can walk you through what I found?

Best,
[YOUR NAME]
[YOUR PHONE]"""

    return {
        "subject": subject,
        "body": body,
        "issue_count": len(issues),
        "top_issues": top_issues,
        "score": score,
    }


def generate_batch_emails(audit_results, min_score=30):
    """Generate emails for all businesses above minimum incompetence score."""
    emails = []
    qualified = [r for r in audit_results if r.get("score", 0) >= min_score]
    qualified.sort(key=lambda x: x["score"], reverse=True)

    for result in qualified:
        email = generate_diagnostic_email(result)
        email["business_name"] = result.get("name", "")
        email["business_phone"] = result.get("phone", "")
        email["business_email"] = result.get("email", "")
        email["city"] = result.get("city", "")
        email["website"] = result.get("audited_url", result.get("website", ""))
        emails.append(email)

    return emails
