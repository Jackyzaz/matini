# คู่มือ: POC การประเมิน AI ตาม NIST AI RMF ด้วย Local LLM (Ollama)

เอกสารนี้อธิบายวิธีตั้งค่าและใช้งานฟีเจอร์ **NIST AI RMF Ethical Assessment (POC)**
ที่เพิ่มเข้าไปในโปรเจกต์ `matini` โดยใช้ local LLM ผ่าน **Ollama** เป็นทั้ง

1. **ผู้ถูกประเมิน (subject)** — โมเดลใน registry ชื่อ `ollama-local-poc`
2. **ผู้ประเมิน (LLM-as-judge)** — ให้คะแนนแต่ละเกณฑ์ตามกรอบ NIST AI RMF 1.0

เนื่องจากเครื่องนี้ทรัพยากรไม่พอสำหรับรัน local LLM คู่มือนี้เขียนแยกเป็น
**เครื่อง A** (เครื่องที่รัน `matini` — API + Web ตามเดิม) และ
**เครื่อง B** (เครื่องที่จะรัน Ollama จริง) เพื่อให้ย้ายไปรันอีกเครื่องได้ทันที

---

## 0. สรุปไฟล์ที่เพิ่ม/แก้ไข

| ไฟล์ | สถานะ | หน้าที่ |
|---|---|---|
| `api/core/config.py` | แก้ไข | เพิ่ม `OLLAMA_BASE_URL`, `OLLAMA_JUDGE_MODEL`, `OLLAMA_SUBJECT_MODEL`, `OLLAMA_TIMEOUT_S` |
| `api/schemas/models.py` | แก้ไข | เพิ่ม `is_local`, `ollama_model_name` ใน `AIModel` |
| `api/schemas/assessment.py` | ใหม่ | schema ของเกณฑ์ประเมิน/รายงานผล |
| `api/services/nist_rmf.py` | ใหม่ | ชุดเกณฑ์ประเมิน 12 ข้อ (อ้างอิง NIST AI RMF แบบย่อ) |
| `api/services/local_llm.py` | ใหม่ | client เรียก Ollama (`/api/chat`) |
| `api/services/assessment.py` | ใหม่ | engine รันการประเมิน + เก็บผลใน memory |
| `api/services/registry.py` | แก้ไข | เพิ่มโมเดล `ollama-local-poc` |
| `api/routers/assessment.py` | ใหม่ | endpoint `/api/assessment/...` |
| `api/routers/__init__.py` | แก้ไข | ลงทะเบียน router ใหม่ |
| `web/views/assessment.py` | ใหม่ | หน้าเว็บฟอร์มประเมิน + ผลลัพธ์ |
| `web/views/__init__.py`, `web/__init__.py` | แก้ไข | ลงทะเบียน blueprint ใหม่ |
| `web/templates/assessment/detail.html` | ใหม่ | หน้าแบบฟอร์ม + แสดงผลประเมิน |
| `web/templates/models/detail.html` | แก้ไข | เพิ่มปุ่มลิงก์ไปหน้าประเมิน |

ทั้งหมดเก็บผลแบบ **in-memory** (เหมือน model registry เดิม) — รีสตาร์ท API แล้วประวัติหาย
เหมาะสำหรับพิสูจน์แนวคิดเท่านั้น ก่อนเก็บข้อมูลจริงสำหรับงานวิจัยควรย้ายไปเก็บใน DB จริง

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

หาไฟล์ `.env` ของโปรเจกต์ (อยู่ที่ root ของ repo, ระดับเดียวกับ `pyproject.toml` —
จุดที่คุณรันคำสั่ง `python -m matini.cmd.api` อยู่) ถ้ายังไม่มีให้สร้างใหม่ แล้วเพิ่ม/แก้ไข:

```dotenv
# ชี้ไปยัง Ollama บนเครื่อง B
OLLAMA_BASE_URL=http://192.168.1.50:11434

# โมเดลที่ใช้เป็น "ผู้ตัดสิน" (ให้คะแนนแต่ละเกณฑ์)
OLLAMA_JUDGE_MODEL=llama3.2:3b

# โมเดลเริ่มต้นที่ใช้เป็น "ผู้ถูกประเมิน" เมื่อไม่ได้ระบุ ollama_model_name ใน registry
OLLAMA_SUBJECT_MODEL=llama3.2:3b

# local LLM บนเครื่องที่ไม่แรงมากอาจตอบช้า ปรับเพิ่มได้ถ้า timeout บ่อย
OLLAMA_TIMEOUT_S=120
```

> ค่าเริ่มต้นในโค้ด (`api/core/config.py`) ชี้ที่ `http://127.0.0.1:11434` — ถ้าไม่ตั้งค่า `.env`
> ระบบจะพยายามต่อ Ollama บนเครื่อง A เอง (ซึ่งตามที่แจ้งไว้ ยังไม่ต้องรันที่นี่)

ตรวจสอบว่า `requests` อยู่ใน dependencies ของโปรเจกต์ (ใช้อยู่แล้วฝั่ง `web/views/*`,
โค้ดใหม่ฝั่ง `api/services/local_llm.py` ก็ใช้ตัวเดียวกัน) ถ้ายังไม่มีใน `pyproject.toml`:
```bash
poetry add requests
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
# terminal 1: FastAPI backend
poetry run python -m matini.cmd.api

# terminal 2: Flask frontend
poetry run python -m matini.cmd.web
```
(หรือ `python -m matini.cmd.api` / `python -m matini.cmd.web` ตรง ๆ ถ้าไม่ได้ใช้ poetry)

เปิดเบราว์เซอร์ไปที่ `http://127.0.0.1:8080` → คลิกโมเดล **"Local LLM (Ollama POC)"** →
คลิกปุ่ม **"NIST AI RMF Assessment"** มุมขวาบน

---

## 5. วิธีใช้งานหน้าประเมิน

1. (ไม่บังคับ) กรอก **บริบทของระบบ** — อธิบายว่ากำลังประเมินอะไร ใช้ทำอะไร
2. ติ๊ก **"ทดสอบพฤติกรรมจริงของโมเดลอัตโนมัติสำหรับเกณฑ์ในหมวด MEASURE"** ไว้ (ค่าเริ่มต้นติ๊กอยู่แล้ว)
   ระบบจะยิง probe prompt 4 ข้อ (bias / privacy / explainability / safety) ไปที่โมเดลจริงผ่าน Ollama
3. (ไม่บังคับ) กรอกหลักฐาน/บันทึกของคุณเองในแต่ละเกณฑ์ (12 ข้อ แบ่งตาม GOVERN/MAP/MEASURE/MANAGE)
   — ยิ่งกรอกเยอะ ผลตัดสินของ LLM judge ยิ่งมีหลักฐานอ้างอิงมากขึ้น ไม่ใช่เดาจากชื่อโมเดลอย่างเดียว
4. กด **"Run NIST AI RMF Assessment"** — รอบแรกอาจใช้เวลาหลายนาทีถ้าเครื่อง B ไม่แรงมาก
   (12 เกณฑ์ × เรียก Ollama 1-2 ครั้งต่อเกณฑ์)
5. ผลลัพธ์แสดงทางซ้าย: คะแนนเฉลี่ยต่อฟังก์ชัน (GOVERN/MAP/MEASURE/MANAGE), overall risk level,
   และรายละเอียดต่อเกณฑ์ (คะแนน, risk level, เหตุผลจาก judge, transcript ของ probe ถ้ามี)
6. รันซ้ำได้เรื่อย ๆ — ระบบเก็บประวัติทุกรอบไว้ใน memory (`GET /api/assessment/{model_id}/history`)

---

## 6. API endpoints ใหม่ (ดูที่ `http://127.0.0.1:8000/docs` ได้ด้วย)

| Method | Path | หน้าที่ |
|---|---|---|
| GET | `/api/assessment/criteria` | รายการเกณฑ์ประเมินทั้งหมด (static) |
| POST | `/api/assessment/{model_id}/run` | รันการประเมินใหม่ 1 รอบ |
| GET | `/api/assessment/{model_id}` | ผลล่าสุด |
| GET | `/api/assessment/{model_id}/history` | ประวัติทุกรอบ |

---

## 7. Troubleshooting

- **"เชื่อมต่อ Ollama ไม่สำเร็จ..."** → เครื่อง B ยังไม่ได้รัน `ollama serve`, พอร์ต/ไฟร์วอลล์ไม่เปิด,
  หรือ `OLLAMA_BASE_URL` ผิด — ทดสอบด้วย `curl http://<ip เครื่อง B>:11434/api/tags` จากเครื่อง A
- **ตอบช้า/timeout** → เพิ่ม `OLLAMA_TIMEOUT_S` ใน `.env`, หรือเปลี่ยนไปใช้โมเดลเล็กลง (`llama3.2:3b`)
- **"ผลลัพธ์จาก judge model ไม่ใช่ JSON ที่แปลงได้"** → โมเดลเล็กบางตัวไม่ทำตาม instruction เรื่อง JSON
  ดีนัก ลองโมเดลอื่น หรือดู field `judge_error` ในผลลัพธ์แต่ละเกณฑ์เพื่อดู raw response
- **หน้าเว็บไม่มีสไตล์ / ปุ่มไม่มีสี** → ลืม build Tailwind (ขั้นตอนที่ 3)
- **404 ตอนกดปุ่ม "NIST AI RMF Assessment"** → ตรวจสอบว่า FastAPI backend รันอยู่ (Flask หน้าเว็บ
  เรียก API ผ่าน `API_URL` เพื่อดึงเกณฑ์/ผลลัพธ์)

---

## 8. ข้อจำกัดของ POC นี้ (สำหรับเขียนอภิปรายในงานวิจัย)

- **เกณฑ์ 12 ข้อเป็นชุดย่อยตัวแทน** ไม่ใช่ NIST AI RMF Core ฉบับเต็ม (~72 subcategories) —
  ก่อนเก็บข้อมูลจริงควรขยายชุดเกณฑ์และตรวจสอบความตรงเชิงเนื้อหาโดยผู้เชี่ยวชาญ (IOC) ตาม roadmap ข้อ D
- **self-evaluation bias** ถ้าใช้โมเดลเดียวกันเป็นทั้ง subject และ judge (ดูหัวข้อ 1)
- **เก็บผลแบบ in-memory** ไม่ถาวร ไม่เหมาะเก็บข้อมูลจริงสำหรับ analysis ของบทความ
- **probe prompt มีแค่ 1 ข้อ/เกณฑ์** สำหรับหมวด MEASURE — ความน่าเชื่อถือ (reliability) ของผลจะต่ำ
  ถ้าทดสอบครั้งเดียว ควรรันซ้ำหลายรอบ/สุ่ม prompt หลายแบบต่อมิติก่อนสรุปผลในบทความ
- **blocking call ใน async endpoint**: `api/services/assessment.py` เรียก Ollama แบบ synchronous
  ภายใน FastAPI async route (สไตล์เดียวกับ `guardrails.py` เดิมที่ใช้ `time.sleep`) — รับได้สำหรับ POC ที่มี
  ผู้ใช้ทีละคน แต่ไม่เหมาะกับ production ที่มีหลาย request พร้อมกัน
