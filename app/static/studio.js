(() => {
  const status = document.querySelector("#job-status[data-status-url]");
  const forms = [...document.querySelectorAll("form[data-dirty-form]")];
  let dirty = false;

  for (const form of forms) {
    form.addEventListener("input", () => { form.dataset.dirty = "true"; dirty = true; });
    form.addEventListener("change", () => { form.dataset.dirty = "true"; dirty = true; });
    form.addEventListener("submit", () => { form.dataset.dirty = "false"; });
  }
  const uploadType = document.querySelector('select[name="kind"]');
  const uploadInput = document.querySelector('input[type="file"]');
  if (uploadType && uploadInput) {
    const allowed = { reference: ".jpg,.jpeg,.png,.webp", voiceover: ".wav,.mp3,.m4a", subtitle: ".srt" };
    const updateUpload = () => {
      uploadInput.accept = allowed[uploadType.value] || "";
      uploadInput.multiple = uploadType.value === "reference";
    };
    uploadType.addEventListener("change", updateUpload);
    updateUpload();
  }
  const referenceImages = [...document.querySelectorAll('input[name="reference_images"]')];
  const referenceCount = document.querySelector("[data-reference-count]");
  if (referenceImages.length && referenceCount) {
    const updateReferences = () => {
      const count = referenceImages.filter(input => input.checked).length;
      referenceCount.textContent = `เลือกแล้ว ${count} รูป`;
      for (const input of referenceImages) input.disabled = !input.checked && count >= 7;
    };
    referenceImages.forEach(input => input.addEventListener("change", updateReferences));
    updateReferences();
  }
  window.addEventListener("beforeunload", event => {
    if (dirty && forms.some(form => form.dataset.dirty === "true")) {
      event.preventDefault();
      event.returnValue = "";
    }
  });

  if (!status || status.dataset.busy !== "true") return;
  let lastSignature = "";
  let timer;
  const labels = {
    submitting: "กำลังส่งงาน", polling: "กำลังรอผลจากผู้ให้บริการ", complete: "กำลังเตรียมคลิป",
    generating: "กำลังสร้างคลิป", assembling: "กำลังประกอบวิดีโอ",
    exporting: "กำลังสร้างชุดดาวน์โหลด", test_review: "คลิปพร้อมตรวจ",
    clips_ready: "คลิปพร้อม", assembled: "วิดีโอพร้อมตรวจ",
    error: "งานมีปัญหา กรุณาตรวจข้อความในหน้านี้", indeterminate: "ต้องตรวจสถานะงานก่อนลองใหม่"
  };
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "โหลดสถานะล่าสุด";
  button.hidden = true;
  button.addEventListener("click", () => location.reload());
  status.after(button);

  async function poll() {
    if (document.hidden) return schedule();
    try {
      const response = await fetch(status.dataset.statusUrl, { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("status unavailable");
      const data = await response.json();
      const activeJob = data.jobs.find(job => !["complete", "failed", "indeterminate"].includes(job.status));
      const signature = [data.project_status, activeJob?.id, activeJob?.status, activeJob?.retry_count, data.completed_count].join(":");
      if (signature !== lastSignature) {
        lastSignature = signature;
        const progress = data.project_status === "generating" && activeJob ? labels[activeJob.status] : labels[data.project_status];
        status.textContent = data.busy
          ? `${progress || "กำลังดำเนินการ"} · ${data.completed_count}/${data.shot_count} คลิปเสร็จแล้ว`
          : `${labels[data.project_status] || "สถานะเปลี่ยนแล้ว"} · กดเพื่อโหลดข้อมูลล่าสุด`;
      }
      status.hidden = false;
      if (!data.busy) {
        button.hidden = false;
        return;
      }
      schedule();
    } catch {
      status.hidden = false;
      status.textContent = "ตรวจสถานะไม่สำเร็จ เครือข่ายอาจขาดช่วง ระบบจะลองอ่านสถานะอีกครั้ง";
      schedule(8000);
    }
  }
  function schedule(delay = 4000) {
    clearTimeout(timer);
    if (!document.hidden) timer = setTimeout(poll, delay);
  }
  document.addEventListener("visibilitychange", () => {
    clearTimeout(timer);
    if (!document.hidden) poll();
  });
  schedule(0);
})();
