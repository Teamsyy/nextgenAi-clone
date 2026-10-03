# UI/UX Improvement Implementation Plan — nextgen-local

> **For agentic workers:** ใช้ superpowers:executing-plans ทำทีละงานตาม checkbox; ใช้ subagent-driven-development เฉพาะเมื่อผู้ใช้เลือกวิธีนั้น แผนนี้เป็นข้อเสนอสำหรับตรวจทาน ไม่ใช่คำสั่งเริ่มแก้ระบบ

**Goal:** ให้ผู้ใช้สร้างโปรเจกต์ ตรวจข้อมูลสินค้า สร้างและตรวจคลิป ประกอบวิดีโอ และดาวน์โหลดได้โดยรู้เสมอว่าถึงขั้นไหน ต้องทำอะไรต่อ และการแก้ไขมีผลอย่างไร

**Architecture:** คง FastAPI + Jinja2 + Workflow เดิม ใช้ HTML/CSS เป็นหลักและ JavaScript ภายในเครื่องเฉพาะงานที่จำเป็น คำนวณสถานะสำหรับแสดงผลจากข้อมูลจริง โดยการอนุมัติและเงื่อนไขความปลอดภัยยังตรวจใน Workflow

**Tech Stack:** Python, FastAPI, Jinja2, SQLAlchemy/SQLite, CSS, vanilla JavaScript, pytest, FFmpeg/Pillow ที่ติดตั้งในโปรเจกต์อยู่แล้ว

**Spec:** อิงข้อกำหนดเดิมใน `docs/mvp-design.md` และเป้าหมาย UI/UX ในเอกสารนี้; ส่วนที่เปลี่ยนจาก 7 ช็อตเป็น UGC 1 ช็อตอิง working tree ปัจจุบันและต้องยืนยันกับพฤติกรรมจริงในเฟสแรก

## ขอบเขตและข้อจำกัด

- สมมติกลุ่มเป้าหมายคือผู้สร้างคอนเทนต์สินค้าใช้งานคนเดียว ภาษาไทยเป็นภาษาหลัก และต้องการความง่ายมากกว่ารายละเอียดทางเทคนิค
- ครอบคลุมความถูกต้องของข้อความ การนำทาง แบบฟอร์ม งานเบื้องหลัง สื่อ การตรวจรับ ความสวยงาม มือถือ accessibility และความเร็ว
- ตรวจจาก source code และเอกสาร ยังไม่ได้ตรวจหน้าจอจริงหรือทดสอบกับผู้ใช้ จึงไม่อ้างว่าพบปัญหาด้านภาพ/ประสิทธิภาพจากการวัดแล้ว
- working tree มีการแก้ `app/prompts.py`, `app/templates/project.html`, `app/workflow.py` และไฟล์ UGC ใหม่อยู่ก่อนแล้ว ต้องรักษางานเหล่านี้และตรวจความเข้ากันได้
- ไม่มีการเปลี่ยนไปใช้ React, เพิ่ม UI framework, ระบบบัญชี, cloud analytics หรือการโพสต์อัตโนมัติในแผนนี้
- mock ต้องระบุว่าเป็นคลิปสังเคราะห์; gflow ที่ยังไม่พร้อมต้องบอกเหตุผลจริง ไม่แสดงความสามารถ เครดิต ราคา หรือเวลาที่ไม่ได้ตรวจสอบ
- รักษา CSRF, Host/Origin guard, CSP, การตรวจไฟล์, การซ่อนความลับ และการห้ามส่งงานซ้ำเมื่อผลการส่งไม่แน่นอน
- ไม่ต้อง migration ฐานข้อมูลสำหรับ UI พื้นฐาน; ถ้าการตั้งค่า overlay จำเป็นต้องเพิ่มข้อมูล ให้แยกงานพร้อมทดสอบโปรเจกต์เก่า

## สิ่งที่พบจากโค้ด

| ปัญหา | หลักฐาน | ผลต่อผู้ใช้ | ลำดับ |
|---|---|---|---|
| จำนวนคลิปขัดกัน | `ROLES` มี `ugc_showcase` รายการเดียว แต่หน้าแรก/metrics/README และ tests บางส่วนยังอิง 7 คลิป | ผู้ใช้ไม่รู้ว่าจะได้งานกี่ชิ้น | P0 |
| ข้อความสินค้าและทรัพยากรประกอบคลิปตายตัว | `Workflow.assemble()` ส่งชื่อแก้วและข้อความเดิม; `ugc_template.py` อ้าง font/BGM จากโปรเจกต์หนึ่ง และ fallback แบบเงียบ | ผลลัพธ์ผิดสินค้า หรือไม่ตรงกับสิ่งที่หน้าจอให้เข้าใจ | P0 |
| ปุ่ม disabled ไม่แสดงเหตุผลรายปุ่ม | macro `action()` แสดงเพียง disabled | ไม่รู้ว่าต้องแก้อะไรเพื่อทำต่อ | P0 |
| error แยกหน้าและกลับได้แค่ dashboard | `error.html`, `value_error()` | หลุดบริบทและอาจต้องกรอกใหม่ | P0 |
| busy รีเฟรชทั้งหน้าทุก 4 วินาที | `base.html` | เสี่ยงเสีย draft, scroll, focus และขัดจังหวะ player | P0 |
| ภาษา/สถานะไม่สม่ำเสมอ | `lang="en"`, ข้อความอังกฤษ, แสดง status enum โดยแทน underscore | เพิ่มภาระผู้ใช้ภาษาไทย | P1 |
| หน้าโปรเจกต์แสดงทุกขั้นและรายละเอียดเทคนิคต่อกัน | `project.html` | ขั้นต่อไปไม่เด่น ต้องเลื่อนหาข้อมูล | P1 |
| มือถือซ่อน hero-card | media query ใน `style.css` | ข้อมูล provider ที่อยู่ในการ์ดต้องมีตำแหน่งอื่น | P1 |
| player และ reference preview เล็ก | video จำกัด 230px, thumbnails 85×100 | ตรวจรายละเอียดสินค้าได้ยาก | P1 |
| QC เน้น JSON และค่าทางเทคนิค | export section | ไม่เห็นสรุปว่าผ่านอะไรและยังต้องตรวจอะไร | P1 |

## แนวทางที่เลือก

1. **แนะนำ: ปรับ workflow และภาพรวมบนระบบเดิม** — แก้ความเข้าใจผิดก่อน แล้วจัดหน้าจอและเพิ่ม interaction เท่าที่จำเป็น ทดสอบแต่ละเฟสได้และ diff ไม่ใหญ่เกินไป
2. ปรับเฉพาะ CSS — เร็วกว่า แต่ไม่แก้สถานะผิด ข้อมูลหาย และเงื่อนไขปุ่ม เหมาะกับการแต่งภาพหลัง P0 เท่านั้น
3. เขียน frontend ใหม่ — ใช้เวลามากและเพิ่มการดูแล เลื่อนจนมีข้อจำกัดที่วัดได้จากระบบเดิม

แนวภาพ: คงสีเขียวของแบรนด์ ใช้พื้นหลังอ่อน พื้นที่ทำงานสะอาด ตัวอักษรไทยอ่านง่าย และสีสถานะที่แยกจากสีตกแต่ง ลดพื้นที่ hero เพื่อให้เห็นงานจริงเร็วขึ้น

## โครงหน้าจอและเส้นทางหลัก

- **Dashboard:** สรุปงานที่รอตรวจ/กำลังทำ/พร้อมดาวน์โหลด → รายการโปรเจกต์ → ปุ่มสร้างโปรเจกต์; empty state มีตัวอย่างข้อมูลและ CTA เดียว
- **Create:** ชื่อโปรเจกต์ ชื่อสินค้า URL เป็นข้อมูลหลัก; audience/tone/claims เป็นส่วนเพิ่มเติม พร้อมบอก required/optional
- **Project Studio:** breadcrumb + ชื่อสินค้า + โหมด → stepper → สรุปขั้นถัดไป → ส่วนของขั้นปัจจุบัน → preview; ย้อนดูขั้นก่อนหน้าได้โดยไม่ต้องล้างข้อมูล
- **เส้นทาง:** สร้างโปรเจกต์ → ข้อเท็จจริงและหลักฐาน → ตรวจ prompt → สร้างและตรวจคลิป → ประกอบ → technical QC + visual review → ดาวน์โหลด
- **Export:** preview ใหญ่ สรุป QC อ่านได้ รายการที่ยังไม่ตรวจ และปุ่ม MP4/ZIP แยกความหมาย
- Desktop ใช้สองคอลัมน์เมื่อช่วยงานจริง; mobile คอลัมน์เดียว ปุ่มหลักเต็มความกว้าง ไม่มีแถบ fixed บังช่องกรอกหรือ focus

## Review Focus

1. โปรเจกต์เก่า 7 ช็อตกับโปรเจกต์ใหม่ 1 ช็อต: ไม่ลบช็อต/ไฟล์/audit history เพื่อให้ UI ตรงกับจำนวนใหม่; หาก workflow ใช้ต่อไม่ได้ ต้องแจ้งก่อนการแก้ไข
2. validation ไม่ผ่านหรือ session/CSRF หมดอายุ: มีทางกลับบริบทและรักษาข้อความที่กรอก โดยไม่เก็บความลับหรือ file input
3. งาน busy, network ขาด, timeout และ indeterminate: status ไม่หลอกว่าทำสำเร็จและไม่มีปุ่มส่งซ้ำโดยอัตโนมัติ
4. แก้ facts/prompt/reference หลังอนุมัติ: แสดงผลกระทบและไม่เปิดดาวน์โหลดผลลัพธ์เก่า
5. ภาษาไทย ชื่อยาว URL ยาว 320px และ zoom 200%: อ่านได้ กดได้ และไม่ทำ layout ล้นทั้งหน้า

## เฟส 0 — เก็บ baseline และตัดสินจำนวนช็อต (P0)

**Files:** `app/prompts.py`, `app/workflow.py`, `app/templates/index.html`, `app/templates/project.html`, `tests/test_workflow.py`, `tests/test_regressions.py`, `README.md`, `docs/verification.md`

- [ ] เปิดแอปใน mock mode และบันทึกภาพ dashboard/project/export ที่ 1440px, 768px, 390px และ 320px ด้วยข้อมูลทดสอบ ไม่แก้โปรเจกต์จริง
- [ ] รัน `python -m pytest -q` บันทึกผลจริงและแยก failure ที่มีอยู่ก่อนออกจากงาน UI
- [ ] ตรวจ flow ใหม่ 1 ช็อตและโปรเจกต์เก่า 7 ช็อต; ให้ UI แสดงจำนวนจาก shots จริง หรือ `len(ROLES)` ก่อนมี shots ไม่ใช้เลข 7 ตายตัว
- [ ] เพิ่ม regression สำหรับจำนวนที่แสดงและโปรเจกต์ legacy; ไม่เรียก regenerate ในการ migration/UI render
- [ ] กำหนดงานมาตรฐานสำหรับวัดก่อน/หลัง: สร้างโปรเจกต์, แก้หลักฐานขาด, ตรวจคลิป, แก้ prompt หลังอนุมัติ และ export

**ตรวจรับ:** หน้าจอ/brief/เอกสาร/ข้อคาดหวังใน tests ตรงกับขอบเขต 1 ช็อตที่เลือก; ข้อมูล legacy ไม่สูญหายเพราะการเปิดหน้าจอ

## เฟส 1 — ความถูกต้องและขั้นถัดไป (P0)

**Files:** `app/web.py`, `app/templates/project.html`, `app/templates/index.html`, `tests/test_web.py`

**Interface:** helper `project_ui_state(detail: dict, provider: dict, can_assemble: bool) -> dict` ใน `app/web.py` คืน `current_step`, `next_action`, `action_blockers`, `shot_count`, `completed_count` สำหรับ render เท่านั้น ไม่อนุมัติหรือแก้ข้อมูล

- [ ] เพิ่ม tests ของสถานะ draft, facts approved, prompts approved, test review, test approved, assembled, QC failed, exported, busy และ provider blocked
- [ ] สรุป “ทำอะไรต่อ” ไว้บนหน้า มี primary CTA เดียวตามขั้นปัจจุบัน และ secondary action ที่เกี่ยวข้อง
- [ ] stepper แสดงกำลังทำ/เสร็จ/ต้องตรวจใหม่ด้วยข้อความและ `aria-current="step"`; ใช้ anchor เดิมและคงการย้อนดูข้อมูล
- [ ] แสดงเหตุผลข้างปุ่ม disabled เช่น “เพิ่มหลักฐานสี รูปร่าง ขนาด และอุปกรณ์ให้ครบก่อน” ไม่พึ่ง tooltip บน hover
- [ ] แสดง mock badge ถาวรและบอกข้อจำกัด reference; gflow blocked มีทางไปคำอธิบายการตั้งค่าโดยไม่เพิ่มปุ่มเปิดใช้งานที่ข้าม readiness
- [ ] เพิ่มสรุปผลของการแก้ข้อมูลก่อนบันทึก เช่น “ต้องอนุมัติ prompt และสร้างคลิปใหม่”; ขอ confirm เฉพาะการทำให้ผลลัพธ์ที่มีอยู่ใช้ไม่ได้

**ตรวจรับ:** ผู้ใช้ระบุขั้นปัจจุบันและสิ่งที่ต้องทำต่อได้ภายใน 5 วินาทีในการทดสอบ; server ยังปฏิเสธ action ที่ไม่ผ่านเงื่อนไขแม้เรียก POST ตรง

## เฟส 2 — แบบฟอร์ม ภาษา และ recovery (P0/P1)

**Files:** `app/web.py`, templates ทั้ง 4 ไฟล์, `app/static/style.css`, `tests/test_web.py`, `tests/test_regressions.py`

- [ ] ใช้ UI ภาษาไทยเป็นค่าเริ่มต้นและ `lang="th"`; ระบุภาษา prompt แยกจากภาษา UI ไม่ผูกสองอย่างเข้าด้วยกัน
- [ ] แปลง status enum เป็นคำที่เข้าใจ เช่น “รอตรวจคลิป”; technical details ยังดูได้ใน details
- [ ] แสดง label จริง ตัวอย่าง และข้อจำกัดช่องกรอก; maxlength ตรง backend สำหรับ facts/source/notes/prompt/negative prompt
- [ ] เพิ่มตัวช่วยกรอกสี/รูปร่าง/ขนาด/อุปกรณ์ โดย serialize กลับเป็น `color:`, `shape:`, `size:`, `accessories:` ให้ `identity()` เดิมอ่านได้; ยังคงกรอก fact อื่นได้
- [ ] แสดง error ใกล้ field และ error summary พร้อมลิงก์ไป field, `aria-invalid` และ `aria-describedby`; คงค่าข้อความเดิมเมื่อ validation ล้มเหลว
- [ ] จัดการ Pydantic validation และ expected workflow errors ให้เป็นข้อความผู้ใช้ที่ redact/escape แล้ว; unexpected error ไม่เปิดเผย traceback
- [ ] หลังบันทึกสำเร็จใช้ POST/Redirect/GET กลับ anchor ของขั้นเดิมและข้อความยืนยันครั้งเดียว; error page กลับโปรเจกต์ได้โดยใช้ปลายทางภายในที่ตรวจสอบแล้ว
- [ ] สำหรับ CSRF ผิด ให้กลับไปโหลดฟอร์มใหม่และคัดลอกข้อความที่ยังกรอกไว้ได้; ไม่ส่ง POST ซ้ำเอง

**ตรวจรับ:** URL ผิด ชื่อว่าง fact ขาดหลักฐาน และ prompt ยาวเกินไม่ทำให้ต้องเริ่มใหม่; HTML ที่กรอกไม่ถูกรัน; successful refresh ไม่ส่ง action ซ้ำ

## เฟส 3 — ภาษาภาพ มือถือ และ accessibility (P1)

**Files:** `app/static/style.css`, `app/templates/base.html`, `app/templates/index.html`, `app/templates/project.html`

- [ ] รวม CSS variables สำหรับสีพื้น/ข้อความ/เส้น/สถานะ, spacing 4/8/12/16/24/32px, radius 8/12/16px และ shadow 2 ระดับ; ใช้กับองค์ประกอบเดิม
- [ ] body 16px, Thai line-height 1.6–1.75; heading ใช้ `clamp()` ไม่แย่งพื้นที่งาน และใช้ system font ที่รองรับไทยก่อน
- [ ] สถานะมีข้อความหรือ icon ประกอบ ไม่ใช้สีล้วน; contrast ข้อความปกติอย่างน้อย 4.5:1, ข้อความใหญ่ 3:1 และ UI boundaries สำคัญ 3:1
- [ ] ทำ button/input/card/alert/stepper ให้ใช้หน้าตาและ spacing เดียวกันผ่าน CSS classes กับ Jinja macro เท่าที่ซ้ำจริง
- [ ] ที่ 320–390px navigation wrap ได้, URL/ชื่อยาว break ได้, thumbnail wrap ได้; ตารางเทคนิคเลื่อนเฉพาะใน container
- [ ] ข้อมูล provider ที่สำคัญยังเห็นบนมือถือแม้ซ่อน hero; dashboard ลด hero และแสดง project status กับ next step เด่นขึ้น
- [ ] เพิ่ม skip link, page title รายโปรเจกต์, heading hierarchy, form landmarks, focus ที่เห็นและไม่ถูก sticky bar บัง
- [ ] ออกแบบเป้าหมายสัมผัสอย่างน้อย 44×44px สำหรับ controls หลัก เป็นเป้าหมายของผลิตภัณฑ์; ไม่อ้างว่า 44px คือเกณฑ์ขั้นต่ำ AA
- [ ] ทดสอบ Tab/Shift+Tab/Enter/Space, screen reader ภาษาไทย, zoom 200% และ reflow; animation สั้นและรองรับ `prefers-reduced-motion`

**ตรวจรับ:** ไม่มี horizontal scroll ทั้งหน้า ยกเว้นตารางเฉพาะส่วน; ทุก action ใช้ keyboard ได้; automated checks และ manual checks ผ่านก่อนอ้างความสอดคล้อง WCAG

## เฟส 4 — งานเบื้องหลังและการรักษาบริบท (P0/P1)

**Files:** `app/web.py`, `app/templates/base.html`, `app/templates/project.html`, สร้าง `app/static/studio.js`, `tests/test_web.py`, `tests/test_regressions.py`

**Interface:** `GET /projects/{pid}/status` คืนเฉพาะ `project_status`, `busy`, `completed_count`, `shot_count`, `jobs` ที่มี `id/status/retry_count` และข้อความ error ที่ redact แล้ว; ไม่คืน prompts, paths หรือ credentials

- [ ] เพิ่ม tests ของ status response ทั้ง busy/complete/failed/indeterminate และการไม่เปิดเผยข้อมูลลับ
- [ ] ลบ meta-refresh; โหลด JS ด้วย external script ภายใต้ CSP เดิม ใช้ polling 4 วินาทีเฉพาะเมื่อ busy และมี request ค้างได้ไม่เกินหนึ่งรายการ
- [ ] แสดงขั้นจริง เช่น “กำลังส่งงาน/รอผล/เตรียมคลิป”; ถ้าไม่รู้ความคืบหน้าใช้ indeterminate indicator ไม่เดาเปอร์เซ็นต์หรือ ETA
- [ ] polling failure แสดง “ติดต่อสถานะไม่ได้” เก็บสถานะล่าสุดไว้ และปุ่ม refresh แบบอ่านอย่างเดียว; หยุด polling เมื่อไม่ busy หรือซ่อน tab
- [ ] อัปเดตเฉพาะ status region และใช้ `aria-live="polite"` เมื่อสถานะเปลี่ยน ไม่ประกาศซ้ำทุก poll
- [ ] เมื่อเสร็จแสดงลิงก์โหลดผลใหม่ให้ผู้ใช้เลือก ไม่ reload ทับ draft หรือ player อัตโนมัติ; no-JS มีปุ่มอัปเดตสถานะ
- [ ] เตือนก่อนออกหน้าเมื่อมีข้อความยังไม่บันทึก ใช้ dirty flag เฉพาะใน memory; เมื่อ submit ปิดคำเตือนและล็อกการกดซ้ำ โดย server guard ยังเป็นตัวหลัก
- [ ] ระบุ indeterminate ว่าต้องตรวจสอบประวัติก่อนทำต่อ; ไม่เพิ่ม retry generation/cancel ถ้า backend ยังไม่รองรับ

**ตรวจรับ:** กรอกข้อความ/ดู preview ระหว่าง poll แล้วข้อมูล focus และตำแหน่งไม่หาย; disconnect/reconnect ไม่ส่ง generation ใหม่

## เฟส 5 — Upload, preview และผลลัพธ์ที่ตรงกับสิ่งที่เลือก (P0/P1)

**Files:** `app/templates/project.html`, `app/static/style.css`, `app/static/studio.js`, `app/web.py`, `app/workflow.py`, `app/ugc_template.py`, `tests/test_regressions.py`, `tests/test_media.py`

- [ ] upload แสดงชนิด ขนาดสูงสุดจาก Settings และชื่อไฟล์ก่อนส่ง; เปลี่ยน `accept` ตามชนิด แต่ server ยังตรวจไฟล์จริง
- [ ] แยกสถานะ reference/voiceover/subtitle ชัดเจน บอกผลต่อ approvals/reassembly; thumbnail มี alt ระบุลำดับและเปิดดูใหญ่ผ่านลิงก์เดิมได้
- [ ] player preview รักษา 9:16 และขยายได้: desktop กว้างสูงสุดประมาณ 360px, mobile กว้างเท่าพื้นที่; โหลด `metadata` และไม่ autoplay
- [ ] negative prompt กับ operation/job detail อยู่ใน details; ข้อความหลักและ preview อยู่ใกล้กันโดยไม่ต้องเลื่อนข้ามส่วนเทคนิค
- [ ] แก้ assembly ให้ default ใช้ชื่อ/ข้อมูลที่อนุมัติจริง หรืองด title overlay จนมีข้อมูลที่ตรวจได้ ไม่ใช้ข้อความแก้วตายตัวกับทุกสินค้า
- [ ] ทรัพยากร font/BGM ต้องไม่อ้างไดเรกทอรีโปรเจกต์ตัวอย่าง; ไม่มี asset ให้ใช้ assembly ธรรมดาโดยแจ้งว่าข้าม effect ใด หากเลือก effect เป็นข้อกำหนดแล้วทำไม่ได้ ให้ error ชัดเจน
- [ ] voiceover/subtitles ที่อัปโหลดต้องถูกใช้ในทุกเส้นทาง assembly รวมถึง UGC effect ไม่ให้ overlay route ข้ามสอง input นี้
- [ ] เพิ่ม media regression สำหรับสินค้าคนละชนิด, assets ไม่มี, ภาษาไทยยาว, voiceover และ subtitle; ถ้าทำ customization ต่อ ให้เป็นงานย่อยที่มีข้อกำหนดและ persistence ชัดเจน

**ตรวจรับ:** preview/export ไม่มีข้อความของโปรเจกต์อื่น และ input เสียง/ซับไม่ถูกละเลย; รูปเสีย ไฟล์เกินขนาด และ SRT ผิดมีคำแนะนำแก้ไข

## เฟส 6 — QC, export และกลับมาทำงานต่อ (P1)

**Files:** `app/templates/project.html`, `app/templates/index.html`, `app/web.py`, `app/static/style.css`, `tests/test_web.py`, `tests/test_regressions.py`

- [ ] แสดง QC เป็น “ผ่าน/ไม่ผ่าน/ยังไม่ตรวจ” พร้อมขนาดวิดีโอ ระยะเวลา ภาพ เสียง และข้อผิดพลาด; JSON เป็นรายละเอียดเพิ่มเติม
- [ ] แสดง visual review ที่ตรวจแล้ว/ทั้งหมดและรายการที่เหลือ ไม่แสดง technical QC เป็นการรับรองสินค้า
- [ ] ปุ่ม “ดาวน์โหลดวิดีโอ MP4” กับ “ดาวน์โหลดชุดตรวจงาน ZIP” แยกคำอธิบาย; บอกเมื่อไฟล์ต้องประกอบ/สร้าง ZIP ใหม่
- [ ] รักษา policy เดิม: review package ที่มีรายการยังไม่ตรวจสามารถส่งออกตาม backend ได้ แต่ต้องระบุชัดว่าไม่ได้อนุมัติเผยแพร่
- [ ] dashboard แสดง status/updated time/ขั้นถัดไป; เพิ่มค้นหาชื่อและ filter สถานะด้วย query parameters เมื่อมีหลายโปรเจกต์ ใช้ list ที่มีอยู่และ empty-search state
- [ ] ไม่ทำ infinite scroll หรือ pagination ก่อนพบจำนวนโปรเจกต์ที่ทำให้หน้าช้าจาก baseline

**ตรวจรับ:** stale MP4/ZIP ยังถูกปฏิเสธทั้งใน UI และ file route; failed QC บอกสาเหตุ; ผู้ใช้หาโปรเจกต์เดิมและกลับไปขั้นที่ค้างได้

## เฟส 7 — ตรวจรับรวมและวัดผล (P1)

**Files:** `tests/test_web.py`, `tests/test_regressions.py`, `tests/test_workflow.py`, `tests/test_media.py`, `docs/verification.md`

- [ ] รัน tests เฉพาะส่วนระหว่างทำแต่ละงาน และ `python -m pytest -q` หลังรวม; expectations เดิมที่อิง 7 ช็อตต้องเปลี่ยนตาม contract ที่ตกลง ไม่ลบทดสอบ approvals/security เพื่อให้ suite ผ่าน
- [ ] รัน `python -m app demo` ใน output/database ทดสอบแยก พร้อม FFmpeg/ffprobe; ตรวจภาพจริง เสียง ซับ QC และ ZIP ไม่ใช้ผล test แทน visual review
- [ ] ทดสอบ keyboard/screen reader และ screenshot matrix 320/390/768/1440px ด้วย empty, long content, busy, failed, exported
- [ ] วัด LCP/INP/CLS กับ dashboard และ studio โดยระบุเครื่อง/browser/dataset; เป้าหมาย LCP ≤2.5s, INP ≤200ms, CLS ≤0.1 เป็น acceptance budget ไม่ใช่ผลที่วัดแล้ว
- [ ] ตรวจ performance จากขนาดภาพ จำนวน project/job และ video loading ก่อนเพิ่ม caching/index/pagination; ไม่ cache หน้า/response ที่มี CSRF หรือ private data แบบ public
- [ ] ทดสอบกับผู้ใช้เป้าหมาย 3–5 คนตามงานเฟส 0 บันทึกเวลาสำเร็จ จุดติดขัด และการสูญเสียข้อมูลโดยไม่ส่ง analytics ออกนอกเครื่อง
- [ ] อัปเดต `docs/verification.md` ด้วยคำสั่ง ผลทดสอบ รูปก่อน/หลัง known issues และประเด็นที่ยังไม่ผ่าน

**เป้าหมาย UX สำหรับ pilot:** อย่างน้อย 80% ทำ flow mock หลักสำเร็จโดยไม่ต้องมีคนบอกขั้นต่อไป; เวลาหาขั้นถัดไปลดจาก baseline; ไม่มีข้อความที่ยังไม่บันทึกสูญหายจาก polling; 100% ของปุ่ม blocked มีเหตุผลที่อ่านได้

## ลำดับส่งมอบและความพยายามโดยประมาณ

| ชุดงาน | เฟส | ความพยายาม | เหตุผล |
|---|---|---|---|
| ความถูกต้องก่อน | 0 → 1 → 2 และส่วน assembly ของ 5 | 3–5 วันทำงาน | แก้สิ่งที่ทำให้งานผิด/ผู้ใช้ติดขัด |
| หน้าจอและ interaction | 3 → 4 → ส่วน upload/preview ของ 5 | 3–5 วันทำงาน | อ่านง่าย มือถือดี งานเบื้องหลังไม่รบกวน |
| ปิด workflow และวัดผล | 6 → 7 | 2–3 วันทำงาน + นัดผู้ใช้ | พิสูจน์ว่าใช้งานได้ดีขึ้น |

ช่วงเวลานี้เป็นประมาณการแรงงาน ไม่รวมการทำ gflow ให้ใช้งานจริง, แก้ media failures ที่พบเพิ่ม หรือระบบปรับแต่งวิดีโอเต็มรูปแบบ ปรับหลัง baseline

## Definition of Done

**Implementation status:** The core one-shot workflow alignment, Thai dashboard/studio UI, next-step and blocker guidance, status endpoint with non-destructive polling, form recovery, search/filter, legacy read-only guard, and mock media/export verification are implemented. Full keyboard/screen-reader review, screenshots at the target viewport matrix, measured Web Vitals, and the 3–5 person pilot are still outstanding; do not report the pilot targets or WCAG conformance as verified.

- ตัวเลข ความสามารถ ราคา สถานะ และ output ที่ UI กล่าวอ้างตรงกับระบบจริง
- flow mock ตั้งแต่สร้างถึง export ผ่านพร้อม approvals/invalidation เดิม
- error แก้ต่อได้ แบบฟอร์มไม่สูญข้อมูลจาก validation/polling
- หน้าจอทั้ง desktop/mobile และ keyboard ผ่านรายการตรวจรับ
- ไม่มีการลด security/readiness หรือสร้างการส่งงานซ้ำ
- มีผลก่อน/หลังและ test evidence แยกจากเป้าหมายที่ยังไม่ได้วัด

## เอกสารอ้างอิง

- [W3C WCAG 2.2 Quick Reference](https://www.w3.org/WAI/WCAG22/quickref/) — contrast, reflow, focus, keyboard, labels, errors และ status messages; การผ่านข้อที่เลือกไม่เท่ากับรับรองว่าผ่าน WCAG ทั้งหมด
- [Google Web Vitals](https://web.dev/articles/vitals) — นิยามและเกณฑ์ LCP/INP/CLS; lab measurements ของ local app ไม่ใช่ field percentile จากผู้ใช้จำนวนมาก

## ตรวจทานแผน

- ครอบคลุมทุกส่วนของเส้นทางผู้ใช้และจุดเสี่ยง 5 รายการใน Review Focus
- ทำบน stack เดิม เพิ่มไฟล์ JS หนึ่งไฟล์เมื่อจำเป็น ไม่แยก component หรือ service ที่ไม่มีหน้าที่จริง
- เริ่มจากเฟส 0 และแก้ P0 ก่อนแต่งภาพ; ไม่มีการแก้ product code ในการจัดทำแผนนี้
