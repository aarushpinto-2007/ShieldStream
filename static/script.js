function showTab(tabId) {
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(tabId).classList.add('active');
    event.currentTarget.classList.add('active');
}

async function handleReceive() {
    const msg = document.getElementById('receiveStat');
    msg.innerText = "Connecting to Vault...";
    
    const res = await fetch('/run_receiver_task', { method: 'POST' });
    const data = await res.json();
    
    if(data.status === "Success") {
        msg.innerText = `✅ Received & Decrypted ${data.decrypted_count} chunks.`;
        const player = document.getElementById('mainPlayer');
        player.load(); // Refresh the video source
        player.play();
    } else {
        msg.innerText = "📭 Vault Empty or Error.";
    }
}
// ... keep your sender_upload and scanLink functions ...
