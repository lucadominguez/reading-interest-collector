"""Recover surrounding context for a labelled passage from a LOCAL source file.

The logger only stores the selected passage + a source identifier (lightweight).
When you later want the surrounding paragraph/page context, use this to pull it
back from the file on disk. The web has no local copy, so URLs just return the
stored passage untouched.

All functions are best-effort and never raise on a missing/unparseable file;
they return None or an empty description instead.

Recovery functions
------------------
    recover_text_file(source, selected_text, context_chars=500)
        Plain text / markdown / source files: return the window of text around
        the first occurrence of the passage.

    recover_pdf(source, page, selected_text, context_chars=600)
        PDF (SumatraPDF etc): if `page` is known, return that page's text with
        the passage window highlighted-position info; otherwise search.
        Requires `pymupdf` (fitz) to be importable; degrades gracefully.

    recover_context(observation) -> str
        Dispatcher that inspects an observation dict and calls the right one.
"""

import os


def _mark(text, passage, context_chars):
    """Return a snippet around `passage` in `text` with a marker, or None."""
    if not text or not passage:
        return None
    idx = text.find(passage)
    if idx < 0:
        # Try a fuzzy match on the first 40 chars of the passage.
        probe = passage[:40]
        idx = text.find(probe)
        if idx < 0:
            return None
    start = max(0, idx - context_chars // 2)
    end = min(len(text), idx + len(passage) + context_chars // 2)
    snippet = text[start:end]
    if start > 0:
        snippet = "... " + snippet
    if end < len(text):
        snippet = snippet + " ..."
    return snippet


def recover_text_file(source, selected_text, context_chars=500):
    try:
        with open(source, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except (OSError, IOError):
        return None
    return _mark(text, selected_text, context_chars)


def recover_pdf_page(page_text, selected_text, context_chars=600):
    return _mark(page_text, selected_text, context_chars)


def recover_pdf(source, page=None, selected_text=None, context_chars=600):
    """Return a dict of context info, or None on any failure.

    Uses pymupdf when available; returns page count + page text snippets.
    """
    try:
        import pymupdf  # also exposes `fitz`
    except Exception:
        try:
            import fitz as pymupdf
        except Exception:
            return None
    try:
        doc = pymupdf.open(source)
    except Exception:
        return None
    info = {"pages": doc.page_count, "source": source}
    # Index text and find first page containing the passage if page unknown.
    if page is not None and 1 <= page <= doc.page_count:
        candidates = [page]
    elif selected_text:
        candidates = []
        probe = (selected_text[:40] or "") if selected_text else ""
        for pno in range(doc.page_count):
            text = doc[pno].get_text()
            if selected_text and selected_text in text:
                candidates.append(pno + 1)
                break
            if probe and probe in text:
                candidates.append(pno + 1)
                break
        if not candidates:
            try:
                doc.close()
            except Exception:
                pass
            return info
    else:
        try:
            doc.close()
        except Exception:
            pass
        return info

    page_no = candidates[0]
    try:
        text = doc[page_no - 1].get_text()
    except Exception:
        text = ""
    finally:
        try:
            doc.close()
        except Exception:
            pass
    info["page"] = page_no
    snippet = recover_pdf_page(text, selected_text, context_chars)
    if snippet:
        info["context"] = snippet
    return info


def recover_context(observation, context_chars=500):
    """Dispatch on an observation dict -> human-readable context string."""
    source = observation.get("source")
    selected = observation.get("selected_text")
    page = observation.get("page")
    if not source:
        return "no source"
    if source.startswith(("http://", "https://")):
        return "web source (no local copy) - stored passage only"
    lower = source.lower()
    is_pdf = lower.endswith(".pdf")
    if is_pdf:
        info = recover_pdf(source, page=page, selected_text=selected,
                           context_chars=context_chars)
        if info and info.get("context"):
            return "pdf p.%s: %s" % (info.get("page", "?"), info["context"])
        return "pdf (context not recovered)"
    snippet = recover_text_file(source, selected, context_chars)
    if snippet:
        return snippet
    return "text source (context not recovered)"
