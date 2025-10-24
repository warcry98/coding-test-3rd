from __future__ import annotations
from itertools import groupby
from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple
import re
from pdfplumber.page import Page
from app.models.transaction import CapitalCall, Distribution, Adjustment
from app.models.document import Document
from app.models.fund import Fund

TABLE_SETTINGS = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "snap_tolerance": 3,
    "join_tolerance": 3,
    "edge_min_length": 3,
    "min_words_vertical": 2,
    "min_words_horizontal": 1,
    "text_x_tolerance": 2,
    "text_y_tolerance": 3,
}

@dataclass(frozen=True)
class HeadingHeuristics:
    # search windows (as ratios of page height)
    same_page_window_ratio: float = 0.40
    cross_page_trigger_ratio: float = 0.16
    prev_page_band_ratio: float = 0.25
    # geometric / font tolerances
    y_tolerance: float = 2.0
    max_merge_gap_ratio: float = 0.015
    font_similarity_tol: float = 0.10
    # overlap thresholds: wide vs narrow tables
    narrow_table_threshold_ratio: float = 0.45
    min_overlap_ratio_wide: float = 0.25
    min_overlap_ratio_narrow: float = 0.15
    # center alignment leniency
    center_tolerance_ratio: float = 0.30
    min_loose_overlap_ratio: float = 0.10
    # heading shape guard
    max_heading_words: int = 8

class TableParser:
    def __init__(self):
        self._heading_cache: Dict[int, Dict[str, object]] = {}

    def parse(self, pages: List[Page], fund_id: int, document_id: int) -> List[Dict]:
        parsed_data = {}

        first_page = pages[0]
        text = first_page.extract_text()
        metadata = self._extract_metadata_from_text(text)

        from app.db.session import SessionLocal

        db = SessionLocal()

        try:
            data_fund = list(metadata.values())
            fund = db.query(Fund).filter(Fund.id == fund_id).first()
            if fund:
                fund.name = data_fund[0]
                fund.gp_name = data_fund[1]
                fund.fund_type = "Venture Capital"
                fund.vintage_year = int(data_fund[2])
            else:
                fund = Fund(
                    id=fund_id,
                    name=data_fund[0],
                    gp_name=data_fund[1],
                    fund_type="Venture Capital",
                    vintage_year=int(data_fund[2])
                )
                db.add(fund)
                db.commit()
                db.refresh(fund)
            
            document = db.query(Document).filter(Document.id == document_id).first()
            document.fund_id = fund_id
            db.commit()

        except Exception as e:
            print(e)

        parsed_data["metadata"] = metadata
        parsed_data["tables"] = self._extract_tables_and_heading(pages)

        return parsed_data
    
    def classify(self, table: Dict, fund_id: int):
        from app.db.session import SessionLocal

        db = SessionLocal()

        headers, *rows = table["data"]
        records = [dict(zip(headers, row)) for row in rows]
        for rec in records:
            data = list(rec.values())
            
            try:
                if "capital call" in table["heading"].lower():
                    amount = 0
                    temp_amount = data[2].replace("$", "").replace(",", "")
                    if temp_amount:
                        amount = int(temp_amount)
                    capitall_calls = CapitalCall(
                        fund_id=fund_id,
                        call_date=data[0],
                        call_type=data[1],
                        amount=amount,
                        description=data[3],
                    )
                    db.add(capitall_calls)
                    db.commit()
                    db.refresh(capitall_calls)
                elif "distribution" in table["heading"].lower():
                    is_recallable = False
                    amount = 0
                    if data[3].lower() == "yes":
                        is_recallable = True
                    temp_amount = data[2].replace("$", "").replace(",", "")
                    if temp_amount:
                        amount = int(temp_amount)
                    distribution = Distribution(
                        fund_id=fund_id,
                        distribution_date=data[0],
                        distribution_type=data[1],
                        is_recallable=is_recallable,
                        amount=amount,
                        description=data[4],
                    )
                    db.add(distribution)
                    db.commit()
                    db.refresh(distribution)
                elif "adjustment" in table["heading"].lower():
                    is_contribution_adjustment = False
                    if "adjustment" in data[3].lower():
                        is_contribution_adjustment = True
                    amount = 0
                    temp_amount = data[2].replace("$", "").replace(",", "")
                    if temp_amount:
                        amount = int(temp_amount)
                    adjustment = Adjustment(
                        fund_id=fund_id,
                        adjustment_date=data[0],
                        adjustment_type=data[1],
                        amount=amount,
                        is_contribution_adjustment=is_contribution_adjustment,
                        description=data[3],
                    )
                    db.add(adjustment)
                    db.commit()
                    db.refresh(adjustment)
            except Exception as e:
                print(e)


    # ---------- core extraction ----------
    def _extract_metadata_from_text(self, text: str) -> dict:
        metadata = {}
        for line in text.splitlines():
            if ":" not in line:
                continue
            parts = line.split(":", 1)
            key, val = parts[0].strip(), parts[1].strip()
            if not key or not val:
                continue
            metadata[key] = val
        return metadata
    
    def _extract_tables_and_heading(
        self,
        pages: List[Page],
        cfg: HeadingHeuristics = HeadingHeuristics(),
    ) -> List[Dict]:
        out: List[Dict] = []
        for page_idx, page in enumerate(pages):
            tables = page.find_tables(table_settings=TABLE_SETTINGS) or []
            if not tables:
                continue
            extracted = page.extract_tables(table_settings=TABLE_SETTINGS) or []
            for table_obj, rows in zip(tables, extracted):
                raw_heading = self._find_heading_near_table(
                    pages=pages,
                    page_idx=page_idx,
                    table_bbox=table_obj.bbox,
                    cfg=cfg,
                )
                # Normalize only if it's a legit heading (not header/metadata)
                normalized = self._normalize_heading(raw_heading) if raw_heading else None
                # Deterministic reconciliation: prefer content when raw is missing/invalid or conflicts
                final_heading = self._reconcile_heading(normalized, raw_heading, rows)

                out.append({
                    "page": page_idx + 1,
                    "heading_raw": raw_heading,
                    "heading": final_heading,
                    "bbox": table_obj.bbox,
                    "data": rows,
                })
        return out

    # ---------- heading detection: rule-based, no scoring ----------
    def _find_heading_near_table(
        self,
        pages: List[Page],
        page_idx: int,
        table_bbox: Tuple[float, float, float, float],
        cfg: HeadingHeuristics = HeadingHeuristics(),
    ) -> Optional[str]:
        page = pages[page_idx]
        t_x0, t_top, t_x1, _ = table_bbox
        table_width = max(1e-6, t_x1 - t_x0)
        table_center = (t_x0 + t_x1) / 2.0

        _, lines, median_font, page_h, page_w = self._get_page_textlines(page_idx, pages, cfg)

        # choose overlap threshold (narrow vs wide tables)
        min_overlap = (
            cfg.min_overlap_ratio_narrow
            if (table_width / max(page_w, 1e-6)) <= cfg.narrow_table_threshold_ratio
            else cfg.min_overlap_ratio_wide
        )

        def qualifies(ln) -> Optional[Tuple[float, float, float]]:
            """Return deterministic tie-break tuple if candidate qualifies: (distance_up, -font_size, center_delta_ratio)."""
            if ln["bottom"] > t_top:
                return None
            if len(ln["text"].split()) > cfg.max_heading_words:
                return None

            overlap = max(0.0, min(ln["x1"], t_x1) - max(ln["x0"], t_x0))
            overlap_ratio = overlap / table_width

            line_center = (ln["x0"] + ln["x1"]) / 2.0
            center_delta_ratio = abs(line_center - table_center) / table_width

            if not (overlap_ratio >= min_overlap or
                    (center_delta_ratio <= cfg.center_tolerance_ratio and
                     overlap_ratio >= cfg.min_loose_overlap_ratio)):
                return None

            # reject metadata/header-ish immediately
            merged = self._merge_multiline(lines, ln, page_h, cfg)
            if self._is_headerish_line(merged) or self._is_metadata_line(merged):
                return None

            distance_up = t_top - ln["bottom"]
            return (distance_up, -ln["size_max"], center_delta_ratio)

        def pick_in_window(lines_, max_height_above: float) -> Optional[str]:
            cands: List[Tuple[Tuple[float, float, float], dict]] = []
            for ln in lines_:
                d = t_top - ln["bottom"]
                if d < 0 or d > max_height_above:
                    continue
                keys = qualifies(ln)
                if keys is not None:
                    cands.append((keys, ln))
            if not cands:
                return None
            # nearest → larger font → more centered
            cands.sort(key=lambda kv: (kv[0][0], kv[0][1], kv[0][2]))
            best_ln = cands[0][1]
            return self._merge_multiline(lines, best_ln, page_h, cfg)

        # progressively widen the same-page window
        windows = [
            max(cfg.same_page_window_ratio * page_h, 1.5 * median_font),
            0.25 * page_h,
            0.40 * page_h,
        ]
        for win in windows:
            res = pick_in_window(lines, win)
            if res:
                return res

        # cross-page fallback: bottom band of previous page if table starts near top
        if page_idx > 0 and t_top <= (cfg.cross_page_trigger_ratio * page_h):
            _, prev_lines, _, prev_h, _ = self._get_page_textlines(page_idx - 1, pages, cfg)
            band_h = cfg.prev_page_band_ratio * prev_h
            band_top = max(0.0, prev_h - band_h)
            band_lines = [ln for ln in prev_lines if ln["bottom"] >= band_top]
            res = pick_in_window(band_lines, band_h)
            if res:
                return res

        return None

    # ---------- text utilities ----------
    def _get_page_textlines(
        self,
        page_idx: int,
        pages: List[Page],
        cfg: HeadingHeuristics,
    ):
        if page_idx in self._heading_cache:
            c = self._heading_cache[page_idx]
            return c["words"], c["lines"], c["median_font"], c["height"], c["width"]

        page = pages[page_idx]
        words = page.extract_words(extra_attrs=["size", "fontname"]) or []
        for w in words:
            w["_top_round"] = round(w["top"] / cfg.y_tolerance) * cfg.y_tolerance

        lines = []
        for _, group in groupby(sorted(words, key=lambda w: (w["_top_round"], w["x0"])),
                                key=lambda w: w["_top_round"]):
            gw = list(group)
            lines.append({
                "text": " ".join(w["text"] for w in gw).strip(),
                "x0": min(w["x0"] for w in gw),
                "x1": max(w["x1"] for w in gw),
                "top": min(w["top"] for w in gw),
                "bottom": max(w["bottom"] for w in gw),
                "size_max": max(w.get("size", 0.0) for w in gw),
            })

        sizes = sorted((w.get("size", 12.0) for w in words))
        median_font = 12.0
        if sizes:
            mid = len(sizes) // 2
            median_font = sizes[mid] if len(sizes) % 2 else (sizes[mid - 1] + sizes[mid]) / 2.0

        lines.sort(key=lambda l: (l["top"], l["x0"]))
        self._heading_cache[page_idx] = {
            "words": words,
            "lines": lines,
            "median_font": median_font,
            "height": page.height,
            "width": page.width,
        }
        return words, lines, median_font, page.height, page.width

    def _merge_multiline(
        self,
        all_lines: List[dict],
        seed: dict,
        page_height: float,
        cfg: HeadingHeuristics,
    ) -> str:
        gap_tol = cfg.max_merge_gap_ratio * page_height
        merged = [seed]
        i = all_lines.index(seed) - 1
        head = seed
        while i >= 0:
            ln = all_lines[i]
            close = (head["top"] - ln["bottom"]) <= gap_tol
            size_sim = (abs(ln["size_max"] - head["size_max"]) /
                        max(head["size_max"], 1e-6)) <= cfg.font_similarity_tol
            if close and size_sim:
                merged.insert(0, ln)
                head = ln
                i -= 1
            else:
                break
        out_text = " ".join(x["text"] for x in merged).strip()
        return re.sub(r"\s+", " ", out_text)

    # ---------- classification (deterministic, no scoring) ----------
    _HEADER_TOKENS = {
        "date", "amount", "description", "type", "call", "number",
        "recallable", "balance", "nav", "units", "unit", "price",
        "transaction", "id", "qty",
    }
    _META_TOKENS = {
        "fund", "name", "gp", "vintage", "year", "size", "report", "date"
    }
    _META_KEYWORDS = (
        "fund name", "gp", "vintage year", "fund size", "report date"
    )

    def _tokens(self, s: str):
        return [t for t in re.findall(r"[a-z]+", (s or "").lower()) if t]

    def _is_headerish_line(self, text: str) -> bool:
        toks = self._tokens(text)
        if not toks:
            return False
        hit = sum(1 for t in toks if t in self._HEADER_TOKENS)
        return (hit / max(len(toks), 1) >= 0.60) or (hit >= 3)

    def _is_metadata_line(self, text: str) -> bool:
        """Reject fund-level metadata like 'Fund Name: ... GP: ... Report Date: ...'."""
        if not text:
            return False
        lowered = text.lower()
        # many key:value pairs → metadata
        if lowered.count(":") >= 2:
            return True
        # explicit keywords
        if any(k in lowered for k in self._META_KEYWORDS):
            return True
        toks = set(self._tokens(lowered))
        # lots of meta tokens is also a sign
        if len(toks & self._META_TOKENS) >= 3:
            return True
        return False

    def _classify_from_data(self, rows) -> Optional[str]:
        """Deterministic precedence: Adjustments > Distributions > Capital Calls."""
        if not rows or not isinstance(rows, list):
            return None

        header = rows[0] if rows and isinstance(rows[0], list) else []
        header_text = " ".join(str(h) for h in header)
        header_toks = set(self._tokens(header_text))

        body = rows[1:] if len(rows) > 1 else []
        body_text = " ".join(" ".join(str(c) for c in r) for r in body)
        body_toks = set(self._tokens(body_text))

        # 1) Adjustments (any appearance wins)
        if (
            "adjustment" in header_toks or "adjustments" in header_toks
            or any(tok.startswith("adjust") for tok in body_toks)
            or "recalled" in body_toks or "recallable" in body_toks
        ):
            return "Adjustments"

        # 2) Distributions
        if (
            "distribution" in header_toks or "distributions" in header_toks
            or "distribution" in body_toks or "distributions" in body_toks
            or "income" in body_toks or "dividend" in body_toks
            or ("return" in body_toks and "capital" in body_toks)  # return of capital
        ):
            return "Distributions"

        # 3) Capital Calls
        if (
            ({"call","number"}.issubset(header_toks))
            or ({"capital","call"}.issubset(header_toks))
            or ("call" in body_toks or "contribution" in body_toks or "capital" in body_toks)
        ):
            return "Capital Calls"

        return None

    def _reconcile_heading(self, heading_norm: Optional[str], heading_raw: Optional[str], rows) -> Optional[str]:
        """No scoring: if raw is missing/invalid or conflicts, use deterministic content classification."""
        # If raw looks like column headers or fund metadata, ignore it
        if heading_raw and (self._is_headerish_line(heading_raw) or self._is_metadata_line(heading_raw)):
            heading_norm = None

        content_label = self._classify_from_data(rows)

        # Prefer content when raw is absent/invalid
        if heading_norm is None:
            return content_label

        # If both exist but conflict, use precedence: let content override
        if content_label and content_label != heading_norm:
            return content_label

        return heading_norm

    def _normalize_heading(self, text: Optional[str]) -> Optional[str]:
        if not text:
            return None
        t = re.sub(r"[^\w\s]", " ", text.strip().lower())
        tokens = set(re.findall(r"[a-z]+", t))
        if "capital" in tokens and ("call" in tokens or "calls" in tokens):
            return "Capital Calls"
        if "distribution" in tokens or "distributions" in tokens:
            return "Distributions"
        if any(tok.startswith("adjust") for tok in tokens):
            return "Adjustments"
        if "return" in tokens or "income" in tokens or "dividend" in tokens:
            return "Distributions"
        return None