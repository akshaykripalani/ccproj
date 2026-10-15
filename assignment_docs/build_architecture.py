"""Build the single presentation architecture as SVG and PNG; no AWS operations.

Uses the document-authoring runtime: reportlab and pypdfium2.
The temporary rasterization PDF is deleted; only the two requested images remain.
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

from reportlab.graphics import renderPDF, renderSVG
from reportlab.graphics.shapes import Drawing, Polygon, PolyLine, Rect, String
from reportlab.lib.colors import HexColor

ROOT = Path(__file__).resolve().parent
WIDTH, HEIGHT = 1920, 1080
INK, MUTED, LINE = "#172b3b", "#526674", "#657b89"
COLORS = {
    "compute": "#246a8a",
    "store": "#28765e",
    "identity": "#76509c",
    "queue": "#a56220",
    "external": "#526674",
}


class ArchitectureFigure:
    slug = "02-aws-components"
    title = "Figure 2. AWS architecture overview"
    caption = (
        "Presentation overview: the React dashboard uses API Gateway and App Lambda; "
        "EC2 telemetry passes through Ingestion, SQS and Processor. DynamoDB serves "
        "live state, S3 preserves history, and Athena/Glue support reports. Fault "
        "notifications use a DynamoDB outbox, scheduled Notifier Lambda and SNS. "
        "Grouped boxes summarize services, not physical deployment boundaries."
    )
    width, height = WIDTH, HEIGHT

    def __init__(self):
        self.d = Drawing(WIDTH, HEIGHT)
        self.d.add(Rect(0, 0, WIDTH, HEIGHT, fillColor=HexColor("#ffffff"), strokeColor=None))
        self.nodes = {}
        self.edges = []
        self.compose()

    def text(self, x, y, text, size=16, color=INK, bold=False, anchor="start"):
        self.d.add(
            String(
                x,
                HEIGHT - y,
                text,
                fontName="Helvetica-Bold" if bold else "Helvetica",
                fontSize=size,
                fillColor=HexColor(color),
                textAnchor=anchor,
            )
        )

    def head(self, origin, end, color=LINE):
        angle = math.atan2(end[1] - origin[1], end[0] - origin[0])
        pts = [end] + [
            (end[0] - 9 * math.cos(angle + s * 0.44), end[1] - 9 * math.sin(angle + s * 0.44))
            for s in (-1, 1)
        ]
        self.d.add(
            Polygon(
                [v for x, y in pts for v in (x, HEIGHT - y)],
                fillColor=HexColor(color),
                strokeColor=None,
            )
        )

    def edge(self, source, target, points, both=False):
        self.d.add(
            PolyLine(
                [v for x, y in points for v in (x, HEIGHT - y)],
                strokeColor=HexColor(LINE),
                strokeWidth=1.8,
                fillColor=None,
            )
        )
        self.head(points[-2], points[-1])
        if both:
            self.head(points[1], points[0])
        self.edges.append((source, target, "", both))

    def compose(self):
        self.text(100, 65, "FORGE / AWS ARCHITECTURE", 16, "#246a8a", True)
        self.text(100, 122, "Industrial motor monitoring", 42, bold=True)
        self.text(1720, 70, "Sydney / ap-southeast-2", 21, MUTED, anchor="end")

        self.simple_box(
            "dashboard",
            100,
            210,
            300,
            "Dashboard",
            ["React / S3 + CloudFront", "Cognito sign-in"],
            "external",
        )
        self.simple_box("api", 540, 210, 300, "API Gateway", ["Secure API access"], "compute")
        self.simple_box(
            "app",
            980,
            210,
            300,
            "App Lambda",
            ["Live views / motor controls", "Users / report requests"],
            "compute",
        )
        self.simple_box(
            "data",
            1420,
            210,
            300,
            "Data & reporting",
            ["DynamoDB: live state", "S3: historical readings", "Athena + Glue: reports"],
            "store",
        )

        self.simple_box(
            "ec2", 100, 525, 300, "EC2 simulator", ["Three simulated motors"], "compute"
        )
        self.simple_box("ing", 540, 525, 300, "Ingestion Lambda", ["Validate telemetry"], "compute")
        self.simple_box("queue", 980, 525, 300, "SQS queue", ["Buffer / retry telemetry"], "queue")
        self.simple_box(
            "processor",
            1420,
            525,
            300,
            "Processor Lambda",
            ["Store readings / detect faults"],
            "compute",
        )

        self.simple_box(
            "notifications",
            980,
            825,
            740,
            "Fault notifications",
            ["DynamoDB outbox / scheduled Notifier Lambda / SNS email"],
            "queue",
            h=120,
        )

        self.edge("dashboard", "api", [(400, 290), (540, 290)])
        self.edge("api", "app", [(840, 290), (980, 290)])
        self.edge("app", "data", [(1280, 290), (1420, 290)], both=True)
        self.edge("ec2", "api", [(400, 605), (465, 605), (465, 425), (620, 425), (620, 370)])
        self.edge("api", "ing", [(760, 370), (760, 525)])
        self.edge("ing", "queue", [(840, 605), (980, 605)])
        self.edge("queue", "processor", [(1280, 605), (1420, 605)])
        self.edge("processor", "data", [(1570, 525), (1570, 370)])
        self.edge("data", "notifications", [(1720, 290), (1800, 290), (1800, 885), (1720, 885)])

        self.d.add(
            PolyLine(
                [100, HEIGHT - 995, 1720, HEIGHT - 995],
                strokeColor=HexColor("#d9e1e7"),
                strokeWidth=1,
            )
        )
        self.text(
            100, 1035, "IAM roles  /  CloudFormation  /  CloudWatch  /  AWS Budgets", 20, MUTED
        )

    def simple_box(self, ident, x, y, w, title, details, kind, h=160):
        from reportlab.pdfbase.pdfmetrics import stringWidth

        self.nodes[ident] = (title, "", details)
        self.d.add(
            Rect(
                x,
                HEIGHT - y - h,
                w,
                h,
                rx=6,
                ry=6,
                fillColor=HexColor("#ffffff"),
                strokeColor=HexColor("#b9cbd6"),
                strokeWidth=1.6,
            )
        )
        self.d.add(
            Rect(x, HEIGHT - y - h, 5, h, fillColor=HexColor(COLORS[kind]), strokeColor=None)
        )
        self.text(x + 23, y + 43, title, 25, bold=True)
        assert stringWidth(title, "Helvetica-Bold", 25) < w - 46, title
        for i, line in enumerate(details):
            self.text(x + 23, y + 78 + 29 * i, line, 19, MUTED)
            assert stringWidth(line, "Helvetica", 19) < w - 46, line

    def save(self):
        import pypdfium2 as pdfium

        target = ROOT / "diagrams"
        target.mkdir(exist_ok=True)
        renderSVG.drawToFile(self.d, str(target / f"{self.slug}.svg"))
        with tempfile.TemporaryDirectory(prefix="forge-architecture-") as folder:
            temp = Path(folder) / "raster-source.pdf"
            renderPDF.drawToFile(self.d, str(temp))
            pdf = pdfium.PdfDocument(str(temp))
            page = pdf[0]
            bitmap = page.render(scale=2)
            bitmap.to_pil().save(target / f"{self.slug}.png")
            bitmap.close()
            page.close()
            pdf.close()
        # Keep the existing semantic source aligned with the exported diagram.
        mermaid = ["flowchart TB"]
        for ident, (service, title, details) in self.nodes.items():
            label = "<br/>".join(value for value in [service, title, *details] if value)
            mermaid.append(f'    {ident}["{label}"]')
        for source, target_id, label, both in self.edges:
            arrow = "<-->" if both else "-->"
            mermaid.append(
                f'    {source} {arrow}|"{label}"| {target_id}'
                if label
                else f"    {source} {arrow} {target_id}"
            )
        (target / f"{self.slug}.mmd").write_text("\n".join(mermaid) + "\n", encoding="utf-8")


if __name__ == "__main__":
    ArchitectureFigure().save()
    print("Updated 02-aws-components.svg and 02-aws-components.png (3840 x 2160).")
