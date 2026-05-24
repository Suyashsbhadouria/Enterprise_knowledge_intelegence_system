"""Interrelated Nexus Dynamics enterprise fixture — Jira, Confluence, Slack, meetings (no GitHub)."""

from __future__ import annotations

from typing import Any

ATLASSIAN_BASE = "https://nexus-dynamics.atlassian.net"
WIKI_BASE = f"{ATLASSIAN_BASE}/wiki"

ENTERPRISE_MANIFEST: dict[str, Any] = {
    "organization": "Nexus Dynamics Ltd.",
    "industry": "B2B SaaS + professional services",
    "teams": [
        {"name": "Atlas Platform", "focus": "Core platform, auth, API gateway", "project": "CORE"},
        {"name": "Beacon Delivery", "focus": "Acme Corp implementation", "project": "ACME"},
        {"name": "Cedar Healthcare", "focus": "Meridian Health HIPAA program", "project": "MERID"},
        {"name": "Delta Operations", "focus": "SRE, incidents, internal runbooks", "project": "OPS"},
    ],
    "clients": [
        {"name": "Acme Corporation", "project": "ACME", "contract": "FY26 platform rollout"},
        {"name": "Meridian Health Systems", "project": "MERID", "contract": "Patient portal + audit trail"},
        {"name": "GlobalRetail Inc.", "project": "CORE", "contract": "Shared multi-tenant isolation (planned)"},
    ],
    "slack_channels": [
        {"id": "C099ATLAS01", "name": "atlas-platform", "team": "Atlas"},
        {"id": "C099ACME001", "name": "client-acme-delivery", "team": "Beacon"},
        {"id": "C099MERID01", "name": "cedar-meridian-health", "team": "Cedar"},
        {"id": "C099OPS0001", "name": "incident-warroom", "team": "Delta"},
    ],
    "confluence_spaces": ["CORE", "ACME", "MERID", "OPS"],
}


def _jira(
    key: str,
    *,
    project: str,
    project_name: str,
    summary: str,
    status: str,
    assignee: str,
    assignee_email: str,
    description: str,
    comments: list[str] | None = None,
    labels: list[str] | None = None,
) -> dict[str, Any]:
    comments_text = "\n".join(comments or [])
    label_line = f"Labels: {', '.join(labels)}" if labels else ""
    body_parts = [
        f"Issue: {key}",
        f"Project: {project} ({project_name})",
        f"Status: {status}",
        f"Assignee: {assignee}",
        f"Summary: {summary}",
    ]
    if label_line:
        body_parts.append(label_line)
    body_parts.append(f"Description:\n{description}")
    if comments_text:
        body_parts.append(f"Comments:\n{comments_text}")
    return {
        "source": "jira",
        "source_id": key,
        "title": summary,
        "content": "\n".join(body_parts),
        "url": f"{ATLASSIAN_BASE}/browse/{key}",
        "metadata": {
            "project": project,
            "project_name": project_name,
            "status": status,
            "assignee": assignee,
            "assignee_account_id": f"acct-{assignee.lower().replace(' ', '-')}",
            "assignee_email": assignee_email,
            "labels": labels or [],
        },
    }


def build_jira_documents() -> list[dict[str, Any]]:
    """~32 interrelated issues across four programs and three client engagements."""
    return [
        # --- CORE / Atlas Platform ---
        _jira(
            "CORE-101",
            project="CORE",
            project_name="Nexus Platform",
            summary="Implement OIDC SSO for enterprise tenants",
            status="In Progress",
            assignee="Priya Sharma",
            assignee_email="priya.sharma@nexus-dynamics.com",
            description=(
                "Deliver tenant-scoped OIDC login for Acme and Meridian pilots. "
                "Depends on token refresh design in Confluence page 10001. "
                "Blocks ACME-205 and MERID-302."
            ),
            comments=[
                "Alex Kim: JWT rotation spec approved in architecture review.",
                "Priya Sharma: Blocked until CORE-105 secrets store is live.",
            ],
            labels=["security", "platform", "client-acme"],
        ),
        _jira(
            "CORE-102",
            project="CORE",
            project_name="Nexus Platform",
            summary="API gateway rate limiting per tenant",
            status="Done",
            assignee="Alex Kim",
            assignee_email="alex.kim@nexus-dynamics.com",
            description="Shipped Redis-backed token bucket limits. Documented in CORE space runbook.",
            labels=["platform"],
        ),
        _jira(
            "CORE-103",
            project="CORE",
            project_name="Nexus Platform",
            summary="Multi-tenant row-level security in Postgres",
            status="In Review",
            assignee="Jordan Lee",
            assignee_email="jordan.lee@nexus-dynamics.com",
            description="RLS policies for GlobalRetail pilot. See MERID-301 for HIPAA overlap requirements.",
            labels=["security", "client-globalretail"],
        ),
        _jira(
            "CORE-104",
            project="CORE",
            project_name="Nexus Platform",
            summary="Observability: distributed tracing for coordination API",
            status="To Do",
            assignee="Sam Rivera",
            assignee_email="sam.rivera@nexus-dynamics.com",
            description="OpenTelemetry hooks across ekcip-api and connector sync jobs.",
        ),
        _jira(
            "CORE-105",
            project="CORE",
            project_name="Nexus Platform",
            summary="Secrets store integration (Vault) for connector credentials",
            status="Blocked",
            assignee="Priya Sharma",
            assignee_email="priya.sharma@nexus-dynamics.com",
            description=(
                "BLOCKER: Vendor security review pending. Escalated in #incident-warroom. "
                "Blocks CORE-101 SSO rollout."
            ),
            comments=["Delta Ops: Waiting on InfoSec sign-off ETA Friday."],
            labels=["blocker", "security"],
        ),
        _jira(
            "CORE-106",
            project="CORE",
            project_name="Nexus Platform",
            summary="Feature flags service v2",
            status="In Progress",
            assignee="Alex Kim",
            assignee_email="alex.kim@nexus-dynamics.com",
            description="Needed for Acme phased rollout (ACME-210).",
        ),
        # --- ACME / Beacon Delivery ---
        _jira(
            "ACME-201",
            project="ACME",
            project_name="Acme Corp Implementation",
            summary="Acme executive dashboard — MVP wireframes sign-off",
            status="Done",
            assignee="Morgan Blake",
            assignee_email="morgan.blake@nexus-dynamics.com",
            description="Client approved wireframes 12 May. Confluence ACME space page 20010.",
            labels=["client-acme", "ux"],
        ),
        _jira(
            "ACME-202",
            project="ACME",
            project_name="Acme Corp Implementation",
            summary="Integrate Acme Salesforce opportunity feed",
            status="In Progress",
            assignee="Taylor Nguyen",
            assignee_email="taylor.nguyen@nexus-dynamics.com",
            description="Sync hourly via MuleSoft. Discussed in client standup 21 May.",
        ),
        _jira(
            "ACME-203",
            project="ACME",
            project_name="Acme Corp Implementation",
            summary="UAT environment provisioning for Acme",
            status="In Progress",
            assignee="Jordan Lee",
            assignee_email="jordan.lee@nexus-dynamics.com",
            description="Tenant acme-uat.nexus-dynamics.com. OPS-402 tracks runbook.",
        ),
        _jira(
            "ACME-204",
            project="ACME",
            project_name="Acme Corp Implementation",
            summary="Data migration — legacy CRM contacts (450k rows)",
            status="To Do",
            assignee="Taylor Nguyen",
            assignee_email="taylor.nguyen@nexus-dynamics.com",
            description="Depends on CORE-103 RLS policies before production cutover.",
        ),
        _jira(
            "ACME-205",
            project="ACME",
            project_name="Acme Corp Implementation",
            summary="SSO cutover weekend — production launch",
            status="Blocked",
            assignee="Morgan Blake",
            assignee_email="morgan.blake@nexus-dynamics.com",
            description=(
                "Blocked on CORE-101 OIDC. Client sponsor: Diane Okonkwo (Acme). "
                "Target date 15 June discussed in #client-acme-delivery."
            ),
            labels=["blocker", "client-acme", "launch"],
        ),
        _jira(
            "ACME-206",
            project="ACME",
            project_name="Acme Corp Implementation",
            summary="Training materials for Acme support desk",
            status="To Do",
            assignee="Morgan Blake",
            assignee_email="morgan.blake@nexus-dynamics.com",
            description="Link from Confluence page 20015.",
        ),
        _jira(
            "ACME-210",
            project="ACME",
            project_name="Acme Corp Implementation",
            summary="Phased feature rollout — billing module",
            status="In Progress",
            assignee="Taylor Nguyen",
            assignee_email="taylor.nguyen@nexus-dynamics.com",
            description="Uses CORE-106 feature flags. Slack thread in C099ACME001.",
        ),
        # --- MERID / Cedar Healthcare ---
        _jira(
            "MERID-301",
            project="MERID",
            project_name="Meridian Health Program",
            summary="HIPAA audit trail — immutable event log",
            status="In Progress",
            assignee="Riley Chen",
            assignee_email="riley.chen@nexus-dynamics.com",
            description=(
                "Must align with CORE-103 RLS. Meridian compliance officer: Dr. Patel. "
                "Confluence MERID space page 30001."
            ),
            labels=["hipaa", "client-meridian"],
        ),
        _jira(
            "MERID-302",
            project="MERID",
            project_name="Meridian Health Program",
            summary="Patient portal SSO with Meridian IdP",
            status="Blocked",
            assignee="Riley Chen",
            assignee_email="riley.chen@nexus-dynamics.com",
            description="Blocked on CORE-101. Meridian requires BAA addendum review.",
            labels=["blocker", "client-meridian"],
        ),
        _jira(
            "MERID-303",
            project="MERID",
            project_name="Meridian Health Program",
            summary="PHI field encryption at rest",
            status="In Review",
            assignee="Priya Sharma",
            assignee_email="priya.sharma@nexus-dynamics.com",
            description="KMS keys per tenant. Security review scheduled with Delta Ops.",
        ),
        _jira(
            "MERID-304",
            project="MERID",
            project_name="Meridian Health Program",
            summary="Clinical staff onboarding workflow",
            status="To Do",
            assignee="Riley Chen",
            assignee_email="riley.chen@nexus-dynamics.com",
            description="Workflow diagrams on Confluence page 30005.",
        ),
        _jira(
            "MERID-305",
            project="MERID",
            project_name="Meridian Health Program",
            summary="Penetration test remediation — medium findings",
            status="In Progress",
            assignee="Jordan Lee",
            assignee_email="jordan.lee@nexus-dynamics.com",
            description="3 medium, 0 critical. Report shared in #cedar-meridian-health.",
        ),
        # --- OPS / Delta ---
        _jira(
            "OPS-401",
            project="OPS",
            project_name="Operations & Reliability",
            summary="Incident runbook — connector sync failures",
            status="Done",
            assignee="Sam Rivera",
            assignee_email="sam.rivera@nexus-dynamics.com",
            description="Published to Confluence OPS space page 40001.",
        ),
        _jira(
            "OPS-402",
            project="OPS",
            project_name="Operations & Reliability",
            summary="UAT playbook — tenant provisioning checklist",
            status="In Progress",
            assignee="Sam Rivera",
            assignee_email="sam.rivera@nexus-dynamics.com",
            description="Supports ACME-203 and MERID UAT. Referenced in standup 21 May.",
        ),
        _jira(
            "OPS-403",
            project="OPS",
            project_name="Operations & Reliability",
            summary="On-call rotation Q3 — Nexus platform",
            status="To Do",
            assignee="Sam Rivera",
            assignee_email="sam.rivera@nexus-dynamics.com",
            description="Primary: Sam Rivera. Secondary: Alex Kim.",
        ),
        _jira(
            "OPS-404",
            project="OPS",
            project_name="Operations & Reliability",
            summary="SEV-2: Elevated API latency — us-east-1",
            status="Blocked",
            assignee="Sam Rivera",
            assignee_email="sam.rivera@nexus-dynamics.com",
            description=(
                "BLOCKER: Root cause suspected Redis connection pool saturation. "
                "War room active in C099OPS0001. Related CORE-102 rate limit deploy."
            ),
            labels=["blocker", "incident"],
        ),
        _jira(
            "OPS-405",
            project="OPS",
            project_name="Operations & Reliability",
            summary="Post-incident review template",
            status="To Do",
            assignee="Jordan Lee",
            assignee_email="jordan.lee@nexus-dynamics.com",
            description="Template in Confluence OPS page 40005.",
        ),
        # Epics / stories (additional volume)
        _jira(
            "CORE-110",
            project="CORE",
            project_name="Nexus Platform",
            summary="Epic: Enterprise knowledge graph for coordination intelligence",
            status="In Progress",
            assignee="Alex Kim",
            assignee_email="alex.kim@nexus-dynamics.com",
            description="Parent for GraphRAG work. Child: CORE-111, CORE-112.",
            labels=["epic"],
        ),
        _jira(
            "CORE-111",
            project="CORE",
            project_name="Nexus Platform",
            summary="Neo4j schema for projects, issues, and assignees",
            status="Done",
            assignee="Alex Kim",
            assignee_email="alex.kim@nexus-dynamics.com",
            description="Seeded via admin enterprise fixture.",
        ),
        _jira(
            "ACME-220",
            project="ACME",
            project_name="Acme Corp Implementation",
            summary="Client success: weekly status deck automation",
            status="To Do",
            assignee="Morgan Blake",
            assignee_email="morgan.blake@nexus-dynamics.com",
            description="Pull Jira + Confluence summaries for Diane Okonkwo.",
        ),
        _jira(
            "MERID-310",
            project="MERID",
            project_name="Meridian Health Program",
            summary="Integration test suite — PHI synthetic data",
            status="In Progress",
            assignee="Riley Chen",
            assignee_email="riley.chen@nexus-dynamics.com",
            description="No real PHI in fixtures. Uses enterprise_catalog seed only.",
        ),
    ]


def _confluence(
    page_id: str,
    *,
    space_key: str,
    space_name: str,
    title: str,
    body: str,
    updated_by: str = "Alex Kim",
) -> dict[str, Any]:
    return {
        "source": "confluence",
        "source_id": page_id,
        "title": title,
        "content": "\n".join(
            [
                f"Page: {title}",
                f"Page ID: {page_id}",
                f"Space: {space_key} ({space_name})",
                f"Last updated: {updated_by} @ 2026-05-20",
                f"Content:\n{body}",
            ]
        ),
        "url": f"{WIKI_BASE}/spaces/{space_key}/pages/{page_id}/{title.replace(' ', '+')}",
        "metadata": {
            "space_key": space_key,
            "space_name": space_name,
            "updated_by": updated_by,
        },
    }


def build_confluence_documents() -> list[dict[str, Any]]:
    return [
        _confluence(
            "10001",
            space_key="CORE",
            space_name="Platform Engineering",
            title="OIDC SSO Architecture — tenant-scoped tokens",
            body=(
                "Defines authorization code flow for Acme and Meridian. "
                "Implementation tracked in CORE-101. Token refresh every 15 minutes. "
                "Secrets from Vault (CORE-105)."
            ),
        ),
        _confluence(
            "10002",
            space_key="CORE",
            space_name="Platform Engineering",
            title="API gateway rate limiting design",
            body="Documents CORE-102 rollout. Per-tenant buckets in Redis.",
        ),
        _confluence(
            "10003",
            space_key="CORE",
            space_name="Platform Engineering",
            title="Multi-tenant RLS policy reference",
            body="Postgres RLS for GlobalRetail and Meridian. Jira: CORE-103, MERID-301.",
        ),
        _confluence(
            "20010",
            space_key="ACME",
            space_name="Acme Delivery",
            title="Acme Executive Dashboard — approved wireframes",
            body="Signed off by Diane Okonkwo (Acme VP Ops). Jira ACME-201. Launch tied to ACME-205.",
        ),
        _confluence(
            "20012",
            space_key="ACME",
            space_name="Acme Delivery",
            title="Acme SSO cutover runbook",
            body=(
                "Weekend window 14–15 June. Prerequisites: CORE-101 complete, ACME-203 UAT sign-off. "
                "Rollback plan section 4. Slack: #client-acme-delivery."
            ),
        ),
        _confluence(
            "20015",
            space_key="ACME",
            space_name="ACme Delivery",
            title="Acme support desk training curriculum",
            body="Linked from ACME-206. Modules: login, billing (ACME-210), escalation.",
        ),
        _confluence(
            "30001",
            space_key="MERID",
            space_name="Meridian Health",
            title="HIPAA audit trail specification",
            body="Immutable events for PHI access. Jira MERID-301. Review with Dr. Patel.",
        ),
        _confluence(
            "30005",
            space_key="MERID",
            space_name="Meridian Health",
            title="Clinical staff onboarding — process maps",
            body="Supports MERID-304. SSO blocked until CORE-101 (MERID-302).",
        ),
        _confluence(
            "30008",
            space_key="MERID",
            space_name="Meridian Health",
            title="BAA addendum — legal checklist",
            body="Meridian legal reviewing. Blocks MERID-302 patient portal SSO.",
        ),
        _confluence(
            "40001",
            space_key="OPS",
            space_name="Operations",
            title="Runbook: Knowledge connector sync failures",
            body="OPS-401. Steps: check embedding provider, Jira token expiry, Slack scopes.",
        ),
        _confluence(
            "40005",
            space_key="OPS",
            space_name="Operations",
            title="Post-incident review (PIR) template",
            body="Used after OPS-404 latency incident. War room channel C099OPS0001.",
        ),
        _confluence(
            "40010",
            space_key="OPS",
            space_name="Operations",
            title="UAT tenant provisioning checklist",
            body="OPS-402. Covers Acme (ACME-203) and Meridian UAT tenants.",
        ),
    ]


def _slack_msg(
    channel_id: str,
    channel_name: str,
    *,
    ts: str,
    user: str,
    text: str,
    thread_ts: str | None = None,
) -> tuple[str, str, dict[str, Any]]:
    return (
        channel_id,
        channel_name,
        {"ts": ts, "user": user, "text": text, "thread_ts": thread_ts},
    )


def build_slack_message_batches() -> list[tuple[str, str, dict[str, Any]]]:
    """~40 messages across four channels, referencing Jira keys and Confluence pages."""
    return [
        # atlas-platform
        _slack_msg(
            "C099ATLAS01",
            "atlas-platform",
            ts="1716288000.100001",
            user="U_ATLAS_PRIYA",
            text="CORE-101 OIDC PR ready for review — still blocked on CORE-105 Vault sign-off.",
        ),
        _slack_msg(
            "C099ATLAS01",
            "atlas-platform",
            ts="1716288060.100002",
            user="U_ATLAS_ALEX",
            text="Merged CORE-102 rate limits. Watching OPS-404 latency — might be related.",
        ),
        _slack_msg(
            "C099ATLAS01",
            "atlas-platform",
            ts="1716288120.100003",
            user="U_ATLAS_JORDAN",
            text="CORE-103 RLS policies in review. Meridian (MERID-301) wants stricter PHI boundaries.",
        ),
        _slack_msg(
            "C099ATLAS01",
            "atlas-platform",
            ts="1716288180.100004",
            user="U_ATLAS_PRIYA",
            text="Can someone link the OIDC doc? Confluence 10001 should be canonical.",
            thread_ts="1716288000.100001",
        ),
        _slack_msg(
            "C099ATLAS01",
            "atlas-platform",
            ts="1716288240.100005",
            user="U_ATLAS_ALEX",
            text="https://nexus-dynamics.atlassian.net/wiki/spaces/CORE/pages/10001 — updated yesterday.",
            thread_ts="1716288000.100001",
        ),
        _slack_msg(
            "C099ATLAS01",
            "atlas-platform",
            ts="1716374400.100010",
            user="U_ATLAS_SAM",
            text="CORE-104 tracing spike started. Need sample traces from production sync jobs.",
        ),
        _slack_msg(
            "C099ATLAS01",
            "atlas-platform",
            ts="1716460800.100011",
            user="U_ATLAS_ALEX",
            text="CORE-110 epic: graph coordination is demo-ready after enterprise seed.",
        ),
        # client-acme-delivery
        _slack_msg(
            "C099ACME001",
            "client-acme-delivery",
            ts="1716288300.200001",
            user="U_BEACON_MORGAN",
            text="Acme sponsor Diane asked for SSO date — ACME-205 still blocked on CORE-101.",
        ),
        _slack_msg(
            "C099ACME001",
            "client-acme-delivery",
            ts="1716288360.200002",
            user="U_BEACON_TAYLOR",
            text="ACME-210 billing rollout at 40% flags. CORE-106 working well.",
        ),
        _slack_msg(
            "C099ACME001",
            "client-acme-delivery",
            ts="1716288420.200003",
            user="U_BEACON_MORGAN",
            text="UAT tenant acme-uat ready per ACME-203. OPS-402 checklist almost done.",
        ),
        _slack_msg(
            "C099ACME001",
            "client-acme-delivery",
            ts="1716288480.200004",
            user="U_BEACON_JORDAN",
            text="Don't migrate CRM until CORE-103 lands — ACME-204 dependency.",
        ),
        _slack_msg(
            "C099ACME001",
            "client-acme-delivery",
            ts="1716288540.200005",
            user="U_BEACON_MORGAN",
            text="Wireframes signed — see Confluence 20010. ACME-201 closed.",
        ),
        _slack_msg(
            "C099ACME001",
            "client-acme-delivery",
            ts="1716374700.200010",
            user="U_BEACON_TAYLOR",
            text="Salesforce feed ACME-202: first successful hourly sync at 6am.",
        ),
        _slack_msg(
            "C099ACME001",
            "client-acme-delivery",
            ts="1716461100.200011",
            user="U_BEACON_MORGAN",
            text="Proposed SSO cutover 14 June — need executive approval from Diane.",
        ),
        _slack_msg(
            "C099ACME001",
            "client-acme-delivery",
            ts="1716461160.200012",
            user="U_BEACON_TAYLOR",
            text="I'll draft the Slack update for Acme channel once CORE-105 clears.",
        ),
        # cedar-meridian-health
        _slack_msg(
            "C099MERID01",
            "cedar-meridian-health",
            ts="1716288600.300001",
            user="U_CEDAR_RILEY",
            text="MERID-301 audit log MVP in staging. Dr. Patel review Thursday.",
        ),
        _slack_msg(
            "C099MERID01",
            "cedar-meridian-health",
            ts="1716288660.300002",
            user="U_CEDAR_PRIYA",
            text="MERID-303 encryption keys rotated. Security review passed.",
        ),
        _slack_msg(
            "C099MERID01",
            "cedar-meridian-health",
            ts="1716288720.300003",
            user="U_CEDAR_RILEY",
            text="MERID-302 SSO blocked — BAA addendum on Confluence 30008 still with legal.",
        ),
        _slack_msg(
            "C099MERID01",
            "cedar-meridian-health",
            ts="1716288780.300004",
            user="U_CEDAR_JORDAN",
            text="Pen test mediums in MERID-305 — no criticals. Fixing CSP headers first.",
        ),
        _slack_msg(
            "C099MERID01",
            "cedar-meridian-health",
            ts="1716375000.300010",
            user="U_CEDAR_RILEY",
            text="Synthetic PHI tests only for MERID-310 — do not use production exports.",
        ),
        _slack_msg(
            "C099MERID01",
            "cedar-meridian-health",
            ts="1716461400.300011",
            user="U_CEDAR_RILEY",
            text="Patient portal timeline slips 2 weeks if CORE-101 slips again.",
        ),
        # incident-warroom
        _slack_msg(
            "C099OPS0001",
            "incident-warroom",
            ts="1716462000.400001",
            user="U_OPS_SAM",
            text="SEV-2 OPS-404: p99 latency 2.4s us-east-1. Suspect Redis pool after CORE-102 deploy.",
        ),
        _slack_msg(
            "C099OPS0001",
            "incident-warroom",
            ts="1716462060.400002",
            user="U_OPS_ALEX",
            text="Scaling Redis replicas. Tracking in OPS-404.",
        ),
        _slack_msg(
            "C099OPS0001",
            "incident-warroom",
            ts="1716462120.400003",
            user="U_OPS_SAM",
            text="CORE-105 Vault delay unrelated but compounding deploy freeze.",
        ),
        _slack_msg(
            "C099OPS0001",
            "incident-warroom",
            ts="1716462180.400004",
            user="U_OPS_JORDAN",
            text="Acme launch ACME-205 at risk if incident runs past Friday.",
        ),
        _slack_msg(
            "C099OPS0001",
            "incident-warroom",
            ts="1716462240.400005",
            user="U_OPS_SAM",
            text="Runbook OPS-401 followed. Escalated to Atlas team in C099ATLAS01.",
        ),
        _slack_msg(
            "C099OPS0001",
            "incident-warroom",
            ts="1716462300.400006",
            user="U_OPS_SAM",
            text="PIR scheduled — template Confluence 40005 after mitigation.",
        ),
        _slack_msg(
            "C099OPS0001",
            "incident-warroom",
            ts="1716462360.400007",
            user="U_OPS_ALEX",
            text="Latency improving — p99 down to 900ms. Monitoring OPS-404.",
        ),
        _slack_msg(
            "C099ATLAS01",
            "atlas-platform",
            ts="1716462400.100020",
            user="U_ATLAS_ALEX",
            text="Cross-post: war room says Redis — verifying rate limiter config from CORE-102.",
        ),
        _slack_msg(
            "C099ACME001",
            "client-acme-delivery",
            ts="1716462500.200020",
            user="U_BEACON_MORGAN",
            text="Heads up Acme: possible SSO delay if platform incident continues (ACME-205).",
        ),
    ]


MEETING_STANDUP_MAY_21 = """\
Nexus Dynamics — Cross-team standup (21 May 2026)

Attendees: Priya Sharma (Atlas), Morgan Blake (Beacon/Acme), Riley Chen (Cedar/Meridian), Sam Rivera (Delta Ops)

Priya: CORE-101 OIDC is code-complete but blocked on CORE-105 Vault approval. This blocks ACME-205 and MERID-302.

Morgan: Acme executive dashboard signed off (ACME-201, Confluence 20010). Diane Okonkwo wants SSO date confirmation — still waiting on platform.

Riley: MERID-301 audit trail in staging for Dr. Patel. BAA addendum (page 30008) is the gating item for patient portal SSO.

Sam: Active SEV-2 OPS-404 latency incident. War room C099OPS0001. May impact Acme cutover weekend.

Action items:
- Priya to chase InfoSec on CORE-105 by Friday.
- Morgan to send Acme revised timeline if OPS-404 not resolved by Thursday.
- Riley to schedule compliance review for MERID-303 encryption.
"""

MEETING_ACME_STEERCO = """\
Acme Corporation — Steering committee (20 May 2026)

Client: Diane Okonkwo (VP Operations), Nexus: Morgan Blake, Taylor Nguyen

Discussion:
- ACME-205 SSO cutover targeted 14–15 June pending CORE-101.
- ACME-210 billing module phased rollout approved for pilot users.
- ACME-204 data migration deferred until CORE-103 RLS complete.
- Training (ACME-206) to start week of 2 June using Confluence 20015.

Decision: Proceed with UAT on acme-uat tenant (ACME-203) this week.
"""

MEETING_MERID_COMPLIANCE = """\
Meridian Health — Compliance sync (19 May 2026)

Attendees: Dr. Anika Patel (Meridian CISO), Riley Chen, Priya Sharma

MERID-301 immutable audit trail design approved with minor notes.
MERID-302 patient portal SSO cannot proceed until BAA addendum signed.
MERID-305 pen test: three medium findings, remediation in progress.

Meridian requires all test data synthetic — reference MERID-310.
"""


def build_meeting_transcript_files() -> list[tuple[str, str]]:
    return [
        ("standup_21_may_2026.txt", MEETING_STANDUP_MAY_21),
        ("acme_steerco_20_may_2026.txt", MEETING_ACME_STEERCO),
        ("meridian_compliance_19_may_2026.txt", MEETING_MERID_COMPLIANCE),
    ]


def build_test_queries() -> dict[str, list[str]]:
    """Categorized queries for manual and API testing after enterprise seed."""
    return {
        "knowledge_qa": [
            "What blockers exist in project CORE?",
            "Who is assigned to ACME-205 and why is it blocked?",
            "Summarize all issues in project MERID with assignees.",
            "What did we decide in the 21 May cross-team standup about SSO?",
            "How does Confluence page 10001 relate to CORE-101?",
            "What is the status of MERID-301 and who is the Meridian compliance contact?",
            "Compare ACME-205 and MERID-302 — what platform dependency do they share?",
            "Summarize recent discussion in #client-acme-delivery about the SSO cutover.",
            "What is OPS-404 and how does it affect the Acme launch?",
            "What does the Meridian compliance meeting say about synthetic PHI testing?",
        ],
        "graph_rag": [
            "Who is assigned to CORE-105?",
            "List all blocked issues in project OPS.",
            "Summarize issues in project ACME.",
            "What blockers exist in project MERID?",
        ],
        "multi_source": [
            "Across Jira, Slack, and Confluence: what is blocking the Acme SSO launch?",
            "Give me a status brief for client Acme Corporation.",
            "What is Nexus doing for Meridian Health HIPAA requirements?",
        ],
        "action_proposals": [
            'Send a Slack message to C099ACME001 saying "Acme SSO cutover may slip to 21 June pending CORE-105 Vault approval."',
            "Add a comment on ACME-205 saying Platform incident OPS-404 may impact cutover weekend.",
            "Update status of OPS-404 to In Progress",
            "Schedule a Slack message to C099OPS0001 in 2 hours saying \"Redis pool scaling complete — monitoring p99.\"",
            "Remind me in 30 minutes to follow up with InfoSec on CORE-105",
        ],
        "api_smoke": [
            "GET /v1/knowledge/status",
            "GET /v1/graph/status",
            "GET /v1/llm/status",
            "POST /v1/admin/seed-enterprise",
            "POST /v1/conversations then POST .../messages with a knowledge_qa query above",
            "GET /v1/actions/conversations/{id}/actions after an action_proposals message",
            "POST /v1/actions/{action_id}/approve with {\"execute\": false}",
        ],
        "env_setup_for_actions": [
            "Set SLACK_CHANNEL_IDS=C099ATLAS01,C099ACME001,C099MERID01,C099OPS0001 in .env (fixture channel IDs).",
            "Jira actions require live JIRA_* credentials — proposals still appear without execute.",
            "Use APP_ENV=development and POST /v1/admin/seed-enterprise (no live Jira/Slack required for knowledge).",
        ],
    }
