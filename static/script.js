const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('videoInput');

dropZone.onclick = () => fileInput.click();

async function handleUpload() {
    const file = fileInput.files[0];
    if(!file) return alert("Select a file!");

    const formData = new FormData();
    formData.append('video', file);

    document.getElementById('senderLoader').style.display = 'block';
    document.getElementById('senderMsg').innerText = "Watermarking & Encrypting...";

    const res = await fetch('/sender_upload', { method: 'POST', body: formData });
    const data = await res.json();
    
    document.getElementById('senderLoader').style.display = 'none';
    document.getElementById('senderMsg').innerText = `Success! ${data.parts} secure parts in vault.`;
}

async function scanLink() {
    const url = document.getElementById('susLink').value;
    if(!url) return;

    const res = await fetch('/scan_link', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ url: url })
    });
    const data = await res.json();

    if(data.found) {
        const table = document.getElementById('pirateTable');
        const row = table.insertRow(0);
        row.style.background = "#450a0a";
        row.innerHTML = `<td style="color:#f87171;">🚩 PIRACY DETECTED</td><td>${data.url}</td><td>${data.ip}</td>`;
        alert("Invisible Watermark Detected on Remote Site!");
    }
}

// Allow Enter Key
document.getElementById('susLink').addEventListener('keypress', (e) => { if(e.key === 'Enter') scanLink(); });