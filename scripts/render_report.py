"""Windows Word fallback for DOCX visual QA when LibreOffice is unavailable.

Run with the bundled artifact Python. Opens only the named document, read-only,
in a dedicated hidden Word instance, exports PDF, and renders every page with Poppler.
"""

import argparse
import json
from pathlib import Path

import pythoncom
import win32com.client
from pdf2image import convert_from_path


def render(source, destination):
    destination.mkdir(parents=True, exist_ok=True)
    pdf = destination / (source.stem + ".pdf")
    pythoncom.CoInitialize()
    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    word.AutomationSecurity = 3
    document = None
    try:
        document = word.Documents.Open(str(source.resolve()), ReadOnly=True, AddToRecentFiles=False, Visible=False)
        document.ExportAsFixedFormat(str(pdf.resolve()), 17, OpenAfterExport=False)
    finally:
        if document is not None:
            document.Close(False)
        word.Quit()
        pythoncom.CoUninitialize()
    pages = convert_from_path(str(pdf), dpi=130, output_folder=str(destination), fmt="png", output_file="page", paths_only=True)
    print(json.dumps({"pdf": str(pdf.resolve()), "pageCount": len(pages), "pages": pages}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    render(args.source, args.destination)
