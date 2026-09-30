# คู่มือ: POC การประเมิน AI ตาม NIST AI RMF ด้วย Local LLM (Ollama)

เอกสารนี้อธิบายวิธีตั้งค่าและใช้งานฟีเจอร์ **NIST AI RMF Ethical Assessment (POC)**
ที่เพิ่มเข้าไปในโปรเจกต์ `matini` โดยใช้ local LLM ผ่าน **Ollama** เป็นทั้ง

1. **ผู้ถูกประเมิน (subject)** — LLM ที่เพิ่มไว้ในหน้า **Admin** (`/admin/`)
2. **ผู้ประเมิน (LLM-as-judge)** — ให้คะแนนแต่ละเกณฑ์ตามกรอบ NIST AI RMF 1.0

เนื่องจากเครื่องนี้ทรัพยากรไม่พอสำหรับรัน local LLM คู่มือนี้เขียนแยกเป็น
**เครื่อง A** (เครื่องที่รัน `matini` — API + Web ตามเดิม) และ
**เครื่อง B** (เครื่องที่จะรัน Ollama จริง) เพื่อให้ย้ายไปรันอีกเครื่องได้ทันที

---

## 0. ภาพรวมสถาปัตยกรรม

| ส่วน | ไฟล์ | หน้าที่ |
|---|---|---|
| Config | `api/core/config.py` | `MONGODB_URI`, `OLLAMA_BASE_URL`, `OLLAMA_JUDGE_MODEL`, `OLLAMA_TIMEOUT_S` |
| Database | `models/` (Beanie) | collection `llms`, `conversations`, `assessments` |
| Schemas | `schemas/` | schema ของ LLM, บทสนทนา, เกณฑ์ประเมิน/รายงาน/สถานะงาน |
| LLM client | `api/services/local_llm.py` | เรียก Ollama `/api/chat` (แบบ sync สำหรับประเมิน, แบบ async stream สำหรับแชท) |
| Assessment engine | `api/services/nist_rmf.py`, `api/services/assessment.py` | เกณฑ์ 12 ข้อ + งานประเมินเบื้องหลังพร้อมรายงานความคืบหน้า |
| Routers | `api/routers/{llms,chat,assessment}.py` | `/api/llms`, `/api/conversations`, `/api/assessment` |
| Web | `web/views/{chat,admin,assessment}.py` + `web/templates/` + `web/static/brython/` | หน้าแชท (`/`), หน้า Admin (`/admin/`), หน้าประเมิน (`/assessment/<llm_id>`) |

ผลการประเมินและประวัติแชทเก็บใน **MongoDB** ส่วนสถานะของงานประเมินที่กำลังรันอยู่ (สำหรับ progress bar)
เก็บใน memory ของ API process — ถ้ารีสตาร์ท API ระหว่างรัน งานนั้นจะหายและต้องกดรันใหม่

> ระบบ Guardrail (`api/services/guardrails.py`) ถูกปิดไว้ — ไม่ได้ต่อเข้ากับแชทแล้ว แต่ยังเก็บโค้ดไว้ใช้ภายหลัง

---

## 1. เครื่อง B — ติดตั้งและเปิด Ollama ให้เข้าถึงจากเครื่อง A ได้

1. ติดตั้ง Ollama: https://ollama.com/download (Linux/macOS/Windows รองรับหมด)
2. ดึงโมเดลที่จะใช้ (แนะนำเริ่มจากโมเดลเล็กให้ POC เร็ว แล้วค่อยขยับขึ้น):
   ```bash
   ollama pull llama3.2:3b      # เร็ว เบา เหมาะกับ POC เริ่มต้น
   # หรือ
   ollama pull llama3.1         # ใหญ่กว่า คุณภาพดีกว่า ถ้าเครื่อง B แรงพอ
   ```
   > **ข้อควรระวังเชิงวิธีวิจัย**: การใช้โมเดลตัวเดียวกันเป็นทั้ง subject และ judge
   > มีความเสี่ยงเรื่อง self-evaluation bias (โมเดลตัดสินตัวเองอาจหย่อนยาน/ไม่คงเส้นคงวา)
   > สำหรับ POC ใช้ตัวเดียวกันได้เพื่อพิสูจน์ว่า pipeline ทำงานครบวงจร แต่สำหรับงานวิจัยจริง
   > ควรใช้โมเดลที่ต่างกัน (เช่น ดึงโมเดลที่ใหญ่/แข็งแรงกว่ามาเป็น judge โดยเฉพาะ) เช่น
   > ```bash
   > ollama pull qwen2.5:14b   # ใช้เป็น judge (ตั้งเป็น OLLAMA_JUDGE_MODEL)
   > ```
3. เปิดให้ Ollama รับ connection จากเครื่องอื่นในวง LAN (ค่าเริ่มต้น bind แค่ 127.0.0.1):
   - Linux (systemd): แก้ `/etc/systemd/system/ollama.service.d/override.conf`
     ```ini
     [Service]
     Environment="OLLAMA_HOST=0.0.0.0:11434"
     ```
     แล้ว `sudo systemctl daemon-reload && sudo systemctl restart ollama`
   - หรือรันตรง ๆ ชั่วคราว: `OLLAMA_HOST=0.0.0.0:11434 ollama serve`
   - macOS/Windows (Ollama app): ตั้งค่า environment variable `OLLAMA_HOST=0.0.0.0:11434` ก่อนเปิดแอป
4. เปิด firewall พอร์ต `11434` ให้เครื่อง A เข้าถึงได้ (เช่น `sudo ufw allow 11434/tcp` บน Linux)
5. หา IP ของเครื่อง B ในวง LAN (เช่น `ip addr` / `ifconfig`) — สมมติได้ `192.168.1.50`
6. ทดสอบจากเครื่อง A ว่ายิงถึง:
   ```bash
   curl http://192.168.1.50:11434/api/tags
   ```
   ถ้าได้ JSON รายชื่อโมเดลกลับมา แปลว่าเชื่อมต่อได้แล้ว

---

## 2. เครื่อง A — ตั้งค่า `matini` ให้ชี้ไปที่เครื่อง B

หาไฟล์ `.env` ของโปรเจกต์ (อยู่ที่ root ของ repo, ระดับเดียวกับ `pyproject.toml`) ถ้ายังไม่มีให้คัดลอกจาก
`.env.example` แล้วเพิ่ม/แก้ไข:

```dotenv
# MongoDB (ชื่อ database อยู่ท้าย URI)
MONGODB_URI="mongodb://localhost:27017/matinidb"

# Ollama บนเครื่อง B — ใช้เป็นค่า Base URL เริ่มต้นเมื่อเพิ่ม LLM ในหน้า Admin แล้วเว้นช่องนี้ว่าง
# และใช้เป็น endpoint ของ "ผู้ตัดสิน" ในการประเมิน
OLLAMA_BASE_URL=http://192.168.1.50:11434

# โมเดลที่ใช้เป็น "ผู้ตัดสิน" (ให้คะแนนแต่ละเกณฑ์)
OLLAMA_JUDGE_MODEL=llama3.2:3b

# local LLM บนเครื่องที่ไม่แรงมากอาจตอบช้า ปรับเพิ่มได้ถ้า timeout บ่อย
OLLAMA_TIMEOUT_S=120
```

> ค่าเริ่มต้นในโค้ด (`api/core/config.py`) ชี้ที่ `http://127.0.0.1:11434` — ถ้าไม่ตั้งค่า `.env`
> ระบบจะพยายามต่อ Ollama บนเครื่อง A เอง

ต้องมี MongoDB รันอยู่ (Beanie ต้องใช้ Python < 3.14 — โปรเจกต์กำหนด `^3.12 || ^3.13`) เช่นรันชั่วคราวด้วย Docker:
```bash
docker run -d --name matini-mongo -p 27017:27017 mongo:7
```

---

## 3. Build Tailwind ใหม่ (จำเป็น เพราะมีการเพิ่ม template ใหม่)

โปรเจกต์นี้ใช้ Tailwind CSS v4 CLI คอมไพล์จาก template จริง (JIT) — ต้องรันคำสั่งนี้ใหม่
ทุกครั้งที่เพิ่ม/แก้ template เพื่อให้ class ที่ใช้ในหน้าประเมินใหม่ถูกคอมไพล์เข้า `app.css`:

```bash
cd matini/web/static
npm install          # ครั้งแรกเท่านั้น ถ้ายังไม่เคยรัน
npm run tw           # build ครั้งเดียว
# หรือระหว่างพัฒนา:
npm run tw:watch
```

---

## 4. รันระบบ

```bash
# terminal 1: FastAPI backend (ต้องมี MongoDB รันอยู่)
poetry run python -m matini.cmd.api

# terminal 2: Flask frontend
poetry run python -m matini.cmd.web
```
(หรือ `./scripts/run-api` / `./scripts/run-web`)

เปิดเบราว์เซอร์ไปที่ `http://127.0.0.1:8080`:

1. ไปหน้า **Admin** (`/admin/`) → เพิ่ม LLM (ชื่อ, Ollama model tag เช่น `llama3.2:3b`, Base URL เว้นว่างได้) →
   กดปุ่มทดสอบการเชื่อมต่อ
2. กลับหน้าแรกเพื่อแชท — เลือกโมเดลจาก dropdown ใต้ช่องพิมพ์
3. หน้าประเมิน: กดลิงก์ **"ประเมินโมเดลนี้ (NIST AI RMF)"** ที่แถบด้านซ้ายของหน้าแชท หรือไอคอนในตาราง Admin

---

## 5. วิธีใช้งานหน้าประเมิน

1. (ไม่บังคับ) กรอก **บริบทของระบบ** — อธิบายว่ากำลังประเมินอะไร ใช้ทำอะไร
2. ติ๊ก **"ทดสอบพฤติกรรมจริงของโมเดลอัตโนมัติสำหรับเกณฑ์ในหมวด MEASURE"** ไว้ (ค่าเริ่มต้นติ๊กอยู่แล้ว)
   ระบบจะยิง probe prompt 4 ข้อ (bias / privacy / explainability / safety) ไปที่ LLM ที่เลือกผ่าน Ollama
3. (ไม่บังคับ) กรอกหลักฐาน/บันทึกของคุณเองในแต่ละเกณฑ์ (12 ข้อ แบ่งตาม GOVERN/MAP/MEASURE/MANAGE)
   — ยิ่งกรอกเยอะ ผลตัดสินของ LLM judge ยิ่งมีหลักฐานอ้างอิงมากขึ้น ไม่ใช่เดาจากชื่อโมเดลอย่างเดียว
4. กด **"Run NIST AI RMF Assessment"** — งานรันเบื้องหลัง และมี **progress bar** ด้านบนแสดงขั้นที่ทำอยู่
   (`ขั้นที่ทำแล้ว/ทั้งหมด`, เปอร์เซ็นต์, ชื่อเกณฑ์ที่กำลังทดสอบ/ให้คะแนน) รอบแรกอาจใช้เวลาหลายนาทีถ้าเครื่อง B
   ไม่แรงมาก ปิดหน้าแล้วกลับมาเปิดใหม่ progress bar จะกลับมาแสดงต่อ
5. เมื่อเสร็จ หน้าจะโหลดใหม่และแสดงผลทางซ้าย: คะแนนเฉลี่ยต่อฟังก์ชัน (GOVERN/MAP/MEASURE/MANAGE),
   overall risk level, และรายละเอียดต่อเกณฑ์ (คะแนน, risk level, เหตุผลจาก judge, transcript ของ probe ถ้ามี)
6. รันซ้ำได้เรื่อย ๆ — ระบบเก็บประวัติทุกรอบไว้ใน MongoDB (`GET /api/assessment/{llm_id}/history`)

---

## 6. API endpoints (ดูที่ `http://127.0.0.1:8000/docs` ได้ด้วย)

| Method | Path | หน้าที่ |
|---|---|---|
| GET | `/api/llms` | รายการ LLM ที่เปิดใช้งาน (`?status=all` รวมที่ปิดอยู่) |
| POST | `/api/llms/create` | เพิ่ม LLM |
| PUT | `/api/llms/update/{llm_id}` | แก้ไข/เปิด-ปิด LLM |
| DELETE | `/api/llms/delete/{llm_id}` | ลบ (soft delete) |
| POST | `/api/llms/{llm_id}/test` | ทดสอบการเชื่อมต่อ Ollama |
| GET/POST | `/api/conversations`, `/api/conversations/create` | รายการ/สร้างบทสนทนา |
| GET/DELETE | `/api/conversations/{id}`, `/api/conversations/delete/{id}` | อ่าน/ลบบทสนทนา |
| POST | `/api/conversations/{id}/messages` | ส่งข้อความ — ตอบกลับเป็น NDJSON stream (`{"delta"}` ... `{"done"}` หรือ `{"error"}`) |
| GET | `/api/assessment/criteria` | รายการเกณฑ์ประเมินทั้งหมด (static) |
| POST | `/api/assessment/{llm_id}/run` | เริ่มการประเมินเบื้องหลัง — คืน `job_id` ทันที |
| GET | `/api/assessment/jobs/{job_id}` | ความคืบหน้า: `status`, `step`, `total`, `label`, `report_id` |
| GET | `/api/assessment/{llm_id}` | ผลล่าสุด |
| GET | `/api/assessment/{llm_id}/history` | ประวัติทุกรอบ |

---

## 7. Troubleshooting

- **"เชื่อมต่อ Ollama ไม่สำเร็จ..."** → เครื่อง B ยังไม่ได้รัน `ollama serve`, พอร์ต/ไฟร์วอลล์ไม่เปิด,
  หรือ `OLLAMA_BASE_URL` ผิด — ทดสอบด้วย `curl http://<ip เครื่อง B>:11434/api/tags` จากเครื่อง A
- **ตอบช้า/timeout** → เพิ่ม `OLLAMA_TIMEOUT_S` ใน `.env`, หรือเปลี่ยนไปใช้โมเดลเล็กลง (`llama3.2:3b`)
- **"ผลลัพธ์จาก judge model ไม่ใช่ JSON ที่แปลงได้"** → โมเดลเล็กบางตัวไม่ทำตาม instruction เรื่อง JSON
  ดีนัก ลองโมเดลอื่น หรือดู field `judge_error` ในผลลัพธ์แต่ละเกณฑ์เพื่อดู raw response
- **หน้าเว็บไม่มีสไตล์ / ปุ่มไม่มีสี** → ลืม build Tailwind (ขั้นตอนที่ 3)
- **API ไม่ขึ้น / error ตอนสตาร์ทเรื่อง Mongo** → ตรวจสอบว่า MongoDB รันอยู่และ `MONGODB_URI` ถูกต้อง
- **`beanie` ติดตั้งไม่ได้** → Beanie 2.x รองรับ Python < 3.14 ใช้ Python 3.12/3.13
- **dropdown โมเดลในหน้าแชทว่าง** → ยังไม่ได้เพิ่ม LLM ที่หน้า Admin (หรือถูกปิดใช้งานอยู่)
- **หน้าเว็บเรียก API ไม่ได้** → ตรวจสอบว่า FastAPI backend รันอยู่ และ `API_URL` ใน `.env` ตรงกับที่ API ฟังอยู่
  (เบราว์เซอร์เรียก API ตรง ๆ จากหน้าแชท/Admin)

---

## 8. ข้อจำกัดของ POC นี้ (สำหรับเขียนอภิปรายในงานวิจัย)

- **เกณฑ์ 12 ข้อเป็นชุดย่อยตัวแทน** ไม่ใช่ NIST AI RMF Core ฉบับเต็ม (~72 subcategories) —
  ก่อนเก็บข้อมูลจริงควรขยายชุดเกณฑ์และตรวจสอบความตรงเชิงเนื้อหาโดยผู้เชี่ยวชาญ (IOC) ตาม roadmap ข้อ D
- **self-evaluation bias** ถ้าใช้โมเดลเดียวกันเป็นทั้ง subject และ judge (ดูหัวข้อ 1)
- **หน้า Admin ยังไม่มีระบบยืนยันตัวตน** และ CORS เปิดกว้าง — ใช้ในเครือข่ายที่เชื่อถือได้เท่านั้น
- **สถานะงานประเมินที่กำลังรันเก็บใน memory** — รีสตาร์ท API ระหว่างรัน งานนั้นจะหาย (ผลที่เสร็จแล้วเก็บใน MongoDB)
- **probe prompt มีแค่ 1 ข้อ/เกณฑ์** สำหรับหมวด MEASURE — ความน่าเชื่อถือ (reliability) ของผลจะต่ำ
  ถ้าทดสอบครั้งเดียว ควรรันซ้ำหลายรอบ/สุ่ม prompt หลายแบบต่อมิติก่อนสรุปผลในบทความ
- **Ollama เป็น provider เดียวที่รองรับตอนนี้** — การเพิ่ม provider อื่นต้องเพิ่ม client ใน `api/services/`
