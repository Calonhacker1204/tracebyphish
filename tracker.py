import base64
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import sys
from urllib.parse import urlparse

HOST = "0.0.0.0"
PORT = 8080
LOG_FILE = "logs.jsonl"
CAPTURE_DIR = "captures"
AUDIO_DIR = "audio_captures"

os.makedirs(CAPTURE_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)

# ANSI Warna biar tampilannya berwarna di Termux
R = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[96m"
PINK = "\033[95m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
BLUE = "\033[94m"
RED = "\033[91m"


def ambil_ip_asli(headers, client_ip):
  for nama_header in ("CF-Connecting-IP", "X-Real-IP", "X-Forwarded-For"):
    nilai = headers.get(nama_header)
    if nilai:
      return nilai.split(",")[0].strip()
  return client_ip


def catat_log(mode, ip, path, ua):
  waktu = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
  entry = {
      "waktu": waktu,
      "mode": mode,
      "ip": ip,
      "path": path,
      "user_agent": ua,
  }
  with open(LOG_FILE, "a", encoding="utf-8") as f:
    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
  print(f"{GREEN}[{waktu}]{R} {CYAN}[{mode.upper()}]{R} IP: {YELLOW}{ip}{R} | Path: {path}")


def halaman_foto(ip: str) -> str:
  return f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Capture Foto + Filter CSS</title>
<style>
  body {{ font-family: sans-serif; background: #090d16; color: #f8fafc; padding: 20px; max-width: 420px; margin: auto; }}
  video {{ width: 100%; border-radius: 12px; background: #000; margin: 12px 0; }}
  .f-none {{ filter: none; }}
  .f-retro {{ filter: sepia(0.55) contrast(1.15); }}
  .f-vivid {{ filter: saturate(1.8) contrast(1.1); }}
  .f-mono {{ filter: grayscale(1) contrast(1.2); }}
  button {{ padding: 10px 14px; margin: 4px 2px; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; }}
  .btn-snap {{ background: #22c55e; color: #052e16; width: 100%; margin-top: 10px; }}
</style>
</head>
<body>
  <h3>Capture Foto (Kamera Depan)</h3>
  <p style="font-size:13px; color:#94a3b8;">IP: {ip}</p>
  <p id="status">Meminta izin kamera depan...</p>

  <div>
    <button onclick="setFilter('f-none')">Normal</button>
    <button onclick="setFilter('f-retro')">Retro</button>
    <button onclick="setFilter('f-vivid')">Vivid</button>
    <button onclick="setFilter('f-mono')">B&amp;W</button>
  </div>

  <video id="vid" class="f-none" autoplay playsinline></video>
  <canvas id="cvs" style="display:none;"></canvas>
  <button class="btn-snap" onclick="ambilFoto()">Ambil &amp; Simpan Foto</button>

<script>
  const vid = document.getElementById("vid");
  const cvs = document.getElementById("cvs");
  const statusEl = document.getElementById("status");

  function setFilter(cls) {{
    vid.className = cls;
  }}

  async function initCam() {{
    try {{
      const stream = await navigator.mediaDevices.getUserMedia({{
          video: {{ facingMode: "user" }},
          audio: false
      }});
      vid.srcObject = stream;
      statusEl.innerText = "Kamera depan aktif.";
    }} catch (e) {{
      statusEl.innerText = "Gagal/ditolak: " + e.message;
    }}
  }}

  async function ambilFoto() {{
    if (!vid.videoWidth) return;
    cvs.width = vid.videoWidth;
    cvs.height = vid.videoHeight;
    const ctx = cvs.getContext("2d");
    ctx.filter = getComputedStyle(vid).filter;
    ctx.drawImage(vid, 0, 0, cvs.width, cvs.height);
    const dataUrl = cvs.toDataURL("image/jpeg", 0.85);

    const res = await fetch("/upload-foto", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{ image: dataUrl }})
    }});
    const out = await res.json();
    statusEl.innerText = out.message || "Terkirim";
  }}

  initCam();
</script>
</body>
</html>"""


def halaman_audio(ip: str) -> str:
  return f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Capture Audio Simpel</title>
<style>
  body {{ font-family: sans-serif; background: #090d16; color: #f8fafc; padding: 20px; max-width: 420px; margin: auto; }}
  button {{ padding: 10px 14px; margin-right: 8px; border: none; border-radius: 8px; cursor: pointer; font-weight: 600; }}
  .rec {{ background: #ef4444; color: #fff; }}
  .stop {{ background: #38bdf8; color: #082f49; }}
</style>
</head>
<body>
  <h3>Capture Audio (Mic)</h3>
  <p style="font-size:13px; color:#94a3b8;">IP: {ip}</p>
  <p id="status">Klik Rekam untuk minta izin mic.</p>
  <button class="rec" id="btnRec" onclick="mulaiRekam()">Mulai Rekam</button>
  <button class="stop" id="btnStop" onclick="stopRekam()" disabled>Stop &amp; Kirim</button>

<script>
  let mediaRecorder = null;
  let chunks = [];
  const statusEl = document.getElementById("status");
  const btnRec = document.getElementById("btnRec");
  const btnStop = document.getElementById("btnStop");

  async function mulaiRekam() {{
    try {{
      const stream = await navigator.mediaDevices.getUserMedia({{ audio: true, video: false }});
      chunks = [];
      mediaRecorder = new MediaRecorder(stream);
      mediaRecorder.ondataavailable = (e) => {{
        if (e.data.size > 0) chunks.push(e.data);
      }};
      mediaRecorder.onstop = async () => {{
        stream.getTracks().forEach(t => t.stop());
        const blob = new Blob(chunks, {{ type: mediaRecorder.mimeType || "audio/webm" }});
        const reader = new FileReader();
        reader.onloadend = async () => {{
          const res = await fetch("/upload-audio", {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{ audio: reader.result }})
          }});
          const out = await res.json();
          statusEl.innerText = out.message || "Audio terkirim";
        }};
        reader.readAsDataURL(blob);
      }};
      mediaRecorder.start();
      btnRec.disabled = true;
      btnStop.disabled = false;
      statusEl.innerText = "Sedang merekam...";
    }} catch (e) {{
      statusEl.innerText = "Gagal/ditolak: " + e.message;
    }}
  }}

  function stopRekam() {{
    if (mediaRecorder && mediaRecorder.state !== "inactive") {{
      mediaRecorder.stop();
      btnRec.disabled = false;
      btnStop.disabled = true;
      statusEl.innerText = "Mengirim audio...";
    }}
  }}
</script>
</body>
</html>"""


def buat_handler(mode_aktif: str):
  class SimpleCaptureHandler(BaseHTTPRequestHandler):

    def do_GET(self):
      parsed = urlparse(self.path)
      if parsed.path == "/favicon.ico":
        self.send_response(204)
        self.end_headers()
        return

      ip = ambil_ip_asli(self.headers, self.client_address[0])
      ua = self.headers.get("User-Agent", "Unknown")
      catat_log(mode_aktif, ip, self.path, ua)

      html_str = (
          halaman_audio(ip) if mode_aktif == "audio" else halaman_foto(ip)
      )
      body = html_str.encode("utf-8")
      self.send_response(200)
      self.send_header("Content-Type", "text/html; charset=utf-8")
      self.send_header("Content-Length", str(len(body)))
      self.end_headers()
      self.wfile.write(body)

    def do_POST(self):
      panjang = int(self.headers.get("Content-Length", 0))
      raw = self.rfile.read(panjang)

      try:
        payload = json.loads(raw.decode("utf-8"))
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ip_bersih = ambil_ip_asli(self.headers, self.client_address[0]).replace(
            ":", "_"
        )

        if self.path == "/upload-foto":
          data_url = payload.get("image", "")
          b64 = data_url.split(",", 1)[1]
          fname = os.path.join(CAPTURE_DIR, f"foto_{ts}_{ip_bersih}.jpg")
          with open(fname, "wb") as f:
            f.write(base64.b64decode(b64))
          print(f"{GREEN}[FOTO TERSIMPAN]{R} {fname}")
          msg = f"Foto tersimpan di {fname}"
        elif self.path == "/upload-audio":
          data_url = payload.get("audio", "")
          b64 = data_url.split(",", 1)[1]
          fname = os.path.join(AUDIO_DIR, f"audio_{ts}_{ip_bersih}.webm")
          with open(fname, "wb") as f:
            f.write(base64.b64decode(b64))
          print(f"{GREEN}[AUDIO TERSIMPAN]{R} {fname}")
          msg = f"Audio tersimpan di {fname}"
        else:
          self.send_response(404)
          self.end_headers()
          return

        resp = json.dumps({"ok": True, "message": msg}).encode("utf-8")
        self.send_response(200)
      except Exception as e:
        resp = json.dumps({"ok": False, "message": str(e)}).encode("utf-8")
        self.send_response(400)

      self.send_header("Content-Type", "application/json; charset=utf-8")
      self.send_header("Content-Length", str(len(resp)))
      self.end_headers()
      self.wfile.write(resp)

    def log_message(self, format, *args):
      return

  return SimpleCaptureHandler


def tampilkan_banner():
  os.system("clear")
  print(f"{PINK}{BOLD}")
  print("  ████████╗██████╗  █████╗  ██████╗██╗  ██╗██╗███╗   ██╗ ██████╗ ")
  print("  ╚══██╔══╝██╔══██╗██╔══██╗██╔════╝██║ ██╔╝██║████╗  ██║██╔════╝ ")
  print("     ██║   ██████╔╝███████║██║     █████╔╝ ██║██╔██╗ ██║██║  ███╗")
  print("     ██║   ██╔══██╗██╔══██║██║     ██╔═██╗ ██║██║╚██╗██║██║   ██║")
  print("     ██║   ██║  ██║██║  ██║╚██████╗██║  ██╗██║██║ ╚████║╚██████╔╝")
  print(f"     ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝ ╚═════╝ {R}")
  print(f"{YELLOW}{BOLD}  [ MENU SIMULASI TERMUX ]{R}\n")
  print(f"{CYAN}  ┌──────────────────────────────────────────────┐{R}")
  print(f"{CYAN}  │ {PINK}[ 01 ]{R} {GREEN}Capture Foto (+ Filter CSS){R}          {CYAN}│{R}")
  print(f"{CYAN}  │ {PINK}[ 02 ]{R} {BLUE}Capture Audio (Mic){R}                  {CYAN}│{R}")
  print(f"{CYAN}  │ {PINK}[ 03 ]{R} {YELLOW}Lihat Isi logs.jsonl{R}                 {CYAN}│{R}")
  print(f"{CYAN}  │ {PINK}[ 00 ]{R} {RED}Keluar{R}                               {CYAN}│{R}")
  print(f"{CYAN}  └──────────────────────────────────────────────┘{R}")
  print(f"\n  {GREEN}●{R} {CYAN}TERMUX ~[ TRACKING UI ]{R}")


def lihat_logs():
  print(f"\n{YELLOW}--- Isi {LOG_FILE} ---{R}")
  if not os.path.exists(LOG_FILE):
    print("Belum ada file logs.jsonl.")
  else:
    with open(LOG_FILE, "r", encoding="utf-8") as f:
      lines = f.readlines()[-15:]
      for line in lines:
        print(line.strip())
  input(f"\n{CYAN}Tekan Enter buat balik ke menu...{R}")


def menu():
  while True:
    tampilkan_banner()
    pilih = input(f"  {PINK}>>>{R} Pilih menu [01/02/03/00]: ").strip().lstrip("0")

    if pilih == "1":
      mode = "foto"
    elif pilih == "2":
      mode = "audio"
    elif pilih == "3":
      lihat_logs()
      continue
    elif pilih == "":
      print(f"\n{YELLOW}Sampai jumpa!{R}")
      sys.exit(0)
    else:
      input(f"  {RED}Pilihan gak valid. Tekan Enter...{R}")
      continue

    server = HTTPServer((HOST, PORT), buat_handler(mode))
    print(
        f"\n{GREEN}Mode {mode.upper()} jalan di http://{HOST}:{PORT}{R}"
        f" {YELLOW}(Ctrl+C buat balik){R}\n"
    )
    try:
      server.serve_forever()
    except KeyboardInterrupt:
      print(f"\n{CYAN}Balik ke menu...{R}")
    finally:
      server.server_close()


if __name__ == "__main__":
  menu()