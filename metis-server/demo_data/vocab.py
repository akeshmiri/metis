"""
Domain vocabulary for demo data generation -- realistic e-commerce/SaaS
platform terms, combined deterministically (seeded RNG) to produce varied
but plausible entity names and EARS-conformant requirement text. All
output from this module is synthetic by design and clearly labeled as
demo data by the generator that consumes it -- it is not a claim about any
real system.
"""
import random

SERVICES = [
    "billing", "orders", "inventory", "auth", "notifications", "search",
    "payments", "shipping", "catalog", "reviews", "recommendations",
    "analytics", "support", "loyalty", "fraud-detection", "pricing",
    "checkout", "cart", "wishlist", "returns", "subscriptions", "invoicing",
    "reporting", "audit-log", "user-profile", "session", "media-upload",
    "tax-calculation", "geo-location", "email-delivery",
]

NOUNS = [
    "invoice", "order", "refund", "shipment", "customer", "product",
    "cart", "subscription", "payment method", "discount code", "review",
    "return request", "session token", "notification", "report",
    "webhook", "audit record", "credit balance", "loyalty point",
    "tax rate", "address", "cache entry", "search index", "user account",
]

ACTIONS = [
    "reject", "approve", "cancel", "reconcile", "archive", "notify",
    "validate", "recalculate", "suspend", "flag", "escalate", "expire",
    "synchronize", "retry", "throttle", "audit", "anonymize", "merge",
    "deduplicate", "reindex",
]

CONDITIONS = [
    "the amount exceeds the configured threshold",
    "the customer's account is suspended",
    "the request originates from an untrusted region",
    "the retry count exceeds 3",
    "the payment gateway returns a timeout",
    "the inventory count drops below the safety stock level",
    "the discount code has already been redeemed",
    "the session has been idle for more than 30 minutes",
    "the webhook signature fails verification",
    "the currency code is not in the supported list",
]

TRIGGERS = [
    "a payment webhook is received",
    "an order is placed",
    "a refund is requested",
    "a customer updates their address",
    "a scheduled job runs",
    "an inventory count changes",
    "a support ticket is escalated",
    "a subscription renews",
    "a new device logs in",
    "a discount code is applied",
]

STATES = [
    "an order is in Shipped state",
    "a subscription is in Trial state",
    "an account is in Suspended state",
    "a session is in Idle state",
    "a refund is in Pending state",
    "an invoice is in Overdue state",
]

FEATURES_ADJ = [
    "multi-currency support", "two-factor authentication", "dark mode",
    "bulk export", "webhook retries", "regional tax rules",
    "loyalty tier upgrades", "saved payment methods", "guest checkout",
]

DEFECT_SUMMARIES = [
    "returns HTTP 500 instead of 400 on missing required field",
    "double-charges the customer on network retry",
    "does not release the inventory lock on cancellation",
    "shows stale cache data for up to 10 minutes after an update",
    "silently drops webhook events under high load",
    "fails to send confirmation email for guest checkouts",
    "allows a negative quantity to be added to the cart",
    "does not respect the configured rate limit",
]

INCIDENT_TITLES = [
    "Checkout latency spike during flash sale",
    "Payment gateway timeout cascade",
    "Search index fell behind by 2 hours",
    "Elevated 5xx rate on the orders API",
    "Notification queue backlog",
    "Database connection pool exhaustion",
]


GOAL_OUTCOME_TEMPLATES = [
    "Reduce {noun} processing time by {pct}%",
    "Increase {service} conversion rate by {pct}%",
    "Cut {service} P1 incident rate in half",
    "Improve {service} reliability to {uptime}% uptime",
    "Reduce {noun} abandonment by {pct}%",
    "Expand {service} support to {n} new regions",
    "Decrease {service} support ticket volume by {pct}%",
    "Increase {noun} accuracy to {uptime}%",
    "Reduce {service} operating cost by {pct}%",
    "Improve {service} page load time by {pct}%",
    "Grow {service} adoption by {pct}%",
    "Reduce {noun} fraud losses by {pct}%",
    "Cut {service} onboarding time by {pct}%",
    "Increase {service} test coverage to {uptime}%",
    "Reduce {noun} reconciliation errors by {pct}%",
]

# Real-sounding Confluence content-page types -- used to generate
# Episode-shaped "Confluence data" tied to each Goal/Feature, same real
# episode_type='DocumentIngested' shape atlassian_connector.py's real
# Confluence-page landing path uses.
CONFLUENCE_DOC_TYPES = [
    "PRD", "Design Doc", "RFC", "Runbook", "Architecture Decision Record",
    "Onboarding Guide", "Post-Incident Review", "Meeting Notes",
]

JIRA_ISSUE_TYPES_FOR_REQUIREMENT = ["Story", "Story", "Story", "Epic"]  # Story dominant, matches real backlog shape
JIRA_STATUSES = ["To Do", "In Progress", "In Review", "Done", "Done", "Done"]


def rng(seed: int) -> random.Random:
    return random.Random(seed)


def pick(r: random.Random, options: list) -> str:
    return r.choice(options)


def goal_name(r: random.Random, service: str) -> str:
    template = pick(r, GOAL_OUTCOME_TEMPLATES)
    return template.format(
        noun=pick(r, NOUNS), service=service, pct=r.choice([10, 15, 20, 25, 30, 40, 50]),
        uptime=r.choice([99, 99.5, 99.9, 99.95]), n=r.choice([2, 3, 4, 5]),
    )
