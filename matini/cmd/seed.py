"""Seed sample data: three LLMs whose assessment profiles are written to hit rubric level 1, 3 and 5.

Usage:  ./scripts/seed [--reset] [--base-url URL] [--model TAG] [--mongodb-uri URI]

What is seeded (nothing else, in particular no assessment reports and no probe answers):
  - one LLM per level ("[ตัวอย่าง] ระดับ 1/3/5") with a system context and, for the GOVERN / MAP /
    MANAGE criteria, a self-declared status, notes and evidence (documents, a link, a text excerpt);
  - the evidence documents themselves (matini/seed_data/level*/, PDF and Markdown) stored as
    EvidenceFile, exactly as if they had been uploaded on the Admin page;
  - one judge LLM, so a run does not need the self-evaluation setup.
MEASURE criteria (me1-me4) are scored from real probe answers, so they are left to the run.

The documents are written against the rubrics in api/services/nist_rmf.py: each one says what the
level-N rubric text of its criterion describes, no more and no less. The per-criterion text the judge
sees is capped (MAX_EVIDENCE_CHARS), so every document is kept under that cap.
The PDFs were rendered from matini/seed_data/_pdf_src/ (Markdown) with Chromium; their stored text is
taken from that Markdown because pypdf drops Thai tone marks and upper vowels.

Running again skips levels that already exist; --reset soft-deletes them (and their files) first.
"""
import argparse
import asyncio
import datetime
import mimetypes
import pathlib
from types import SimpleNamespace
from typing import Dict, List, Optional

from beanie import PydanticObjectId

from matini import models, schemas
from matini.api.core.config import settings
from matini.api.services import evidence_text
from matini.api.services.nist_rmf import get_criteria

DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "seed_data"
PDF_SOURCE_DIR = DATA_DIR / "_pdf_src"
NAME_PREFIX = "[ตัวอย่าง]"
DEFAULT_BASE_URL = "http://172.30.222.240:11434"
DEFAULT_MODEL = "llama3.2:3b"
PARAMETER_SIZE_B = 3.2  # llama3.2:3b


def doc(file: str, title: str, date: str, excerpt: str = "") -> dict:
    return {"kind": "document", "file": file, "title": title, "doc_date": date, "excerpt": excerpt}


def link(url: str, title: str, date: str) -> dict:
    return {"kind": "link", "url": url, "title": title, "doc_date": date}


def text(title: str, excerpt: str, date: str) -> dict:
    return {"kind": "text", "title": title, "excerpt": excerpt, "doc_date": date}


def entry(status: str, notes: str, *items: dict) -> dict:
    return {"status": status, "notes": notes, "items": list(items)}


# ---------- level 5: every rubric text of level 5 is backed by a document ----------

LEVEL_5 = {
    "key": "level5",
    "score": 5,
    "description": (
        "ข้อมูลตัวอย่างระดับ 5 — แชทบอทบริการนักศึกษาที่มีธรรมาภิบาลครบถ้วน "
        "(นโยบาย ผู้รับผิดชอบ ประเมินผลกระทบ ทะเบียนความเสี่ยง และบันทึกติดตามพร้อมหลักฐาน)"
    ),
    "context": {
        "intended_use": (
            "ตอบคำถามเบื้องต้นของนักศึกษาเรื่องปฏิทินการศึกษา การลงทะเบียน ทุนการศึกษา และระเบียบของมหาวิทยาลัยตัวอย่าง "
            "เป็นข้อมูลประกอบเท่านั้น ไม่ใช่การตัดสินใจแทนเจ้าหน้าที่"
        ),
        "target_users": "นักศึกษาปริญญาตรี/บัณฑิตศึกษา (อายุ 18 ปีขึ้นไป) และบุคลากรสายสนับสนุนที่ยืนยันตัวตนผ่านพอร์ทัลนักศึกษา",
        "out_of_scope_use": (
            "ห้ามใช้ให้คำปรึกษาทางการแพทย์ กฎหมาย หรือการเงินส่วนบุคคล ห้ามใช้ตัดสินผลการเรียน การรับเข้า ทุน หรือวินัย "
            "และห้ามป้อนข้อมูลส่วนบุคคลที่อ่อนไหว"
        ),
        "data_sources": (
            "โมเดล llama3.2:3b (Meta ผ่าน Ollama) ไม่ได้ fine-tune; ความรู้เฉพาะมหาวิทยาลัยมาจากเอกสาร FAQ 42 ฉบับที่กองบริการการศึกษารับรอง; "
            "ไม่นำบทสนทนาไปฝึกโมเดลและลบที่ 30 วัน"
        ),
        "deployment_context": (
            "รันบนเซิร์ฟเวอร์ภายในมหาวิทยาลัยผ่าน Ollama (ข้อมูลไม่ออกนอกเครือข่าย) เปิดผ่านพอร์ทัลนักศึกษา "
            "มีแบนเนอร์บอกขอบเขตและปุ่มส่งต่อเจ้าหน้าที่"
        ),
        "notes": "คณะกรรมการกำกับดูแล AI ทบทวนระบบทุก 6 เดือน",
    },
    "criteria": {
        "g1": entry(
            "implemented",
            "นโยบายฉบับที่ 2 ประกาศใช้และเผยแพร่แล้ว ทบทวนมาแล้ว 2 ครั้ง",
            doc("g1-นโยบายการใช้-AI.pdf", "นโยบายการใช้ AI อย่างมีจริยธรรม ฉบับที่ 2", "2026-09-15"),
            link("https://example.com/ai-governance", "หน้าธรรมาภิบาล AI ของมหาวิทยาลัย", "2026-09-15"),
        ),
        "g2": entry(
            "implemented",
            "มี RACI ขั้นตอนรับมือเหตุ ช่องทางร้องเรียน และ decision log",
            doc("g2-ผู้รับผิดชอบและ-RACI.md", "RACI และขั้นตอนรับมือเหตุ ฉบับที่ 3", "2026-09-20"),
        ),
        "g3": entry(
            "implemented",
            "คณะกรรมการมีตัวแทนหลายกลุ่ม รับฟังทุกภาคเรียน และติดตามผลข้อเสนอ",
            doc("g3-การมีส่วนร่วมของผู้มีส่วนได้ส่วนเสีย.md", "แนวทางการมีส่วนร่วมและความหลากหลาย", "2026-09-01"),
        ),
        "m1": entry(
            "implemented",
            "ระบุวัตถุประสงค์ ผู้ใช้ นอกขอบเขต แจ้งผู้ใช้ และมีมาตรการป้องกัน",
            doc("m1-ขอบเขตและบริบทการใช้งาน.md", "Intended Use Statement ฉบับที่ 2", "2026-01-15"),
        ),
        "m2": entry(
            "implemented",
            "บันทึก data provenance และ PIA ทบทวนแล้ว 2 ครั้ง",
            doc("m2-Data-Provenance-และ-PIA.pdf", "Data Provenance & Privacy Impact Assessment", "2026-09-01"),
        ),
        "m3": entry(
            "implemented",
            "ประเมิน 7 มิติก่อนใช้งานจริง ติดตามรายเดือน และนำผลไปลดผลกระทบแล้ว",
            doc("m3-ประเมินผลกระทบต่อกลุ่มบุคคล.md", "รายงานประเมินผลกระทบต่อกลุ่มบุคคล", "2026-08-15"),
        ),
        "ma1": entry(
            "implemented",
            "มีเกณฑ์จัดลำดับ วิธีตอบสนอง ผู้รับผิดชอบ กำหนดเวลา และเหตุผลครบทุกรายการ",
            doc("ma1-การตอบสนองและจัดลำดับความเสี่ยง.md", "ขั้นตอนตอบสนองความเสี่ยงและทะเบียนความเสี่ยง", "2026-07-10"),
        ),
        "ma2": entry(
            "implemented",
            "ติดตามรายไตรมาส ทบทวนซ้ำเมื่อโมเดล/ระเบียบเปลี่ยน พร้อมหลักฐานทุกรอบ",
            doc("ma2-บันทึกติดตามความเสี่ยง.pdf", "Risk Monitoring Log ไตรมาส 1-3/2569", "2026-09-26"),
            text(
                "ผลตรวจสอบภายใน",
                "ฝ่ายตรวจสอบภายในสุ่มตรวจบันทึกทั้ง 3 รอบเมื่อ 30 ก.ย. 2569 พบหลักฐานครบทุกรอบ ไม่มีข้อบกพร่อง",
                "2026-09-30",
            ),
        ),
    },
}

# ---------- level 3: each document stops exactly where the level-3 rubric text says it stops ----------

LEVEL_3 = {
    "key": "level3",
    "score": 3,
    "description": (
        "ข้อมูลตัวอย่างระดับ 3 — แชทบอทบริการนักศึกษาที่ดำเนินการบางส่วน "
        "(มีร่างนโยบายแต่ยังไม่เผยแพร่ กำหนดบทบาทบางส่วน ประเมินบางมิติ บันทึกความเสี่ยงแต่ไม่ติดตามต่อ)"
    ),
    "context": {
        "intended_use": "ตอบคำถามนักศึกษาเรื่องปฏิทินการศึกษา การลงทะเบียน และทุนการศึกษา",
        "target_users": "นักศึกษาปริญญาตรีของคณะวิศวกรรมศาสตร์ มหาวิทยาลัยตัวอย่าง",
        "out_of_scope_use": "",
        "data_sources": "โมเดล llama3.2:3b ผ่าน Ollama และเอกสาร FAQ 18 ฉบับของกองบริการการศึกษา",
        "deployment_context": "รันบนเครื่องภายในคณะ เปิดผ่านเว็บภายในคณะ",
        "notes": "โครงการระดับคณะ ทีมพัฒนา 2 คน",
    },
    "criteria": {
        "g1": entry(
            "partial",
            "มีร่างนโยบายแต่ยังไม่ประกาศใช้และไม่ได้เผยแพร่",
            doc("g1-ร่างนโยบายการใช้-AI.pdf", "ร่างนโยบายการใช้ AI v0.3", "2026-05-04"),
        ),
        "g2": entry(
            "partial",
            "กำหนดบทบาทผู้พัฒนาและผู้ดูแลเครื่อง แต่ยังไม่มีผู้รับผิดชอบต่อผลลัพธ์",
            doc("g2-รายชื่อทีมพัฒนา.md", "บทบาทในทีมพัฒนา", "2026-06-10"),
        ),
        "g3": entry(
            "partial",
            "เคยรับฟังนักศึกษาเพียงบางส่วน ไม่ได้ทำต่อเนื่อง",
            text(
                "แบบสอบถามนักศึกษา",
                "ก.พ. 2569 ส่งแบบสอบถามถึงนักศึกษา 2 คนจากคณะเดียวกัน (ทีมพัฒนาเลือกเอง) ไม่ได้ทำซ้ำและไม่ได้สรุปผล",
                "2026-02-20",
            ),
        ),
        "m1": entry(
            "partial",
            "ระบุวัตถุประสงค์และกลุ่มผู้ใช้ แต่ยังไม่ระบุการใช้งานนอกขอบเขต",
            doc("m1-สรุปโครงการ.md", "สรุปโครงการ", "2026-06-15"),
        ),
        "m2": entry(
            "partial",
            "ระบุแหล่งข้อมูลหลักแล้ว แต่ยังไม่ประเมินบุคคลที่สามและความเป็นส่วนตัว",
            doc("m2-รายการแหล่งข้อมูล.md", "รายการแหล่งข้อมูล", "2026-06-15"),
        ),
        "m3": entry(
            "partial",
            "ทดสอบบางมิติก่อนใช้งาน ไม่เป็นระบบ",
            doc("m3-ผลทดสอบเบื้องต้น.md", "ผลทดสอบเบื้องต้นก่อนเปิดใช้", "2026-07-20"),
        ),
        "ma1": entry(
            "partial",
            "จัดลำดับความสำคัญของปัญหาแล้ว แต่ยังไม่เลือกวิธีตอบสนอง",
            doc("ma1-ปัญหาที่พบและลำดับความสำคัญ.md", "ปัญหาที่พบจากการทดสอบ", "2026-07-25"),
        ),
        "ma2": entry(
            "partial",
            "มีบันทึกความเสี่ยงและมาตรการ แต่ไม่ได้ติดตามต่อเนื่อง",
            doc("ma2-risk-log.md", "บันทึกความเสี่ยงและมาตรการ", "2026-03-20"),
        ),
    },
}

# ---------- level 1: nothing in place ----------

LEVEL_1 = {
    "key": "level1",
    "score": 1,
    "description": "ข้อมูลตัวอย่างระดับ 1 — โปรเจกต์ทดลองที่ยังไม่มีเอกสารหรือกระบวนการกำกับดูแลใด ๆ",
    "context": {
        "intended_use": "",
        "target_users": "",
        "out_of_scope_use": "",
        "data_sources": "",
        "deployment_context": "",
        "notes": "โปรเจกต์ทดลองของนักศึกษา ยังไม่มีเอกสารประกอบ",
    },
    "criteria": {
        "g1": entry("not_implemented", "ยังไม่มีนโยบายหรือแนวปฏิบัติด้านจริยธรรม AI"),
        "g2": entry("not_implemented", "ยังไม่ได้กำหนดบทบาทหรือผู้รับผิดชอบ"),
        "g3": entry("not_implemented", "ยังไม่ได้พิจารณาผู้มีส่วนได้ส่วนเสีย"),
        "m1": entry(
            "not_implemented",
            "มีเพียง README ทางเทคนิคสำหรับติดตั้ง ไม่ได้ระบุวัตถุประสงค์ กลุ่มผู้ใช้ หรือข้อจำกัด",
            doc("README.md", "README ของโปรเจกต์", "2026-09-01"),
        ),
        "m2": entry("not_implemented", "ไม่ทราบแหล่งที่มาของข้อมูลและยังไม่ได้ประเมินความเป็นส่วนตัว"),
        "m3": entry("not_implemented", "ยังไม่ได้ประเมินผลกระทบต่อกลุ่มบุคคลใด"),
        "ma1": entry("not_implemented", "ยังไม่มีกระบวนการตอบสนองต่อความเสี่ยง"),
        "ma2": entry("not_implemented", "ยังไม่มีการบันทึกหรือติดตามความเสี่ยง"),
    },
}

LEVELS = [LEVEL_1, LEVEL_3, LEVEL_5]
JUDGE_NAME = f"{NAME_PREFIX} Judge"


def level_name(level: dict) -> str:
    return f"{NAME_PREFIX} ระดับ {level['score']}"


def read_bytes(level: dict, filename: str) -> bytes:
    return (DATA_DIR / level["key"] / filename).read_bytes()


def extracted_text(level: dict, filename: str, content_type: str, data: bytes):
    """Text + error as stored on the EvidenceFile (see the module docstring for the PDF case)."""
    if filename.lower().endswith(".pdf"):
        source = PDF_SOURCE_DIR / level["key"] / (pathlib.Path(filename).stem + ".md")
        return source.read_text(encoding="utf-8").strip()[: models.evidence.MAX_EXTRACTED_CHARS], None
    return evidence_text.extract_text(filename, content_type, data)


def build_profile(level: dict, file_ids: Dict[str, PydanticObjectId]) -> schemas.evidence.AssessmentProfile:
    criteria = {}
    for criterion_id, declared in level["criteria"].items():
        items = []
        for raw in declared["items"]:
            item = {k: v for k, v in raw.items() if k != "file"}
            if raw["kind"] == "document":
                item["file_id"] = file_ids[raw["file"]]
            if item.get("doc_date"):
                item["doc_date"] = datetime.date.fromisoformat(item["doc_date"])
            items.append(schemas.evidence.EvidenceItem(**item))
        criteria[criterion_id] = schemas.evidence.CriterionEvidence(
            status=declared["status"], notes=declared["notes"], items=items
        )
    return schemas.evidence.AssessmentProfile(
        system_context=schemas.evidence.SystemContext(**level["context"]),
        criteria=criteria,
        updated_date=datetime.datetime.now(),
    )


async def find_existing(name: str) -> List[models.LLM]:
    return await models.LLM.find({"name": name, "status": {"$ne": "delete"}}).to_list()


async def soft_delete(llm: models.LLM) -> None:
    for file in await models.EvidenceFile.find({"llm_id": llm.id, "status": {"$ne": "delete"}}).to_list():
        file.status = "delete"
        await file.save()
    llm.status = "delete"
    llm.updated_date = datetime.datetime.now()
    await llm.save()


async def seed_level(level: dict, base_url: str, model: str) -> models.LLM:
    llm = models.LLM(
        name=level_name(level),
        base_url=base_url,
        model_name=model,
        description=level["description"],
        parameter_size_b=PARAMETER_SIZE_B,
    )
    await llm.insert()

    file_ids: Dict[str, PydanticObjectId] = {}
    for filename in sorted({i["file"] for d in level["criteria"].values() for i in d["items"] if i["kind"] == "document"}):
        data = read_bytes(level, filename)
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        if filename.endswith(".md"):
            content_type = "text/markdown"
        body, error = extracted_text(level, filename, content_type, data)
        file = models.EvidenceFile(
            llm_id=llm.id,
            filename=filename,
            content_type=content_type,
            size=len(data),
            data=data,
            extracted_text=body,
            extract_error=error,
        )
        await file.insert()
        file_ids[filename] = file.id

    llm.assessment_profile = build_profile(level, file_ids)
    await llm.save()
    return llm


async def seed_all(base_url: str, model: str, reset: bool) -> List[str]:
    """Create whatever is missing (Beanie must already be initialised). Returns the names it created."""
    created = []
    wanted = [(level_name(level), level) for level in LEVELS] + [(JUDGE_NAME, None)]
    for name, level in wanted:
        existing = await find_existing(name)
        if existing and not reset:
            print(f"ข้าม  {name} (มีอยู่แล้ว ใช้ --reset เพื่อสร้างใหม่)")
            continue
        for llm in existing:
            await soft_delete(llm)
        if level is None:
            llm = models.LLM(
                name=name,
                base_url=base_url,
                model_name=model,
                description="ผู้ตัดสิน (judge) สำหรับรันการประเมินของข้อมูลตัวอย่าง",
                parameter_size_b=PARAMETER_SIZE_B,
            )
            await llm.insert()
            print(f"สร้าง {name}  id={llm.id}")
        else:
            llm = await seed_level(level, base_url, model)
            files = sum(1 for d in level["criteria"].values() for i in d["items"] if i["kind"] == "document")
            print(f"สร้าง {name}  id={llm.id}  หลักฐาน {files} ไฟล์")
        created.append(name)
    return created


async def seed(base_url: str, model: str, reset: bool, mongodb_uri: Optional[str]) -> None:
    await models.beanie_client.init_beanie(SimpleNamespace(mongodb_uri=mongodb_uri or settings.mongodb_uri))
    try:
        await seed_all(base_url, model, reset)
    finally:
        await models.beanie_client.client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"Ollama base URL ของ LLM ตัวอย่าง (ค่าเริ่มต้น {DEFAULT_BASE_URL})")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model tag (ค่าเริ่มต้น {DEFAULT_MODEL})")
    parser.add_argument("--reset", action="store_true", help="ลบ (soft delete) ข้อมูลตัวอย่างเดิมแล้วสร้างใหม่")
    parser.add_argument("--mongodb-uri", default=None, help="แทนที่ MONGODB_URI จาก .env")
    args = parser.parse_args()
    asyncio.run(seed(args.base_url, args.model, args.reset, args.mongodb_uri))


if __name__ == "__main__":
    main()
