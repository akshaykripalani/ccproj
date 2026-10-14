"""Build submission-only artifacts. Does not import an AWS SDK or call AWS.

Requirements: reportlab, Pillow, pdfplumber, pypdfium2.
Run with a document-authoring Python environment, independently of the app venv.
"""

from __future__ import annotations

import hashlib
import html
import json
import math
import re
import shutil
from pathlib import Path

from PIL import Image as PILImage
from reportlab.graphics import renderPDF, renderSVG
from reportlab.graphics.shapes import Drawing, Line, Polygon, PolyLine, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    LongTable,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
DIAGRAMS = ROOT / "diagrams"
QA = ROOT / ".qa"
BLUE = colors.HexColor("#1e4e79")
INK = colors.HexColor("#183047")
MUTED = colors.HexColor("#526779")
PALE = colors.HexColor("#edf4fa")
PALETTE = {
    "compute": ("#eaf2fc", "#3675ad"),
    "data": ("#eaf6f3", "#2b8072"),
    "auth": ("#f2edfa", "#8056a6"),
    "external": ("#f0f3f6", "#637587"),
    "warning": ("#fff5e6", "#b77b22"),
}


class Figure:
    def __init__(self, slug, title, caption, height=460):
        self.slug, self.title, self.caption = slug, title, caption
        self.width, self.height = 650, height
        self.d = Drawing(self.width, self.height)
        self.d.add(Rect(0, 0, self.width, self.height, fillColor=colors.white, strokeColor=None))
        self.nodes, self.edges = {}, []
        self.mermaid = None

    def text(self, x, y, text, size=12, bold=False, anchor="middle", color=INK):
        self.d.add(
            String(
                x,
                self.height - y,
                text,
                fontName="Helvetica-Bold" if bold else "Helvetica",
                fontSize=size,
                textAnchor=anchor,
                fillColor=color,
            )
        )

    def box(self, ident, x, y, w, h, lines, kind="compute"):
        fill, stroke = PALETTE[kind]
        self.d.add(
            Rect(
                x,
                self.height - y - h,
                w,
                h,
                rx=7,
                ry=7,
                fillColor=colors.HexColor(fill),
                strokeColor=colors.HexColor(stroke),
                strokeWidth=1.1,
            )
        )
        self.nodes[ident] = (x, y, w, h, lines)
        top = y + h / 2 - (len(lines) - 1) * 8 + 4
        for i, line in enumerate(lines):
            self.text(x + w / 2, top + i * 16, line, 12 if i else 12.4, bold=(i == 0))

    def region(self, x, y, w, h, label):
        self.d.add(
            Rect(
                x,
                self.height - y - h,
                w,
                h,
                rx=9,
                ry=9,
                fillColor=None,
                strokeColor=colors.HexColor("#a8b8c6"),
                strokeWidth=1,
                strokeDashArray=[5, 3],
            )
        )
        self.text(x + 12, y + 18, label, 11.5, True, "start", MUTED)

    def port(self, ident, side):
        x, y, w, h, _ = self.nodes[ident]
        return {
            "l": (x, y + h / 2),
            "r": (x + w, y + h / 2),
            "t": (x + w / 2, y),
            "b": (x + w / 2, y + h),
        }[side]

    def arrow(self, a, b, label="", sides=("r", "l"), via=(), label_at=None):
        start, end = self.port(a, sides[0]), self.port(b, sides[1])
        pts = [start, *via, end]
        self.path(pts)
        if label:
            x, y = label_at or ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2 - 9)
            self.label(x, y, label)
        self.edges.append((a, b, label))

    def path(self, pts, dashed=False):
        points = [v for x, y in pts for v in (x, self.height - y)]
        self.d.add(
            PolyLine(
                points,
                strokeColor=MUTED,
                strokeWidth=1.25,
                strokeDashArray=[4, 3] if dashed else None,
            )
        )
        (x0, y0), (x, y) = pts[-2:]
        angle = math.atan2(y - y0, x - x0)
        ends = [(x, y)] + [
            (x - 8 * math.cos(angle + s * 0.45), y - 8 * math.sin(angle + s * 0.45))
            for s in (-1, 1)
        ]
        self.d.add(
            Polygon(
                [v for px, py in ends for v in (px, self.height - py)],
                fillColor=MUTED,
                strokeColor=None,
            )
        )

    def label(self, x, y, value):
        w = stringWidth(value, "Helvetica", 10.7) + 8
        self.d.add(
            Rect(x - w / 2, self.height - y - 4, w, 16, fillColor=colors.white, strokeColor=None)
        )
        self.text(x, y, value, 10.7, color=MUTED)

    def note(self, y, text):
        self.text(14, y, text, 11.4, anchor="start", color=MUTED)

    def sequence(self, lanes, steps):
        positions = []
        spacing = 628 / len(lanes)
        for i, (ident, title) in enumerate(lanes):
            x = 11 + i * spacing
            self.box(ident, x, 12, spacing - 12, 49, title)
            mid = x + (spacing - 12) / 2
            positions.append(mid)
            self.d.add(
                Line(
                    mid,
                    self.height - 65,
                    mid,
                    53,
                    strokeColor=colors.HexColor("#bdc9d3"),
                    strokeDashArray=[3, 3],
                )
            )
        mermaid = ["sequenceDiagram"] + [f"    participant {i} as {' '.join(t)}" for i, t in lanes]
        for j, (a, b, text) in enumerate(steps):
            y = 99 + j * 43
            self.path([(positions[a], y), (positions[b], y)])
            self.label((positions[a] + positions[b]) / 2, y - 9, f"{j + 1}. {text}")
            mermaid.append(f"    {lanes[a][0]}->>{lanes[b][0]}: {text}")
        self.mermaid = "\n".join(mermaid) + "\n"

    def save(self):
        renderSVG.drawToFile(self.d, str(DIAGRAMS / f"{self.slug}.svg"))
        temp = QA / f"{self.slug}.pdf"
        renderPDF.drawToFile(self.d, str(temp))
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(str(temp))
        page = pdf[0]
        bitmap = page.render(scale=2)
        bitmap.to_pil().save(DIAGRAMS / f"{self.slug}.png")
        bitmap.close()
        page.close()
        pdf.close()
        if self.mermaid is None:
            lines = ["flowchart TB"]
            for ident, (_, _, _, _, labels) in self.nodes.items():
                value = "<br/>".join(labels).replace('"', "'")
                lines.append(f'    {ident}["{value}"]')
            for a, b, label in self.edges:
                lines.append(f'    {a} -->|"{label}"| {b}' if label else f"    {a} --> {b}")
            self.mermaid = "\n".join(lines) + "\n"
        (DIAGRAMS / f"{self.slug}.mmd").write_text(self.mermaid, encoding="utf-8")


def figures():
    result = []
    f = Figure(
        "01-system-context",
        "Figure 1. System context",
        "People authenticate through Cognito; the gateway uses IAM. Equipment notification subscription is separate from a login account.",
        420,
    )
    f.box("people", 15, 25, 150, 65, ["Viewer / operator", "Web browser"], "external")
    f.box("gateway", 15, 180, 150, 70, ["Factory gateway", "Three simulated", "motors on EC2"])
    f.box(
        "app",
        240,
        105,
        170,
        105,
        [
            "Monitoring platform",
            "Current state + charts",
            "Controls + alerts",
            "Historical reports",
        ],
    )
    f.box("cognito", 480, 25, 150, 65, ["Amazon Cognito", "Human identity"], "auth")
    f.box(
        "email",
        480,
        185,
        150,
        65,
        ["Confirmed mailbox", "Equipment /", "operational alerts"],
        "external",
    )
    f.box("maintainer", 240, 300, 170, 60, ["Maintainer", "Logged CLI + IaC"], "external")
    f.arrow("people", "app", "HTTPS + access JWT", via=[(200, 57), (200, 157)])
    f.arrow("gateway", "app", "Signed telemetry", via=[(200, 215), (200, 187)], label_at=(195, 243))
    f.arrow("people", "cognito", "Hosted login", via=[(210, 57), (440, 57)], label_at=(322, 44))
    f.arrow("app", "email", "SNS email", via=[(445, 157), (445, 220)])
    f.arrow("maintainer", "app", "Deploy / observe", ("t", "b"), label_at=(325, 266))
    f.note(
        400,
        "Regional deployment: Sydney. CloudFront delivers the static browser application at the edge.",
    )
    result.append(f)

    f = Figure(
        "02-aws-components",
        "Figure 2. Implemented AWS components",
        "Logical data flow, not VPC placement. ApiBackend owns controls and reporting. A durable outbox and scheduled Notifier separate email from telemetry commit.",
        585,
    )
    f.box("ec2", 8, 20, 120, 58, ["EC2 gateway", "IAM / SigV4"])
    f.box("api", 177, 20, 125, 58, ["API Gateway", "IAM or JWT"])
    f.box("ing", 350, 20, 122, 58, ["Ingestion", "Lambda"])
    f.box("q", 519, 20, 122, 58, ["SQS FIFO", "factory group"], "data")
    f.box("processor", 519, 135, 122, 58, ["Processor", "Lambda"])
    f.box("dlq", 350, 135, 122, 58, ["FIFO DLQ", "After 3 receives"], "warning")
    f.box(
        "data", 519, 252, 122, 70, ["DynamoDB Data", "State / history", "Alerts / outbox"], "data"
    )
    f.box("archive", 350, 252, 122, 70, ["S3 archive", "JSON.gz / date", "Glue schema"], "data")
    f.box("app", 177, 135, 125, 58, ["ApiBackend", "Lambda"])
    f.box("ctrl", 8, 135, 120, 58, ["DynamoDB", "Controls"], "data")
    f.box("browser", 8, 252, 120, 70, ["React browser", "Cognito login", "JWT APIs"], "auth")
    f.box("hosting", 8, 390, 120, 70, ["CloudFront", "OAC -> private", "S3 frontend"])
    f.box("athena", 177, 252, 125, 70, ["Athena", "Bounded SQL", "Private results"], "data")
    f.box("sched", 177, 390, 125, 70, ["Scheduler", "Every minute"])
    f.box("notify", 350, 390, 122, 70, ["Notifier Lambda", "Pending work", "GSI query"])
    f.box("sns", 519, 390, 122, 70, ["SNS + KMS", "Confirmed", "email"], "auth")
    f.arrow("ec2", "api")
    f.arrow("api", "ing")
    f.arrow("ing", "q")
    f.arrow("q", "processor", "Consume", ("b", "t"))
    f.arrow("q", "dlq", "Redrive", ("b", "t"), via=[(500, 106), (411, 106)], label_at=(437, 96))
    f.arrow("processor", "data", "Transaction", ("b", "t"))
    f.arrow(
        "processor",
        "archive",
        "Archive",
        ("l", "t"),
        via=[(493, 164), (493, 219), (411, 219)],
        label_at=(452, 211),
    )
    f.arrow("api", "app", "JWT routes", ("b", "t"))
    f.arrow("app", "ctrl", "Request", ("l", "r"))
    f.arrow("ec2", "ctrl", "Poll / ack", ("b", "t"))
    f.arrow(
        "browser", "api", "Access JWT", ("r", "l"), via=[(151, 287), (151, 49)], label_at=(150, 226)
    )
    f.arrow("hosting", "browser", "HTTPS", ("t", "b"))
    f.arrow("app", "athena", "Start / status", ("b", "t"))
    f.arrow("athena", "archive", "Query")
    f.arrow(
        "app",
        "data",
        "Read state",
        ("r", "l"),
        via=[(325, 164), (325, 229), (494, 229), (494, 287)],
        label_at=(341, 214),
    )
    f.arrow("sched", "notify")
    f.arrow("notify", "sns", "Publish")
    f.arrow(
        "data",
        "notify",
        "Pending intents",
        ("b", "t"),
        via=[(580, 351), (411, 351)],
        label_at=(489, 343),
    )
    f.note(
        520, "Cross-cutting: IAM roles, CloudWatch logs/alarms, CloudFormation and logged AWS CLI."
    )
    f.note(
        545, "Four Lambda functions. Live reads use DynamoDB; only requested reports use Athena."
    )
    result.append(f)

    f = Figure(
        "03-network-deployment",
        "Figure 3. Network and runtime boundary",
        "Only the simulator occupies the project VPC. Public IPv4 supports outbound HTTPS; its security group has no inbound rules. Lambda is not placed in this VPC.",
        465,
    )
    f.region(10, 15, 390, 345, "Simulator stack / VPC 10.42.0.0/24")
    f.region(27, 55, 355, 205, "Public subnet 10.42.0.0/26")
    f.box(
        "instance",
        58,
        100,
        290,
        120,
        [
            "EC2 t4g.micro ARM",
            "systemd Python simulator",
            "Encrypted 8 GiB gp3; IMDSv2",
            "IAM instance profile; no SSH ingress",
        ],
    )
    f.box("igw", 75, 285, 255, 55, ["Route + Internet Gateway", "0.0.0.0/0; public IPv4"])
    f.box(
        "endpoints",
        440,
        120,
        192,
        120,
        [
            "Regional AWS endpoints",
            "API Gateway / DynamoDB",
            "SSM / S3 / CloudWatch",
            "Service IAM authorization",
        ],
        "data",
    )
    f.arrow("instance", "igw", "TCP 443 outbound", ("b", "t"))
    f.arrow("igw", "endpoints", "HTTPS", via=[(419, 312), (419, 180)], label_at=(430, 281))
    f.note(397, "DNS egress: TCP/UDP 53 to the VPC resolver 10.42.0.2.")
    f.note(
        421,
        "No NAT Gateway, inbound listener, bastion host or continuously running frontend server.",
    )
    result.append(f)

    f = Figure(
        "04-telemetry-sequence",
        "Figure 4. Telemetry commit and retry sequence",
        "A 202 confirms queue acceptance. Processor archives before per-reading transactions. If a message fails, FIFO processing stops and unprocessed IDs are returned for retry.",
        535,
    )
    f.sequence(
        [
            ("gateway", ["Gateway"]),
            ("ingest", ["API +", "Ingestion"]),
            ("queue", ["SQS FIFO"]),
            ("process", ["Processor"]),
            ("stores", ["S3 +", "DynamoDB"]),
        ],
        [
            (0, 1, "Signed readings"),
            (1, 2, "Validate; enqueue stable batch"),
            (1, 0, "202 after queue acceptance"),
            (2, 3, "Batch event source mapping"),
            (3, 4, "Conditional S3 date archive"),
            (3, 4, "DDB atomic event/state/alert write"),
            (3, 2, "Success or failed/unprocessed IDs"),
            (2, 3, "Retry until DLQ receive limit"),
        ],
    )
    f.note(
        496,
        "Matching event markers suppress recounting; changed-payload event IDs fail validation.",
    )
    result.append(f)

    f = Figure(
        "05-data-model",
        "Figure 5. Logical data model and access patterns",
        "These are DynamoDB item types and S3 layouts, not relational tables. pk/sk compose each item key; a sparse index selects pending notification work.",
        545,
    )
    f.region(10, 15, 385, 410, "Data table: pk + sk / on-demand / encrypted / TTL")
    for ident, x, y, w, h, lines in [
        ("state", 26, 54, 170, 83, ["Device STATE", "pk = motor ID", "latest / rules / revision"]),
        (
            "recent",
            209,
            54,
            170,
            83,
            ["READING#time#ID", "pk = motor ID", "24-hour recent history"],
        ),
        (
            "event",
            26,
            158,
            170,
            83,
            ["EVENT#eventId / META", "fingerprint / archiveKey", "31-day marker"],
        ),
        ("alert", 209, 158, 170, 83, ["ALERT#episode", "pk = motor ID", "active -> resolved"]),
        (
            "outbox",
            26,
            262,
            170,
            83,
            ["NOTIFY / alertId", "delivery + message ID", "pending work attributes"],
        ),
        (
            "reports",
            209,
            262,
            170,
            83,
            ["REPORT#ID / META", "owner / parameters", "daily QUOTA item"],
        ),
    ]:
        f.box(ident, x, y, w, h, lines, "data")
    f.box("gsi", 26, 366, 353, 43, ["Work GSI: workStatus / workAt"], "data")
    f.box(
        "controls",
        435,
        54,
        200,
        125,
        [
            "Controls table",
            "motor ID / CONTROL",
            "requested vs applied",
            "requestId / runId",
            "GATEWAY / RUN",
        ],
        "data",
    )
    f.box(
        "archive",
        435,
        229,
        200,
        94,
        ["S3 archive", "telemetry/day=DATE/", "batchId.json.gz", "30-day current + old versions"],
        "data",
    )
    f.box("results", 435, 366, 200, 60, ["Private S3 results", "Seven-day lifecycle"], "data")
    f.arrow("outbox", "gsi", "Pending only", ("b", "t"), label_at=(112, 359))
    f.arrow(
        "event",
        "archive",
        "Archive pointer",
        via=[(201, 199), (201, 150), (405, 150), (405, 276)],
        label_at=(450, 216),
    )
    f.note(
        478, "API date bounds enforce visibility even while asynchronous TTL deletion is pending."
    )
    f.note(
        504,
        "Device state and control records remain current; history items have separate lifetimes.",
    )
    result.append(f)

    f = Figure(
        "06-auth-sequence",
        "Figure 6. Browser authentication and authorization",
        "The browser is a public client with no client secret. The access token authorizes application APIs; privileged backend requests also check current Cognito groups.",
        545,
    )
    f.sequence(
        [
            ("browser", ["React browser"]),
            ("cognito", ["Cognito", "hosted login"]),
            ("api", ["API Gateway", "JWT authorizer"]),
            ("backend", ["ApiBackend"]),
            ("data", ["DynamoDB /", "Cognito groups"]),
        ],
        [
            (0, 1, "Authorize: code + state + S256"),
            (1, 0, "Callback: code + matching state"),
            (0, 1, "Exchange code + PKCE verifier"),
            (1, 0, "Access / ID / refresh tokens"),
            (0, 2, "Bearer access token"),
            (2, 3, "Validated principal + claims"),
            (3, 4, "Role/owner check; current operator"),
            (3, 0, "Authorized result or rejection"),
        ],
    )
    f.note(505, "Session storage is per tab. Sign-out clears local session and uses hosted logout.")
    result.append(f)

    f = Figure(
        "07-control-fault-state",
        "Figure 7. Controls and fault state machines",
        "Control acknowledgement and measured fault state are different processes. Reset changes the requested simulator mode; actual healthy readings resolve an alert.",
        515,
    )
    f.box("request", 12, 45, 175, 76, ["Operator request", "new requestId", "status pending"])
    f.box(
        "apply", 238, 45, 175, 76, ["Simulator poll", "Match request / run", "Apply + acknowledge"]
    )
    f.box(
        "timeout",
        465,
        45,
        173,
        76,
        ["No ack after 60s", "UI timeout", "Request retained"],
        "warning",
    )
    f.arrow("request", "apply", "~5-second poll")
    f.arrow("apply", "timeout", "If no ack")
    f.text(18, 175, "Per-device, per-rule measured state", 13, True, "start")
    f.box(
        "healthy", 12, 220, 175, 80, ["Healthy rule", "above = 0..2", "No active episode"], "data"
    )
    f.box(
        "active",
        238,
        220,
        175,
        80,
        ["Active episode", "Record alert + intent", "No repeat activation"],
        "warning",
    )
    f.box(
        "resolved",
        465,
        220,
        173,
        80,
        ["Resolved episode", "Keep alert history", "No recovery email"],
        "data",
    )
    f.arrow("healthy", "active", "3 consecutive breaches", label_at=(214, 207))
    f.arrow("active", "resolved", "3 consecutive healthy", label_at=(438, 207))
    f.arrow(
        "resolved",
        "healthy",
        "A later episode may activate again",
        ("b", "b"),
        via=[(551, 355), (99, 355)],
        label_at=(325, 347),
    )
    f.note(
        411, "Temperature >75 C; vibration >4.5 mm/s. Each opposite reading resets its sequence."
    )
    f.note(
        437, "Stopped + reporting can be online. No valid processed receipt for 60s means offline."
    )
    f.note(463, "Only newer observations advance counters. Operator reset does not delete alerts.")
    result.append(f)

    f = Figure(
        "08-reports-recovery",
        "Figure 8. Historical reports and limited recovery",
        "Reporting and reconstruction reuse private history for different purposes. Reconstruction targets a disposable table and never republishes old fault emails.",
        520,
    )
    f.box("browser", 12, 35, 145, 70, ["Authenticated UI", "Report parameters"])
    f.box("backend", 224, 35, 185, 70, ["ApiBackend", "Validate / quota / owner"])
    f.box("athena", 477, 35, 160, 70, ["Athena workgroup", "10 MiB scan limit"])
    f.box(
        "archive",
        477,
        176,
        160,
        85,
        ["Private S3 archive", "Projected dates", "Glue table schema"],
        "data",
    )
    f.box(
        "results",
        224,
        176,
        185,
        85,
        ["Private results", "Owner-checked status", "Charts / table / CSV"],
        "data",
    )
    f.box(
        "recovery",
        12,
        340,
        175,
        85,
        ["Recovery script", "Bounded archive prefix", "Dedup + original times"],
    )
    f.box(
        "table",
        255,
        340,
        175,
        85,
        ["Disposable table", "Reconstructed state", "No live-table writes"],
        "data",
    )
    f.box(
        "verify",
        477,
        340,
        160,
        85,
        ["Verify + clean up", "No SNS publication", "Not regional DR"],
        "external",
    )
    f.arrow("browser", "backend")
    f.arrow("backend", "athena", "Predefined SQL")
    f.arrow("athena", "archive", "Read", ("b", "t"))
    f.arrow(
        "athena",
        "results",
        "Query output",
        ("l", "r"),
        via=[(444, 70), (444, 218)],
        label_at=(443, 143),
    )
    f.arrow(
        "results",
        "browser",
        "Poll result via API",
        ("l", "b"),
        via=[(84, 218)],
        label_at=(141, 205),
    )
    f.arrow(
        "archive",
        "recovery",
        "Read / sort history",
        ("b", "t"),
        via=[(557, 295), (99, 295)],
        label_at=(302, 287),
    )
    f.arrow("recovery", "table")
    f.arrow("table", "verify")
    f.note(477, "Reports: 1-7 dates within 30 days, at most 100 project report starts per UTC day.")
    result.append(f)

    f = Figure(
        "09-frontend-structure",
        "Figure 9. Frontend software structure",
        "The browser serves five role-aware views. Shared polling and authentication feed a single protected API client; charts and UI state are derived from API responses.",
        465,
    )
    f.box("entry", 10, 35, 150, 67, ["main.tsx", "React root"])
    f.box("app", 229, 35, 185, 67, ["App.tsx", "Auth shell / hash routes"])
    f.box("auth", 478, 35, 160, 67, ["auth.ts", "OIDC / PKCE session"], "auth")
    f.box(
        "pages",
        20,
        184,
        275,
        86,
        ["pages.tsx", "Overview / device / alerts", "Reports / operator users"],
    )
    f.box(
        "components",
        356,
        184,
        275,
        86,
        ["components.tsx", "Recharts / cards / controls", "Accessible shared UI"],
    )
    f.box("hooks", 20, 346, 175, 67, ["hooks.ts", "Poll / clock / abort"])
    f.box("api", 238, 346, 175, 67, ["api.ts", "Access token / timeout"])
    f.box("types", 456, 346, 175, 67, ["types.ts / format.ts", "CSS tokens / entry"])
    f.arrow("entry", "app")
    f.arrow("app", "auth")
    f.arrow("app", "pages", "Route", ("b", "t"), via=[(321, 145), (157, 145)], label_at=(215, 137))
    f.arrow("pages", "components", "Compose")
    f.arrow("pages", "hooks", "Live state", ("b", "t"))
    f.arrow("hooks", "api", "Fetch")
    f.arrow("types", "components", "Types / presentation", ("t", "b"), label_at=(549, 315))
    result.append(f)

    f = Figure(
        "10-deployment-lifecycle",
        "Figure 10. Build, deployment and evidence lifecycle",
        "Infrastructure and static UI have independent release steps. Operator AWS calls use the append-only logger; the document build is an offline authoring step, not another deployment.",
        485,
    )
    f.box("source", 12, 30, 170, 76, ["Git source + PRD", "Python / TypeScript", "infra generator"])
    f.box(
        "validate",
        241,
        30,
        170,
        76,
        ["Validate + test", "pytest / lint / Guard", "TypeScript / browser"],
    )
    f.box(
        "artifacts",
        468,
        30,
        170,
        76,
        ["Artifact stack", "Versioned S3 releases", "Backend + simulator"],
        "data",
    )
    f.box(
        "platform",
        468,
        189,
        170,
        76,
        ["Platform stack", "API / data / identity", "Hosting / monitoring"],
    )
    f.box(
        "sim", 241, 189, 170, 76, ["Simulator stack", "Network / EC2 / SSM", "Supervised gateway"]
    )
    f.box(
        "frontend",
        12,
        189,
        170,
        76,
        ["React build / publish", "Private S3 + config", "CloudFront invalidate"],
    )
    f.box(
        "proof",
        12,
        349,
        290,
        76,
        [
            "Recorded acceptance evidence",
            "AWS scenarios / real browser journeys",
            "Screenshots / hashes / XML",
        ],
        "data",
    )
    f.box(
        "audit",
        350,
        349,
        288,
        76,
        [
            "AWS_COMMANDS.txt",
            "Logged CLI purpose / argv / exit",
            "No response or credential logging",
        ],
        "external",
    )
    f.arrow("source", "validate")
    f.arrow("validate", "artifacts")
    f.arrow("artifacts", "platform", "Deploy", ("b", "t"))
    f.arrow("platform", "sim", "Outputs", ("l", "r"))
    f.arrow("sim", "frontend", "Platform URL/config", ("l", "r"))
    f.arrow("frontend", "proof", "Verify served release", ("b", "t"), label_at=(126, 313))
    f.arrow("platform", "audit", "All operator AWS calls", ("b", "t"), label_at=(532, 313))
    result.append(f)
    return result


def inline(value):
    value = html.escape(value)
    value = re.sub(r"`([^`]+)`", r'<font name="Courier" size="8">\1</font>', value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", value)
    value = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: f'<link href="{m[2]}"><font color="#1e4e79">{m[1]}</font></link>',
        value,
    )
    return value


def styles():
    s = getSampleStyleSheet()
    s.add(
        ParagraphStyle(
            "Body", fontName="Helvetica", fontSize=9.4, leading=14, textColor=INK, spaceAfter=8
        )
    )
    s.add(
        ParagraphStyle(
            "H1",
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=25,
            textColor=BLUE,
            spaceAfter=16,
            keepWithNext=True,
        )
    )
    s.add(
        ParagraphStyle(
            "H2",
            fontName="Helvetica-Bold",
            fontSize=12.3,
            leading=17,
            textColor=BLUE,
            spaceBefore=14,
            spaceAfter=8,
            keepWithNext=True,
        )
    )
    s.add(
        ParagraphStyle(
            "H3",
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=15,
            textColor=INK,
            spaceBefore=10,
            spaceAfter=7,
            keepWithNext=True,
        )
    )
    s.add(
        ParagraphStyle(
            "Cell",
            fontName="Helvetica",
            fontSize=8.1,
            leading=11.7,
            textColor=INK,
            splitLongWords=True,
        )
    )
    s.add(
        ParagraphStyle(
            "Caption", fontName="Helvetica", fontSize=9, leading=13, textColor=MUTED, spaceAfter=12
        )
    )
    s.add(ParagraphStyle("BulletItem", parent=s["Body"], leftIndent=12, firstLineIndent=-8))
    return s


S = styles()
PAGE_W, PAGE_H = A4
CONTENT_W = PAGE_W - 88


def markdown_story(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    flow, i = [], 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r"[-: ]+", c) for c in cells):
                    rows.append(cells)
                i += 1
            count = len(rows[0])
            weights = {2: [0.32, 0.68], 3: [0.26, 0.30, 0.44], 4: [0.21, 0.25, 0.34, 0.20]}[count]
            if path.name == "Requirements.md" and rows[0][0] == "ID":
                weights = [0.10, 0.44, 0.46]
            if rows[0][0] == "Method and route":
                weights = [0.30, 0.40, 0.30]
            if rows[0][0] == "Monthly component":
                weights = [0.77, 0.23]
            data = [
                [
                    Paragraph(
                        ("<b>" if r == 0 else "") + inline(v) + ("</b>" if r == 0 else ""),
                        S["Cell"],
                    )
                    for v in row
                ]
                for r, row in enumerate(rows)
            ]
            table = LongTable(
                data, colWidths=[CONTENT_W * w for w in weights], repeatRows=1, hAlign="LEFT"
            )
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), PALE),
                        (
                            "ROWBACKGROUNDS",
                            (0, 1),
                            (-1, -1),
                            [colors.white, colors.HexColor("#f7f9fb")],
                        ),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 7),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                        ("TOPPADDING", (0, 0), (-1, -1), 7),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                        ("LINEBELOW", (0, 0), (-1, 0), 0.7, colors.HexColor("#b0c2d2")),
                        ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor("#dce4eb")),
                    ]
                )
            )
            flow.extend([table, Spacer(1, 10)])
            continue
        image_match = re.fullmatch(r"!\[([^]]*)\]\(([^)]+)\)", line)
        if image_match:
            image_path = ROOT / image_match[2]
            with PILImage.open(image_path) as img:
                w, h = img.size
            scale = min(CONTENT_W / w, 515 / h)
            flow.append(Image(str(image_path), width=w * scale, height=h * scale, hAlign="CENTER"))
            flow.append(Spacer(1, 10))
            flow.append(Paragraph(inline(image_match[1]), S["Caption"]))
            i += 1
            continue
        heading = re.match(r"^(#{1,3}) (.+)$", line)
        if heading:
            level, title = len(heading[1]), heading[2]
            if title.startswith("Screenshot "):
                flow.append(PageBreak())
            p = Paragraph(inline(title), S[f"H{level}"])
            if level <= 2:
                p.toc_level = level - 1
                p.toc_text = title
            flow.append(p)
            i += 1
            continue
        if re.match(r"^(- |\d+\. )", line):
            line = re.sub(r"^- ", "- ", line)
            flow.append(Paragraph(inline(line), S["BulletItem"]))
            i += 1
            continue
        paragraph = [line]
        i += 1
        while (
            i < len(lines) and lines[i].strip() and not re.match(r"^(#|\||!\[|- |\d+\. )", lines[i])
        ):
            paragraph.append(lines[i].strip())
            i += 1
        flow.append(Paragraph(inline(" ".join(paragraph)), S["Body"]))
    return flow


class SubmissionDoc(BaseDocTemplate):
    def __init__(self, path):
        super().__init__(
            str(path),
            pagesize=A4,
            leftMargin=44,
            rightMargin=44,
            topMargin=48,
            bottomMargin=45,
            title="Cloud-Based Industrial Equipment Monitoring and Fault Detection",
            author="Project submission",
            pageCompression=1,
        )
        self.addPageTemplates(
            PageTemplate(
                id="body",
                frames=Frame(
                    44,
                    45,
                    CONTENT_W,
                    PAGE_H - 93,
                    leftPadding=0,
                    rightPadding=0,
                    topPadding=0,
                    bottomPadding=0,
                ),
                onPage=self.decorate,
            )
        )

    def decorate(self, c, doc):
        c.saveState()
        if doc.page > 1:
            c.setFillColor(MUTED)
            c.setFont("Helvetica", 8)
            c.drawString(44, PAGE_H - 27, "CCPROJ  /  REQUIREMENTS, DESIGN AND IMPLEMENTATION")
            c.setStrokeColor(colors.HexColor("#d7e1e9"))
            c.line(44, PAGE_H - 34, PAGE_W - 44, PAGE_H - 34)
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 8)
        c.drawString(44, 25, "Academic submission  |  15 October 2026")
        c.drawRightString(PAGE_W - 44, 25, str(doc.page))
        c.restoreState()

    def afterFlowable(self, flowable):
        if hasattr(flowable, "toc_level"):
            key = "heading-" + hashlib.sha256(flowable.toc_text.encode()).hexdigest()[:12]
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(
                flowable.toc_text, key, level=flowable.toc_level, closed=False
            )
            self.notify("TOCEntry", (flowable.toc_level, flowable.toc_text, self.page, key))


def build_pdf(figs):
    flow = [Spacer(1, 70)]
    flow.append(
        Paragraph(
            "CLOUD COMPUTING PROJECT",
            ParagraphStyle("Kicker", fontSize=10, leading=15, textColor=MUTED, spaceAfter=18),
        )
    )
    flow.append(
        Paragraph(
            "Cloud-Based Industrial<br/>Equipment Monitoring<br/>and Fault Detection",
            ParagraphStyle(
                "Cover",
                fontName="Helvetica-Bold",
                fontSize=29,
                leading=36,
                textColor=BLUE,
                spaceAfter=24,
            ),
        )
    )
    flow.append(
        Paragraph(
            "Requirements specification<br/>System design and implementation<br/>Tools, diagrams and verification evidence",
            ParagraphStyle("Subtitle", fontSize=15, leading=23, textColor=INK, spaceAfter=28),
        )
    )
    flow.append(
        Paragraph("15 October 2026<br/>AWS Asia Pacific (Sydney) / ap-southeast-2", S["Body"])
    )
    flow.append(Spacer(1, 22))
    flow.append(Paragraph("Deployment: https://d1idggpc663p7f.cloudfront.net", S["Body"]))
    flow.append(
        Paragraph(
            "Prepared from implemented source and recorded acceptance evidence. Source baseline: b31c746; documentation is committed separately.",
            S["Caption"],
        )
    )
    flow.append(
        Paragraph(
            "Acceptance exception: initial-account password setup/recovery remains unresolved. Final actual AWS spend has not yet been reconciled. See sections 2.14 and 4.5.",
            S["Body"],
        )
    )
    flow.append(PageBreak())
    flow.append(Paragraph("Contents", S["H1"]))
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle(
            "TOC0",
            fontName="Helvetica-Bold",
            fontSize=10.2,
            leading=17,
            textColor=BLUE,
            spaceBefore=10,
        ),
        ParagraphStyle(
            "TOC1", fontName="Helvetica", fontSize=9, leading=14, leftIndent=12, textColor=INK
        ),
    ]
    flow.extend([toc, PageBreak()])
    for filename in (
        "Requirements.md",
        "Design_and_Implementation.md",
        "Tools_Used.md",
        "Evidence.md",
    ):
        flow.extend(markdown_story(ROOT / filename))
        flow.append(PageBreak())
    p = Paragraph("Part 5. Architecture and design diagrams", S["H1"])
    p.toc_level, p.toc_text = 0, "Part 5. Architecture and design diagrams"
    flow.extend(
        [
            p,
            Paragraph(
                "Ten diagrams describe the implemented system at complementary levels. Arrows show request, data or dependency direction as labeled. Boxes are logical responsibilities unless a network boundary is explicitly drawn. Full-size SVG/PNG and editable Mermaid versions accompany the report.",
                S["Body"],
            ),
        ]
    )
    for n, f in enumerate(figs):
        if n:
            flow.append(PageBreak())
        p = Paragraph(f.title, S["H2"])
        p.toc_level, p.toc_text = 1, f.title
        scaled = Drawing(CONTENT_W, f.height * CONTENT_W / f.width)
        # A drawing in a group is independently transformed, keeping the original vector artifact intact.
        from reportlab.graphics.shapes import Group

        group = Group()
        group.add(f.d)
        group.scale(CONTENT_W / f.width, CONTENT_W / f.width)
        scaled.add(group)
        flow.extend(
            [p, Spacer(1, 12), scaled, Spacer(1, 16), Paragraph(inline(f.caption), S["Caption"])]
        )
    SubmissionDoc(ROOT / "Submission_Report.pdf").multiBuild(flow)


def main():
    for folder in (DIAGRAMS, QA, ROOT / "assets", ROOT / "evidence"):
        folder.mkdir(parents=True, exist_ok=True)
    for name in (
        "live-acceptance.json",
        "ui-acceptance.json",
        "ui-live-smoke.json",
        "deployed-evidence.json",
        "notification-evidence.json",
        "budget-model.json",
    ):
        shutil.copyfile(REPO / "docs" / name, ROOT / "evidence" / name)
    for path in sorted((REPO / "docs").glob("ui-*.png")):
        shutil.copyfile(path, ROOT / "assets" / path.name)
    # A viewport excerpt is legible in print; the unchanged full-page original accompanies it.
    with PILImage.open(ROOT / "assets" / "ui-overview-mobile.png") as image:
        image.crop((0, 0, image.width, min(844, image.height))).save(
            ROOT / "assets" / "ui-overview-mobile-viewport.png"
        )
    figs = figures()
    index = [
        "# Part 5. Architecture and design diagrams\n",
        "All diagrams describe the implemented design. SVG is the vector submission original; PNG is a convenient preview; Mermaid is editable semantic source. The PDF embeds vector drawings. Colors distinguish compute (blue), stores (green), identity (purple), external actors (grey) and exceptional states (amber). Arrows show the labeled request/data/dependency direction; network boundaries are explicit only in Figure 3.\n",
    ]
    for f in figs:
        f.save()
        index += [
            f"## {f.title}\n",
            f.caption + "\n",
            f"![{f.title}](diagrams/{f.slug}.svg)\n",
            f"[PNG](diagrams/{f.slug}.png) | [Editable Mermaid](diagrams/{f.slug}.mmd)\n",
        ]
    (ROOT / "Diagrams.md").write_text("\n".join(index), encoding="utf-8")
    build_pdf(figs)
    missing = []
    for path in ROOT.glob("*.md"):
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if (
                not re.match(r"https?://", target)
                and not (path.parent / target.split("#")[0]).exists()
            ):
                missing.append(f"{path.name}: {target}")
    if missing:
        raise RuntimeError("Broken links: " + str(missing))
    import pdfplumber

    with pdfplumber.open(ROOT / "Submission_Report.pdf") as pdf:
        pages = [p.extract_text() or "" for p in pdf.pages]
        for required in (
            "FR-11",
            "FORCE_CHANGE_PASSWORD",
            "Tools and technologies",
            "Figure 10.",
            "26.93",
            "23 passed",
        ):
            if required not in "\n".join(pages):
                raise RuntimeError("Missing PDF content: " + required)
        if any(not p.strip() for p in pages):
            raise RuntimeError("Empty PDF page")
    manifest = {
        "preparedDate": "2026-10-15",
        "sourceBaseline": "b31c746",
        "awsOperationsDuringDocumentBuild": 0,
        "pdfPages": len(pages),
        "diagrams": len(figs),
        "markdownLinks": "all local targets exist",
        "note": "Recorded tests were not rerun for document generation. Hashes exclude this manifest and ignored QA intermediates.",
        "files": {},
    }
    for path in sorted(ROOT.rglob("*")):
        if (
            path.is_file()
            and not any(x in (".qa", "__pycache__") for x in path.parts)
            and path.name != "manifest.json"
        ):
            manifest["files"][path.relative_to(ROOT).as_posix()] = {
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
    (ROOT / "evidence" / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "pages": len(pages),
                "diagrams": len(figs),
                "files": len(manifest["files"]),
                "links": "PASS",
                "pdfText": "PASS",
            }
        )
    )


if __name__ == "__main__":
    main()
