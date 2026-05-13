// OmniDub web UI
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

const state = {
  file: null,
  lang: "zh",
  voice: "clone",
  subs: false,
  jobId: null,
};

// --- chips ---
function wireChips(groupSel, key) {
  $$(`${groupSel} button`).forEach(b => {
    b.onclick = () => {
      $$(`${groupSel} button`).forEach(x => x.classList.remove("on"));
      b.classList.add("on");
      state[key] = b.dataset.v;
    };
  });
}
wireChips("#langs", "lang");
wireChips("#voice", "voice");
$("#subs").onchange = e => state.subs = e.target.checked;

// --- drop zone ---
const drop = $("#drop");
const input = $("#file");

drop.onclick = () => input.click();
input.onchange = () => setFile(input.files[0]);
["dragenter", "dragover"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("drag"); }));
["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("drag"); }));
drop.addEventListener("drop", e => {
  const f = e.dataTransfer?.files?.[0];
  if (f) setFile(f);
});

function setFile(f) {
  state.file = f;
  $("#filename").textContent = f ? `${f.name} · ${(f.size / 1024 / 1024).toFixed(1)} MB` : "or drag it here";
}

// --- submit ---
$("#go").onclick = async () => {
  if (!state.file) { alert("Pick a video first"); return; }
  $("#go").disabled = true;
  $("#go").textContent = "Uploading…";

  const fd = new FormData();
  fd.append("video", state.file);
  fd.append("target_lang", state.lang);
  fd.append("voice_mode", state.voice);
  fd.append("burn_subtitles", state.subs ? "true" : "false");

  try {
    const r = await fetch("/api/dub", { method: "POST", body: fd });
    if (!r.ok) throw new Error(await r.text());
    const { job_id } = await r.json();
    state.jobId = job_id;
    showProgress();
    stream(job_id);
  } catch (e) {
    alert("Upload failed: " + e.message);
    $("#go").disabled = false;
    $("#go").textContent = "Dub it →";
  }
};

function showProgress() {
  $("#step-upload").classList.add("hide");
  $("#step-progress").classList.remove("hide");
  $$("#steps li").forEach(li => li.classList.remove("active", "done"));
}

function log(line) {
  const el = $("#log");
  el.textContent += line + "\n";
  el.scrollTop = el.scrollHeight;
}

function stream(jobId) {
  const es = new EventSource(`/api/stream/${jobId}`);
  let lastKey = null;
  es.onmessage = ev => {
    const evt = JSON.parse(ev.data);
    log(JSON.stringify(evt));
    markStage(evt.stage);
    lastKey = evt.stage;
    if (evt.stage === "done") {
      es.close();
      finish(jobId);
    } else if (evt.stage === "error") {
      es.close();
      alert("Error: " + (evt.reason || "unknown"));
    }
  };
  es.onerror = () => {
    es.close();
    if (lastKey !== "done") log("[stream closed]");
  };
}

function markStage(k) {
  const li = $(`#steps li[data-k="${k}"]`);
  if (!li) return;
  // Previous active becomes done.
  $$("#steps li.active").forEach(x => { x.classList.remove("active"); x.classList.add("done"); });
  li.classList.add("active");
  if (k === "done") li.classList.add("done");
}

function finish(jobId) {
  $("#step-progress").classList.add("hide");
  $("#step-done").classList.remove("hide");
  const url = `/api/download/${jobId}`;
  $("#player").src = url;
  $("#dl").href = url;
}

$("#again").onclick = () => location.reload();
